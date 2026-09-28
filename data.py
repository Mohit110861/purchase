"""Mock data. Day numbers are days from today (today = day 0)."""

BASE = {
    "budget_remaining": 20000.0,
    "storage_capacity": 800,          # max units the warehouse can hold
    "skus": {
        "SKU-100": {"name": "Widget", "on_hand": 120, "daily_demand": 20.0},
    },
    "suppliers": {
        "SKU-100": [
            # S-A is the supplier who could only ship 250 of 500
            {"id": "S-A", "price": 10.0, "lead_days": 4, "moq": 100, "max_qty": 1000,
             "reliability": 0.95, "active": True, "approved": True},
            {"id": "S-B", "price": 10.5, "lead_days": 5, "moq": 100, "max_qty": 1000,
             "reliability": 0.90, "active": True, "approved": True},
            # cheap but slow and big minimum order
            {"id": "S-C", "price": 9.2, "lead_days": 12, "moq": 300, "max_qty": 2000,
             "reliability": 0.80, "active": True, "approved": True},
            # fast and reliable but expensive, and a NEW supplier (not yet approved)
            {"id": "S-D", "price": 12.0, "lead_days": 2, "moq": 50, "max_qty": 500,
             "reliability": 0.97, "active": True, "approved": False},
        ],
    },
    "pos": [
        # We ordered 500, supplier confirmed only 250.
        {"po_id": "PO-1001", "sku": "SKU-100", "supplier_id": "S-A", "ordered_qty": 500,
         "confirmed_qty": 250, "unit_price": 10.0, "eta_days": 4, "status": "PARTIAL"},
    ],
}
