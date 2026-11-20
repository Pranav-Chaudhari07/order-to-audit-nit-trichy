"""Seed the benchmark master data (problem-statement section 5).

Run:  python seed.py            (seeds only if the DB is empty)
       python seed.py --reset    (wipes and re-seeds from scratch)
The app also calls seed_if_empty() on startup.
All money in integer paise; quantities in milli-units (x1000).
Rates stored as milli-paise per whole unit: Rs 42/kg -> 4_200_000.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import DB_PATH, SCHEMA, M, now_iso, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

PASSWORD = "demo1234"

USERS = [
    ("salesman_a", "Salesman A", "salesman"),
    ("salesman_b", "Salesman B", "salesman"),
    ("admin", "Factory Admin", "admin"),
    ("production", "Production In-charge", "production"),
    ("accountant", "Accountant / Auditor", "accountant"),
    ("owner", "Owner", "owner"),
]

# sku, name, pack_size, selling_price_paise, gst_rate_pct, hsn
PRODUCTS = [
    ("MUR-200", "Murukku 200g", "200g", 5000, 5, "1905"),
    ("MIX-200", "Mixture 200g", "200g", 4500, 5, "1905"),
    ("CHP-150", "Banana Chips 150g", "150g", 4000, 5, "1905"),
]

CUSTOMERS = [
    ("Retailer A", "Retailer", "Tamil Nadu", "", "12, Main Road, Trichy, Tamil Nadu", "9876500001"),
    ("Distributor B", "Distributor", "Karnataka", "29ABCDE1234F1Z5", "45, MG Road, Bengaluru, Karnataka", "9876500002"),
]

SUPPLIERS = [
    ("Sri Lakshmi Flour Mills", "Tamil Nadu", "33AAAPL1234M1Z5", "9843000001"),
    ("Kovai Oil Traders", "Tamil Nadu", "", "9843000002"),
]

# sku, name, unit, opening avg rate in milli-paise per unit, opening stock (milli)
RAW_MATERIALS = [
    ("RM-FLOUR", "Flour", "kg", 4_200_000, 100_000),
    ("RM-OIL", "Cooking oil", "L", 14_000_000, 30_000),
    ("RM-SPICE", "Salt and spice mix", "kg", 20_000_000, 5_000),
    ("RM-POUCH", "200g pouch", "pcs", 250_000, 500_000),
    ("RM-CARTON", "Carton (20 packets)", "pcs", 1_500_000, 30_000),
]

# BOM for Murukku 200g, one batch = 200 packets expected:
# (raw material sku, qty per batch in milli-units)
BOM_MURUKKU = [
    ("RM-FLOUR", 40_000),
    ("RM-OIL", 10_000),
    ("RM-SPICE", 1_200),
    ("RM-POUCH", 200_000),
    ("RM-CARTON", 10_000),
]
EXPECTED_OUTPUT = 200


def seed(db):
    for username, full_name, role in USERS:
        db.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES (?,?,?,?)",
                   (username, generate_password_hash(PASSWORD), full_name, role))
    prod_ids = {}
    for sku, name, pack, price, gst, hsn in PRODUCTS:
        cur = db.execute("INSERT INTO products(sku,name,pack_size,selling_price_paise,"
                         "gst_rate_pct,hsn) VALUES (?,?,?,?,?,?)",
                         (sku, name, pack, price, gst, hsn))
        prod_ids[sku] = cur.lastrowid
    for name, typ, state, gstin, addr, phone in CUSTOMERS:
        db.execute("INSERT INTO customers(name,type,state,gstin,address,phone) VALUES (?,?,?,?,?,?)",
                   (name, typ, state, gstin, addr, phone))
    for name, state, gstin, phone in SUPPLIERS:
        db.execute("INSERT INTO suppliers(name,state,gstin,phone) VALUES (?,?,?,?)",
                   (name, state, gstin, phone))
    rm_ids = {}
    for sku, name, unit, rate_mp, opening in RAW_MATERIALS:
        cur = db.execute("INSERT INTO raw_materials(sku,name,unit,avg_rate_mp) VALUES (?,?,?,?)",
                         (sku, name, unit, rate_mp))
        rm_ids[sku] = cur.lastrowid
        db.execute("INSERT INTO stock_movements(item_kind,item_id,qty_milli,source_type,"
                   "source_id,ref,notes,created_by,created_at) VALUES ('RM',?,?,'OPENING',NULL,"
                   "'OPENING','Opening stock',NULL,?)", (cur.lastrowid, opening, now_iso()))
    for sku, qty in BOM_MURUKKU:
        db.execute("INSERT INTO bom(product_id,raw_material_id,qty_milli_per_batch,"
                   "expected_output_packets) VALUES (?,?,?,?)",
                   (prod_ids["MUR-200"], rm_ids[sku], qty, EXPECTED_OUTPUT))
    # Opening finished-goods stock: 50 packets of Murukku 200g
    db.execute("INSERT INTO stock_movements(item_kind,item_id,qty_milli,source_type,source_id,"
               "ref,notes,created_by,created_at) VALUES ('FG',?,?,'OPENING',NULL,'OPENING',"
               "'Opening stock',NULL,?)", (prod_ids["MUR-200"], 50 * M, now_iso()))
    db.commit()


def seed_if_empty():
    init_db()
    db = sqlite3.connect(DB_PATH)
    n = db.execute("SELECT COUNT(*) c FROM users").fetchone()[0]
    if n == 0:
        seed(db)
        print("Seeded benchmark master data.")
    db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        print("Database reset.")
    seed_if_empty()
