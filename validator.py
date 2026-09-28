"""Plain-code checks. The LLM never grades its own work.
The validator re-reads the ERP instead of trusting what the agent remembers."""
from policy import MIN_COVER_DAYS, TARGET_DAYS, position, shortfall, stockout_day


def _row(name, ok, detail):
    return {"check": name, "ok": bool(ok), "detail": detail}


def validate_order(erp, plan, new_po_id):
    sku = plan["sku"]
    po = erp.get_po(new_po_id)
    sup = next(s for s in erp.get_suppliers(sku) if s["id"] == plan["supplier"])
    on_hand = erp.get_inventory(sku)["on_hand"]
    demand = erp.get_forecast(sku)["daily_demand"]
    open_pos = erp.get_open_pos(sku)
    others = [p for p in open_pos if p["po_id"] != new_po_id]
    capacity = erp.get_storage()["capacity"]
    budget_left = erp.get_budget()["remaining"]
    pos_after = position(on_hand, open_pos)
    sd = stockout_day(on_hand, demand, others)

    checks = [
        _row("po_confirmed", po and po["status"] == "CONFIRMED", f"status={po and po['status']}"),
        _row("supplier_matches", po and po["supplier_id"] == plan["supplier"],
             f"planned {plan['supplier']}"),
        _row("full_qty_confirmed", po and po["confirmed_qty"] >= plan["qty"],
             f"confirmed {po['confirmed_qty']} of {plan['qty']}"),
        _row("min_order_ok", po and po["confirmed_qty"] >= sup["moq"], f"moq {sup['moq']}"),
        _row("budget_ok", budget_left >= 0, f"budget left {budget_left:.2f}"),
        _row("storage_ok", pos_after <= capacity, f"units after {pos_after} / capacity {capacity}"),
        _row("arrives_in_time", sd is None or po["eta_days"] <= sd,
             f"eta day {po['eta_days']}, stock-out day {sd}"),
        _row("cover_ok", pos_after / demand >= MIN_COVER_DAYS,
             f"cover {pos_after / demand:.1f} days (min {MIN_COVER_DAYS})"),
    ]
    return checks


def validate_no_action(erp, sku):
    on_hand = erp.get_inventory(sku)["on_hand"]
    demand = erp.get_forecast(sku)["daily_demand"]
    open_pos = erp.get_open_pos(sku)
    short = shortfall(on_hand, demand, open_pos)
    return [_row("no_shortfall", short == 0, f"shortfall {short} for {TARGET_DAYS}-day target")]
