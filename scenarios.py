"""Test scenarios. Each one has a known correct answer so we can grade the agent."""
import copy
from data import BASE

ORIG = "PO-1001"


def make(mutate=None):
    d = copy.deepcopy(BASE)
    if mutate:
        mutate(d)
    return d


def _stock_ok(d):       d["skus"]["SKU-100"]["on_hand"] = 500
def _only_c(d):
    for s in d["suppliers"]["SKU-100"]:
        if s["id"] in ("S-B", "S-D"):
            s["active"] = False
def _budget(x):
    def f(d): d["budget_remaining"] = x
    return f
def _no_forecast(d):    d["skus"]["SKU-100"]["daily_demand"] = None
def _only_d(d):
    for s in d["suppliers"]["SKU-100"]:
        if s["id"] in ("S-B", "S-C"):
            s["active"] = False


SCENARIOS = [
    dict(name="stock_is_enough", mutate=_stock_ok, faults={}, approve=True,
         about="Stock plus the 250 already coming is enough. Agent must NOT buy more.",
         expect=dict(decision="NO_ACTION")),
    dict(name="happy_path", mutate=None, faults={}, approve=True,
         about="Normal shortfall. Best alternate supplier, order passes all checks.",
         expect=dict(decision="ORDER_PLACED", supplier="S-B", qty=230, approval=False, attempts=1)),
    dict(name="min_order_forces_extra", mutate=_only_c, faults={}, approve=True,
         about="Only S-C is left and its minimum order (300) is above the shortfall (230).",
         expect=dict(decision="ORDER_PLACED", supplier="S-C", qty=300, approval=False, attempts=1)),
    dict(name="tight_budget_partial", mutate=_budget(1500), faults={}, approve=True,
         about="Budget too small for the full order. Agent buys less, and asks a human.",
         expect=dict(decision="ORDER_PLACED", supplier="S-B", qty=142, approval=True, attempts=1)),
    dict(name="budget_too_low_escalate", mutate=_budget(400), faults={}, approve=True,
         about="Budget cannot reach any supplier's minimum order. Agent must escalate.",
         expect=dict(decision="ESCALATED")),
    dict(name="supplier_rejects_order", mutate=None, faults={"reject": ["S-B"]}, approve=True,
         about="S-B rejects the PO. Agent must retry with the next best supplier.",
         expect=dict(decision="ORDER_PLACED", supplier="S-D", qty=230, approval=True, attempts=2)),
    dict(name="price_jumps_at_confirm", mutate=_budget(2800), faults={"price_mult": {"S-B": 1.25}},
         approve=True,
         about="S-B confirms at a higher price and breaks the budget. Validator must catch it.",
         expect=dict(decision="ORDER_PLACED", supplier="S-D", qty=230, approval=True, attempts=2)),
    dict(name="missing_forecast", mutate=_no_forecast, faults={}, approve=True,
         about="Demand forecast is missing. Agent must escalate, not guess.",
         expect=dict(decision="ESCALATED")),
    dict(name="all_suppliers_fail", mutate=None, faults={"reject": ["S-B", "S-C", "S-D"]},
         approve=True,
         about="Every supplier rejects. Agent must stop retrying and escalate.",
         expect=dict(decision="ESCALATED")),
    dict(name="human_declines", mutate=_only_d, faults={}, approve=False,
         about="Only new supplier S-D is left and the human says no. Must escalate.",
         expect=dict(decision="ESCALATED")),
]
