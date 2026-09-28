"""Mock ERP. These are the only ways the agent can read or change anything.
`faults` lets tests make the ERP misbehave: {"reject": [supplier ids], "price_mult": {id: x}}."""
import copy

READ_TOOLS = {"get_po", "get_inventory", "get_forecast", "get_open_pos",
              "get_suppliers", "get_budget", "get_storage"}


class MockERP:
    def __init__(self, data, faults=None):
        self.db = copy.deepcopy(data)
        self.faults = faults or {}
        self.calls = []              # every tool call is recorded, used by evaluation
        self._seq = 2000

    def _c(self, name, **kw):
        self.calls.append((name, kw))

    # ---------- read tools ----------
    def get_po(self, po_id):
        self._c("get_po", po_id=po_id)
        po = next((p for p in self.db["pos"] if p["po_id"] == po_id), None)
        return copy.deepcopy(po)

    def get_inventory(self, sku):
        self._c("get_inventory", sku=sku)
        s = self.db["skus"].get(sku)
        return None if s is None else {"on_hand": s["on_hand"]}

    def get_forecast(self, sku):
        self._c("get_forecast", sku=sku)
        s = self.db["skus"].get(sku)
        if s is None or s["daily_demand"] is None:
            return None
        return {"daily_demand": s["daily_demand"]}

    def get_open_pos(self, sku):
        self._c("get_open_pos", sku=sku)
        return copy.deepcopy([p for p in self.db["pos"]
                              if p["sku"] == sku and p["status"] in ("PARTIAL", "CONFIRMED")])

    def get_suppliers(self, sku):
        self._c("get_suppliers", sku=sku)
        return copy.deepcopy(self.db["suppliers"].get(sku, []))

    def get_budget(self):
        self._c("get_budget")
        return {"remaining": self.db["budget_remaining"]}

    def get_storage(self):
        self._c("get_storage")
        return {"capacity": self.db["storage_capacity"]}

    # ---------- write tools ----------
    def create_po(self, sku, supplier_id, qty, quoted_price):
        self._c("create_po", sku=sku, supplier_id=supplier_id, qty=qty)
        if supplier_id in self.faults.get("reject", []):
            return {"status": "REJECTED", "reason": "supplier declined the order"}
        sup = next(s for s in self.db["suppliers"][sku] if s["id"] == supplier_id)
        # the real price is only known at confirmation; a fault can change it
        price = round(quoted_price * self.faults.get("price_mult", {}).get(supplier_id, 1.0), 2)
        self._seq += 1
        po = {"po_id": f"PO-{self._seq}", "sku": sku, "supplier_id": supplier_id,
              "ordered_qty": qty, "confirmed_qty": qty, "unit_price": price,
              "eta_days": sup["lead_days"], "status": "CONFIRMED"}
        self.db["pos"].append(po)
        self.db["budget_remaining"] -= qty * price   # the ERP does NOT stop us going negative
        return copy.deepcopy(po)

    def cancel_po(self, po_id):
        self._c("cancel_po", po_id=po_id)
        po = next(p for p in self.db["pos"] if p["po_id"] == po_id)
        if po["status"] != "CANCELLED":
            po["status"] = "CANCELLED"
            self.db["budget_remaining"] += po["confirmed_qty"] * po["unit_price"]
        return {"status": "CANCELLED"}

    def close_po_remainder(self, po_id):
        """Stop waiting for the units the supplier cannot deliver."""
        self._c("close_po_remainder", po_id=po_id)
        po = next(p for p in self.db["pos"] if p["po_id"] == po_id)
        po["ordered_qty"] = po["confirmed_qty"]
        po["status"] = "CONFIRMED"
        return copy.deepcopy(po)
