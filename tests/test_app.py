"""Tests for the Order-to-Audit prototype.
Run:  python -m unittest discover -s tests -v
Covers: money/GST unit maths, weighted-average costing, and the full
benchmark scenario end-to-end through the Flask test client.
"""
import os
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod
from app import gst_split, weighted_avg_rate, paise_to_rs, M
from seed import seed


class UnitTests(unittest.TestCase):
    def test_gst_intra_state(self):
        cgst, sgst, igst = gst_split(750_000, 5, True)  # Rs 7,500 @ 5%
        self.assertEqual((cgst, sgst, igst), (18_750, 18_750, 0))

    def test_gst_inter_state(self):
        cgst, sgst, igst = gst_split(750_000, 5, False)
        self.assertEqual((cgst, sgst, igst), (0, 0, 37_500))

    def test_gst_odd_paise_split(self):
        # Rs 10.01 @ 5% -> 50 paise tax, split 25/25
        self.assertEqual(gst_split(1_001, 5, True), (25, 25, 0))

    def test_weighted_avg_flour(self):
        # 100 kg @ Rs 42 + 60 kg @ Rs 45 -> Rs 43.125/kg = 4,312,500 milli-paise
        avg = weighted_avg_rate(100_000, 4_200_000, 60_000, 4_500_000)
        self.assertEqual(avg, 4_312_500)
        # exact rate Rs 43.125/kg; paise display truncates via integer division
        self.assertEqual(Decimal(avg) / Decimal(100_000), Decimal("43.125"))

    def test_money_never_float(self):
        self.assertIsInstance(paise_to_rs(787_500), Decimal)
        self.assertEqual(str(paise_to_rs(787_500)), "7875.00")


class BenchmarkEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        appmod.app.config["DATABASE"] = os.path.join(self.tmp.name, "test.db")
        appmod.app.config["TESTING"] = True
        import sqlite3
        appmod.init_db()
        db = sqlite3.connect(appmod.app.config["DATABASE"])
        seed(db)
        db.close()
        self.c = appmod.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, username):
        return self.c.post("/login", data={"username": username, "password": "demo1234"},
                           follow_redirects=True)

    def bal(self, kind, item_id):
        import sqlite3
        db = sqlite3.connect(appmod.app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT COALESCE(SUM(qty_milli),0) b FROM stock_movements"
                         " WHERE item_kind=? AND item_id=?", (kind, item_id)).fetchone()
        db.close()
        return int(row["b"])

    def test_benchmark_scenario(self):
        # ids in a fresh seed: products 1=Murukku, customers 1=Retailer A, 2=Distributor B,
        # raw materials 1=flour, 2=oil, 3=spice, 4=pouch, 5=carton, supplier 1
        # 1) Purchase 60 kg flour @ Rs 45/kg
        self.login("admin")
        r = self.c.post("/purchases", data={"supplier_id": 1, "raw_material_id": 1,
                                            "qty": "60", "rate": "45", "bill_no": "B-101"},
                        follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.bal("RM", 1), 160_000)  # 100 + 60 kg

        # 2) + 3) Production run: flour 40, oil 10.5, spice 1.2, pouches 194
        #    (188 good + 6 damaged), cartons 9; labour 1200, overhead 600
        self.login("production")
        r = self.c.post("/production", data={
            "product_id": 1, "expected_packets": 200, "good_packets": 188,
            "damaged_pouches": 6, "cartons_used": 9,
            "qty_1": "40", "qty_2": "10.5", "qty_3": "1.2", "qty_4": "194", "qty_5": "9",
            "labour": "1200", "overhead": "600"}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.bal("RM", 1), 120_000)   # flour closing 120 kg
        self.assertEqual(self.bal("RM", 2), 19_500)    # oil closing 19.5 L
        self.assertEqual(self.bal("RM", 3), 3_800)     # spice 5 - 1.2 = 3.8 kg
        self.assertEqual(self.bal("RM", 4), 306_000)   # pouches 500 - 194 = 306
        self.assertEqual(self.bal("RM", 5), 21_000)    # cartons 30 - 9 = 21
        self.assertEqual(self.bal("FG", 1), 238_000)   # FG after run: 50 + 188

        import sqlite3
        db = sqlite3.connect(appmod.app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        run = db.execute("SELECT * FROM production_runs WHERE id=1").fetchone()
        # Cost per packet: materials 405500 + overheads 180000 = 585500 / 188 = 3114 paise
        self.assertEqual(run["material_cost_paise"], 405_500)
        self.assertEqual(run["total_cost_paise"], 585_500)
        self.assertEqual(run["cost_per_packet_paise"], 3114)  # Rs 31.14
        db.close()

        # 4) Salesman A orders 150 packets for Retailer A (Tamil Nadu)
        self.login("salesman_a")
        r = self.c.post("/orders/new", data={"customer_id": 1, "product_id": 1, "qty": 150},
                        follow_redirects=True)
        self.assertIn(b"pending admin approval", r.data)
        # 5) Admin approves, invoices (CGST+SGST), dispatches
        self.login("admin")
        self.c.post("/orders/1/approve", follow_redirects=True)
        r = self.c.post("/orders/1/invoice", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        db = sqlite3.connect(appmod.app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        inv = db.execute("SELECT * FROM invoices WHERE id=1").fetchone()
        self.assertEqual(inv["taxable_paise"], 750_000)
        self.assertEqual(inv["cgst_paise"], 18_750)
        self.assertEqual(inv["sgst_paise"], 18_750)
        self.assertEqual(inv["igst_paise"], 0)
        self.assertEqual(inv["total_paise"], 787_500)
        db.close()
        self.assertEqual(self.bal("FG", 1), 88_000)  # FG after dispatch: 238 - 150

        # 6) Salesman B orders 120 for Distributor B (Karnataka) -> shortage 32
        self.login("salesman_b")
        r = self.c.post("/orders/new", data={"customer_id": 2, "product_id": 1, "qty": 120},
                        follow_redirects=True)
        self.assertIn(b"SHORTAGE", r.data)
        db = sqlite3.connect(appmod.app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        o2 = db.execute("SELECT * FROM orders WHERE id=2").fetchone()
        self.assertEqual(o2["status"], "shortage")
        self.assertEqual(o2["shortage_qty"], 32)
        db.close()

        # 7) Payment Rs 4,000 from Retailer A -> outstanding Rs 3,875
        self.login("admin")
        self.c.post("/payments", data={"invoice_id": 1, "amount": "4000",
                                       "method": "Bank"}, follow_redirects=True)
        db = sqlite3.connect(appmod.app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        paid = db.execute("SELECT COALESCE(SUM(amount_paise),0) p FROM payments"
                          " WHERE invoice_id=1").fetchone()["p"]
        self.assertEqual(paid, 400_000)
        self.assertEqual(787_500 - paid, 387_500)  # outstanding Rs 3,875
        db.close()

        # 9) Reports + exports still work
        self.assertEqual(self.c.get("/reports/sales-register.csv").status_code, 200)
        self.assertEqual(self.c.get("/reports/sales-register.xlsx").status_code, 200)
        self.assertEqual(self.c.get("/reports/stock.csv").status_code, 200)
        r = self.c.get("/invoices/1/pdf")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/pdf", r.content_type)
        # Variance flags appear on dashboard
        r = self.c.get("/dashboard")
        self.assertIn(b"yield variance", r.data)
        self.assertIn(b"consumption variance", r.data)

    def test_cancel_invoice_uses_credit_note_and_restores_stock(self):
        self.login("admin")
        self.c.post("/orders/new", data={"customer_id": 1, "product_id": 1, "qty": 10},
                    follow_redirects=True)
        self.c.post("/orders/1/approve", follow_redirects=True)
        self.c.post("/orders/1/invoice", follow_redirects=True)
        self.assertEqual(self.bal("FG", 1), 40_000)
        r = self.c.post("/invoices/1/cancel", data={"reason": "wrong qty"},
                        follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.bal("FG", 1), 50_000)  # stock returned
        import sqlite3
        db = sqlite3.connect(appmod.app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        inv = db.execute("SELECT * FROM invoices WHERE id=1").fetchone()
        self.assertEqual(inv["status"], "cancelled")
        cn = db.execute("SELECT * FROM credit_notes WHERE invoice_id=1").fetchone()
        self.assertIsNotNone(cn)
        db.close()

    def test_accountant_is_read_only(self):
        self.login("accountant")
        r = self.c.post("/payments", data={"invoice_id": 1, "amount": "100"},
                        follow_redirects=True)
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
