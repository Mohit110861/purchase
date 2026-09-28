"""Business rules and pure maths. No LLM and no I/O here, so results are exact and testable."""
import math

TARGET_DAYS = 30         # we want stock that covers 30 days of demand
MIN_COVER_DAYS = 21      # a reduced order must still give at least 21 days of cover
APPROVAL_LIMIT = 5000.0  # orders above this value need a human
MAX_RETRIES = 2          # 1 first try + 2 retries, then escalate
HORIZON = 90             # days we look ahead when checking for stock-outs
LIVE = ("PARTIAL", "CONFIRMED")   # PO statuses that will still deliver goods


def incoming(pos):
    return sum(p["confirmed_qty"] for p in pos if p["status"] in LIVE)


def position(on_hand, pos):
    """Stock we have plus stock we are sure will arrive."""
    return on_hand + incoming(pos)


def shortfall(on_hand, demand, pos):
    return max(0, math.ceil(TARGET_DAYS * demand - position(on_hand, pos)))


def stockout_day(on_hand, demand, pos):
    """First day stock goes below zero, or None if it never does within the horizon."""
    if demand <= 0:
        return None
    arrivals = [(p["eta_days"], p["confirmed_qty"]) for p in pos if p["status"] in LIVE]
    for day in range(HORIZON + 1):
        stock = on_hand - demand * day + sum(q for eta, q in arrivals if eta <= day)
        if stock < 0:
            return day
    return None


def build_options(f, excluded):
    """List every supplier option and say whether it passes ALL constraints.
    f = facts dict. excluded = supplier ids that already failed in this run."""
    room = f["capacity"] - f["position"]
    options = []
    for s in f["suppliers"]:
        o = {"id": s["id"], "price": s["price"], "eta": s["lead_days"],
             "reliability": s["reliability"], "qty": 0, "cost": 0.0, "cover_days": 0.0,
             "reduced": False, "feasible": False, "why_not": "", "approval_reasons": [],
             "score": 1e9}
        options.append(o)
        if s["id"] in excluded:
            o["why_not"] = "failed earlier in this run"
            continue
        if not s["active"]:
            o["why_not"] = "supplier is not active"
            continue
        if s["id"] == f["original_supplier"]:
            o["why_not"] = "original supplier said it cannot supply the rest"
            continue

        qty = max(f["shortfall"], s["moq"])              # respect minimum order
        limit = min(s["max_qty"], int(f["budget"] // s["price"]), room)
        if qty > limit:                                  # budget / storage / supplier cap
            qty = limit
            o["reduced"] = True
        if qty < s["moq"]:
            o["why_not"] = (f"cannot reach minimum order {s['moq']} "
                            f"(max allowed by budget/storage/supplier is {max(limit, 0)})")
            continue
        cover = (f["position"] + qty) / f["demand"]
        if o["reduced"] and cover < MIN_COVER_DAYS:
            o["why_not"] = f"reduced order gives only {cover:.1f} days cover (min {MIN_COVER_DAYS})"
            continue
        if f["stockout"] is not None and s["lead_days"] > f["stockout"]:
            o["why_not"] = f"arrives day {s['lead_days']}, stock runs out day {f['stockout']}"
            continue

        o.update(qty=qty, cost=round(qty * s["price"], 2), cover_days=round(cover, 1),
                 feasible=True)
        useful = min(qty, f["shortfall"])                # extra units above shortfall are waste
        o["score"] = round(o["cost"] / useful / s["reliability"], 3)   # lower is better
        if o["cost"] > APPROVAL_LIMIT:
            o["approval_reasons"].append(f"order value {o['cost']:.0f} above limit {APPROVAL_LIMIT:.0f}")
        if not s["approved"]:
            o["approval_reasons"].append("supplier is not yet approved")
        if o["reduced"]:
            o["approval_reasons"].append("order is smaller than what we need")
    options.sort(key=lambda o: (not o["feasible"], o["reduced"], o["score"]))
    return options
