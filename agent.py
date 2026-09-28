"""The purchasing agent. Handles the event: 'supplier confirmed less than we ordered'.

Loop: gather facts -> build options (code) -> choose (LLM or rule) -> human approval if needed
      -> act -> validate (code) -> if it failed: roll back, exclude that supplier, retry -> escalate."""
import json
import os
import urllib.request

from policy import MAX_RETRIES, build_options, position, shortfall, stockout_day
from validator import validate_no_action, validate_order


# ---------------------------------------------------------------- choosers
class RuleChooser:
    """Picks the best-ranked feasible option. Works with no API key."""
    def choose(self, facts, feasible):
        return feasible[0], "rule: lowest cost per useful unit after supplier reliability"


class LLMChooser:
    """Asks Claude to pick among options that code already checked.
    Claude can only pick an id from the list. Anything else falls back to the rule."""
    def __init__(self, model=None):
        self.model = model or os.getenv("MODEL", "claude-sonnet-5")
        self.fallback = RuleChooser()

    def choose(self, facts, feasible):
        try:
            keys = ("id", "qty", "price", "cost", "eta", "reliability", "cover_days",
                    "approval_reasons")
            slim = [{k: o[k] for k in keys} for o in feasible]
            prompt = (
                "You are a purchasing advisor. A supplier could not deliver the full order.\n"
                f"Shortfall: {facts['shortfall']} units, demand {facts['demand']}/day, "
                f"stock runs out on day {facts['stockout']}.\n"
                "These options already pass every hard constraint (budget, storage, minimum "
                "order, arrival time). Pick the best one. Do not invent new options.\n"
                f"Options: {json.dumps(slim)}\n"
                'Reply with JSON only: {"option_id": "...", "reason": "..."}'
            )
            body = json.dumps({"model": self.model, "max_tokens": 400,
                               "messages": [{"role": "user", "content": prompt}]}).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body,
                headers={"content-type": "application/json",
                         "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                         "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            text = "".join(b.get("text", "") for b in data["content"])
            reply = json.loads(text[text.index("{"): text.rindex("}") + 1])
            pick = next((o for o in feasible if o["id"] == reply["option_id"]), None)
            if pick is None:
                raise ValueError("LLM picked an option that is not in the list")
            return pick, "llm: " + str(reply.get("reason", ""))
        except Exception as e:            # any problem -> safe fallback, never crash
            pick, why = self.fallback.choose(facts, feasible)
            return pick, f"{why} (LLM unavailable or invalid: {type(e).__name__})"


# ---------------------------------------------------------------- facts
def gather(erp, po_id):
    """Read everything needed. Missing data is reported, never guessed."""
    po = erp.get_po(po_id)
    if po is None:
        return {"missing": [f"purchase order {po_id}"]}
    sku = po["sku"]
    inv, fc = erp.get_inventory(sku), erp.get_forecast(sku)
    open_pos, suppliers = erp.get_open_pos(sku), erp.get_suppliers(sku)
    budget, storage = erp.get_budget(), erp.get_storage()
    missing = [n for n, v in (("inventory", inv), ("forecast", fc),
                              ("suppliers", suppliers or None)) if v is None]
    if missing:
        return {"missing": missing, "sku": sku}
    on_hand, demand = inv["on_hand"], fc["daily_demand"]
    return {
        "missing": [], "sku": sku, "po": po, "original_supplier": po["supplier_id"],
        "on_hand": on_hand, "demand": demand, "open_pos": open_pos, "suppliers": suppliers,
        "budget": budget["remaining"], "capacity": storage["capacity"],
        "position": position(on_hand, open_pos),
        "shortfall": shortfall(on_hand, demand, open_pos),
        "stockout": stockout_day(on_hand, demand, open_pos),
    }


# ---------------------------------------------------------------- the agent
def run_agent(erp, po_id, chooser=None, approve_fn=None, max_retries=MAX_RETRIES):
    chooser = chooser or RuleChooser()
    approve_fn = approve_fn or (lambda option: False)   # safe default: nobody approved
    trace, excluded, attempts = [], set(), 0

    def log(step, detail):
        trace.append({"step": step, "detail": detail})

    def escalate(reason):
        log("ESCALATE", reason)
        return {"decision": "ESCALATED", "reason": reason, "attempts": attempts,
                "po": None, "trace": trace}

    for _ in range(max_retries + 1):
        attempts += 1
        f = gather(erp, po_id)
        if f["missing"]:
            return escalate("Missing data, will not guess: " + ", ".join(f["missing"]))
        log("FACTS", f"on_hand={f['on_hand']} demand={f['demand']}/day incoming="
            f"{f['position'] - f['on_hand']} shortfall={f['shortfall']} "
            f"stockout_day={f['stockout']} budget={f['budget']:.0f} capacity={f['capacity']}")

        if f["shortfall"] == 0:
            erp.close_po_remainder(po_id)
            checks = validate_no_action(erp, f["sku"])
            log("VALIDATE", checks)
            if all(c["ok"] for c in checks):
                return {"decision": "NO_ACTION", "attempts": attempts, "po": None,
                        "validation": checks, "trace": trace}
            return escalate("No-action check failed")

        options = build_options(f, excluded)
        log("OPTIONS", options)
        feasible = [o for o in options if o["feasible"]]
        if not feasible:
            why = "; ".join(f"{o['id']}: {o['why_not']}" for o in options)
            return escalate("No option passes all constraints. " + why)

        choice, why = chooser.choose(f, feasible)
        log("CHOICE", f"{choice['id']} qty={choice['qty']} cost={choice['cost']} ({why})")

        if choice["approval_reasons"]:
            ok = approve_fn(choice)
            log("APPROVAL", f"needed because: {choice['approval_reasons']} -> "
                            f"{'approved' if ok else 'NOT approved'}")
            if not ok:
                return escalate("Human did not approve: " + "; ".join(choice["approval_reasons"]))

        po = erp.create_po(f["sku"], choice["id"], choice["qty"], choice["price"])
        if po["status"] == "REJECTED":
            excluded.add(choice["id"])
            log("ACT", f"{choice['id']} rejected the order ({po['reason']}). Excluding it, retrying.")
            continue

        plan = {"sku": f["sku"], "supplier": choice["id"], "qty": choice["qty"]}
        checks = validate_order(erp, plan, po["po_id"])
        log("VALIDATE", checks)
        if all(c["ok"] for c in checks):
            erp.close_po_remainder(po_id)       # only now stop waiting for the missing 250
            return {"decision": "ORDER_PLACED", "po": erp.get_po(po["po_id"]), "choice": choice,
                    "needed_approval": bool(choice["approval_reasons"]),
                    "validation": checks, "attempts": attempts, "trace": trace}

        bad = [c["check"] for c in checks if not c["ok"]]
        erp.cancel_po(po["po_id"])              # roll back so we do not leave a bad PO
        excluded.add(choice["id"])
        log("ROLLBACK", f"{po['po_id']} failed {bad}. Cancelled it, excluding {choice['id']}, retrying.")

    return escalate(f"Gave up after {attempts} attempts")
