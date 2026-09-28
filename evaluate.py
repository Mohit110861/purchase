"""Runs every scenario and grades it on the six questions from the brief.
Grading uses an audit that looks at the raw ERP state, not at the agent's own story."""
import json
import sys

from agent import RuleChooser, run_agent
from policy import LIVE
from scenarios import ORIG, SCENARIOS, make
from tools import READ_TOOLS, MockERP


def audit(erp):
    """Independent check of the final system state. Returns a list of problems."""
    db, problems = erp.db, []
    sku = "SKU-100"
    live = [p for p in db["pos"] if p["status"] in LIVE]
    new_live = [p for p in live if p["po_id"] != ORIG]
    if db["budget_remaining"] < 0:
        problems.append("budget is negative")
    units = db["skus"][sku]["on_hand"] + sum(p["confirmed_qty"] for p in live)
    if units > db["storage_capacity"]:
        problems.append("storage capacity exceeded")
    for p in new_live:
        sup = next(s for s in db["suppliers"][sku] if s["id"] == p["supplier_id"])
        if p["confirmed_qty"] < sup["moq"]:
            problems.append(f"{p['po_id']} below minimum order")
    if len(new_live) > 1:
        problems.append("more than one live replacement PO (duplicate or leftover)")
    return problems


def grade(sc, result, erp):
    exp, orig = sc["expect"], erp.get_po(ORIG)
    new_live = [p for p in erp.db["pos"] if p["po_id"] != ORIG and p["status"] in LIVE]
    called = {name for name, _ in erp.calls}
    g = {}
    g["decision"] = result["decision"] == exp["decision"]
    g["info"] = READ_TOOLS <= called
    g["constraints"] = not audit(erp)
    if exp["decision"] == "ORDER_PLACED":
        po = new_live[0] if new_live else None
        g["action"] = bool(po and po["supplier_id"] == exp["supplier"] and po["confirmed_qty"] == exp["qty"]
                           and result.get("needed_approval") == exp["approval"]
                           and result["attempts"] == exp["attempts"] and orig["status"] == "CONFIRMED")
        g["validated"] = bool(result.get("validation") and all(c["ok"] for c in result["validation"]))
    elif exp["decision"] == "NO_ACTION":
        g["action"] = not new_live and orig["status"] == "CONFIRMED"
        g["validated"] = bool(result.get("validation") and all(c["ok"] for c in result["validation"]))
    else:   # escalation: nothing may be left behind, original PO must stay untouched
        g["action"] = not new_live and orig["status"] == "PARTIAL"
        g["validated"] = None           # nothing to validate
    return g


def run_all(chooser=None):
    rows = []
    for sc in SCENARIOS:
        erp = MockERP(make(sc["mutate"]), sc["faults"])
        result = run_agent(erp, ORIG, chooser or RuleChooser(), lambda o, a=sc["approve"]: a)
        g = grade(sc, result, erp)
        rows.append({"name": sc["name"], "about": sc["about"], "expected": sc["expect"],
                     "decision": result["decision"], "attempts": result["attempts"],
                     "grades": g, "passed": all(v in (True, None) for v in g.values()),
                     "audit": audit(erp), "trace": result["trace"],
                     "reason": result.get("reason", "")})
    return rows


def show(v):
    return "n/a" if v is None else ("PASS" if v else "FAIL")


if __name__ == "__main__":
    rows = run_all()
    print(f"{'scenario':26}{'decision':14}{'right':7}{'info':7}{'rules':7}{'action':8}{'valid':7}")
    for r in rows:
        g = r["grades"]
        print(f"{r['name']:26}{r['decision']:14}{show(g['decision']):7}{show(g['info']):7}"
              f"{show(g['constraints']):7}{show(g['action']):8}{show(g['validated']):7}")
    ok = sum(r["passed"] for r in rows)
    print(f"\n{ok}/{len(rows)} scenarios passed")
    if "--json" in sys.argv:
        json.dump(rows, open("docs/results.json", "w"), indent=1, default=str)
    sys.exit(0 if ok == len(rows) else 1)
