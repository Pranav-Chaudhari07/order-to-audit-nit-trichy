"""
Order-to-Audit System for a Small Food Manufacturer
NIT Trichy CDI Software Developer Intern - Winter 2026 (shortlisting task)

Stack: Python + Flask + SQLite (+ reportlab for GST invoice PDF).
Money: integer paise everywhere (never floats). Quantities: integer
milli-units (kg/L/pcs x 1000) so stock maths is exact integer maths.
Stock balances are ALWAYS derived from the stock_movements ledger
(SUM over movements), never an overwritten column.
"""
import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   Response, send_file, session, url_for, flash)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
M = 1000                      # milli factor for quantities
TOLERANCE_PCT = Decimal("3")  # variance alert tolerance

# ---------------------------------------------------------------- money/qty
def paise_to_rs(p):
    """Integer paise -> Decimal rupees (2dp)."""
    return (Decimal(int(p)) / Decimal(100)).quantize(Decimal("0.01"))

def fmt_money(p):
    return f"\u20b9{paise_to_rs(p):,.2f}"

def fmt_qty(milli, unit=""):
    d = (Decimal(int(milli)) / Decimal(M)).normalize()
    s = format(d, "f")
    return f"{s} {unit}".strip()

def qty_to_milli(s):
    return int((Decimal(str(s)) * M).to_integral_value(rounding=ROUND_HALF_UP))

def money_to_paise(s):
    return int((Decimal(str(s)) * 100).to_integral_value(rounding=ROUND_HALF_UP))

def gst_split(taxable_paise, rate_pct, intra_state):
    """Return (cgst, sgst, igst) in paise. Total tax rounded half-up to paise,
    then split as evenly as possible (odd paise goes to CGST)."""
    rate = Decimal(str(rate_pct))
    total_tax = int((Decimal(int(taxable_paise)) * rate / Decimal(100)
                     ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if intra_state:
        cgst = (total_tax + 1) // 2
        return cgst, total_tax - cgst, 0
    return 0, 0, total_tax

def weighted_avg_rate(old_qty_milli, old_rate_mp, new_qty_milli, new_rate_mp):
    """Weighted-average rate in milli-paise per whole unit, integer maths."""
    if old_qty_milli + new_qty_milli == 0:
        return new_rate_mp
    num = (Decimal(old_qty_milli) * Decimal(old_rate_mp)
           + Decimal(new_qty_milli) * Decimal(new_rate_mp))
    return int((num / Decimal(old_qty_milli + new_qty_milli)
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

# ---------------------------------------------------------------- app / db
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["DATABASE"] = DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, pack_size TEXT, selling_price_paise INTEGER NOT NULL,
  gst_rate_pct REAL NOT NULL DEFAULT 5, hsn TEXT);
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, type TEXT,
  state TEXT NOT NULL, gstin TEXT, address TEXT, phone TEXT);
CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  state TEXT, gstin TEXT, phone TEXT);
CREATE TABLE IF NOT EXISTS raw_materials(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, unit TEXT NOT NULL,
  avg_rate_mp INTEGER NOT NULL DEFAULT 0);  -- milli-paise per whole unit
CREATE TABLE IF NOT EXISTS bom(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL,
  raw_material_id INTEGER NOT NULL, qty_milli_per_batch INTEGER NOT NULL,
  expected_output_packets INTEGER NOT NULL,
  UNIQUE(product_id, raw_material_id));
CREATE TABLE IF NOT EXISTS purchases(
  id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER,
  purchase_date TEXT NOT NULL, bill_no TEXT, status TEXT DEFAULT 'received',
  created_by INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS purchase_lines(
  id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_id INTEGER NOT NULL,
  raw_material_id INTEGER NOT NULL, qty_milli INTEGER NOT NULL,
  rate_mp INTEGER NOT NULL, amount_paise INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS stock_movements(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_kind TEXT NOT NULL, -- 'RM'|'FG'
  item_id INTEGER NOT NULL, qty_milli INTEGER NOT NULL, -- signed
  source_type TEXT NOT NULL, -- OPENING|PURCHASE|PRODUCTION|INVOICE|ADJUSTMENT
  source_id INTEGER, ref TEXT, notes TEXT,
  created_by INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS production_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL,
  run_date TEXT NOT NULL, expected_packets INTEGER NOT NULL,
  good_packets INTEGER NOT NULL, damaged_pouches INTEGER NOT NULL DEFAULT 0,
  cartons_used INTEGER NOT NULL DEFAULT 0,
  labour_paise INTEGER NOT NULL DEFAULT 0,
  overhead_paise INTEGER NOT NULL DEFAULT 0,
  material_cost_paise INTEGER NOT NULL DEFAULT 0,
  total_cost_paise INTEGER NOT NULL DEFAULT 0,
  cost_per_packet_paise INTEGER, status TEXT DEFAULT 'completed',
  created_by INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS run_consumption(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
  raw_material_id INTEGER NOT NULL, qty_milli INTEGER NOT NULL,
  rate_mp INTEGER NOT NULL, amount_paise INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, salesman_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
  qty INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  -- pending|approved|rejected|dispatched|shortage
  shortage_qty INTEGER NOT NULL DEFAULT 0, notes TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS invoices(
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
  invoice_no TEXT UNIQUE NOT NULL, invoice_date TEXT NOT NULL,
  taxable_paise INTEGER NOT NULL, cgst_paise INTEGER NOT NULL DEFAULT 0,
  sgst_paise INTEGER NOT NULL DEFAULT 0, igst_paise INTEGER NOT NULL DEFAULT 0,
  total_paise INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'posted',
  created_by INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS credit_notes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL,
  credit_no TEXT UNIQUE NOT NULL, amount_paise INTEGER NOT NULL,
  reason TEXT, created_by INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL,
  invoice_id INTEGER, amount_paise INTEGER NOT NULL,
  method TEXT, payment_date TEXT NOT NULL, received_by INTEGER, notes TEXT);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT NOT NULL,
  entity TEXT, entity_id INTEGER, detail TEXT, created_at TEXT NOT NULL);
"""

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(app.config["DATABASE"])
    db.executescript(SCHEMA)
    db.commit()
    db.close()

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def audit(user_id, action, entity, entity_id, detail=""):
    db = get_db()
    db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,detail,created_at)"
               " VALUES (?,?,?,?,?,?)", (user_id, action, entity, entity_id, detail, now_iso()))
    db.commit()

# ------------------------------------------------------------ stock ledger
def stock_balance(item_kind, item_id, db=None):
    db = db or get_db()
    row = db.execute("SELECT COALESCE(SUM(qty_milli),0) AS b FROM stock_movements"
                     " WHERE item_kind=? AND item_id=?", (item_kind, item_id)).fetchone()
    return int(row["b"])

def record_movement(item_kind, item_id, qty_milli, source_type, source_id,
                    ref="", notes="", user_id=None, db=None):
    db = db or get_db()
    db.execute("INSERT INTO stock_movements(item_kind,item_id,qty_milli,source_type,"
               "source_id,ref,notes,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (item_kind, item_id, qty_milli, source_type, source_id, ref,
                notes, user_id, now_iso()))

# ------------------------------------------------------------------ auth
ROLES = ["salesman", "admin", "production", "accountant", "owner"]
READ_ONLY = {"accountant"}

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper

def role_required(*roles):
    from functools import wraps
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("login", next=request.path))
            if u["role"] not in roles and u["role"] != "owner":
                return "Forbidden: role '%s' cannot do this." % u["role"], 403
            return fn(*a, **kw)
        return wrapper
    return deco

def can_write():
    u = current_user()
    return u and u["role"] not in READ_ONLY

@app.context_processor
def inject():
    return dict(user=current_user(), fmt_money=fmt_money, fmt_qty=fmt_qty,
                paise_to_rs=paise_to_rs)

# ------------------------------------------------------------------ routes
@app.route("/")
def index():
    return redirect(url_for("dashboard")) if current_user() else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE username=?",
                       (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session["user_id"] = u["id"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    u = current_user()
    ctx = {"role": u["role"]}
    ctx["fg"] = [(p, stock_balance("FG", p["id"], db)) for p in
                 db.execute("SELECT * FROM products ORDER BY name")]
    ctx["rm"] = [(m, stock_balance("RM", m["id"], db)) for m in
                 db.execute("SELECT * FROM raw_materials ORDER BY name")]
    ctx["pending_orders"] = db.execute(
        "SELECT COUNT(*) c FROM orders WHERE status IN ('pending','shortage')").fetchone()["c"]
    ctx["month_sales"] = db.execute(
        "SELECT COALESCE(SUM(total_paise),0) t FROM invoices WHERE status='posted'"
        " AND substr(invoice_date,1,7)=?", (date.today().isoformat()[:7],)).fetchone()["t"]
    ctx["outstanding"] = db.execute(
        "SELECT COALESCE(SUM(i.total_paise),0)-COALESCE((SELECT SUM(amount_paise)"
        " FROM payments),0) t FROM invoices i WHERE i.status='posted'").fetchone()["t"]
    ctx["recent_runs"] = db.execute(
        "SELECT r.*, p.name pname FROM production_runs r JOIN products p"
        " ON p.id=r.product_id ORDER BY r.id DESC LIMIT 5").fetchall()
    ctx["recent_invoices"] = db.execute(
        "SELECT i.*, c.name cname FROM invoices i JOIN orders o ON o.id=i.order_id"
        " JOIN customers c ON c.id=o.customer_id ORDER BY i.id DESC LIMIT 5").fetchall()
    ctx["alerts"] = variance_alerts(db)
    return render_template("dashboard.html", **ctx)

def variance_alerts(db):
    """Production runs whose yield or any consumption variance exceeds 3%."""
    alerts = []
    for r in db.execute("SELECT r.*, p.name pname FROM production_runs r"
                        " JOIN products p ON p.id=r.product_id"):
        yv = (Decimal(r["good_packets"]) - Decimal(r["expected_packets"])) \
            / Decimal(r["expected_packets"]) * 100
        if abs(yv) > TOLERANCE_PCT:
            alerts.append(f"Run #{r['id']} {r['pname']}: yield variance {yv:+.1f}%")
        for c in db.execute(
                "SELECT rc.*, b.qty_milli_per_batch std, m.name mname FROM run_consumption rc"
                " JOIN bom b ON b.product_id=? AND b.raw_material_id=rc.raw_material_id"
                " JOIN raw_materials m ON m.id=rc.raw_material_id WHERE rc.run_id=?",
                (r["product_id"], r["id"])):
            cv = (Decimal(c["qty_milli"]) - Decimal(c["std"])) / Decimal(c["std"]) * 100
            if abs(cv) > TOLERANCE_PCT:
                alerts.append(f"Run #{r['id']} {c['mname']}: consumption variance {cv:+.1f}%")
    return alerts

# ------------------------------------------------------------------ orders
@app.route("/orders")
@login_required
def orders():
    db = get_db()
    u = current_user()
    q = ("SELECT o.*, c.name cname, p.name pname, u2.full_name sname FROM orders o"
         " JOIN customers c ON c.id=o.customer_id JOIN products p ON p.id=o.product_id"
         " JOIN users u2 ON u2.id=o.salesman_id")
    args = []
    if u["role"] == "salesman":
        q += " WHERE o.salesman_id=?"
        args.append(u["id"])
    rows = db.execute(q + " ORDER BY o.id DESC", args).fetchall()
    return render_template("orders.html", orders=rows,
                           customers=db.execute("SELECT * FROM customers").fetchall(),
                           products=db.execute("SELECT * FROM products").fetchall())

@app.route("/orders/new", methods=["POST"])
@login_required
@role_required("salesman", "admin")
def order_new():
    db = get_db()
    u = current_user()
    customer_id = int(request.form["customer_id"])
    product_id = int(request.form["product_id"])
    qty = int(request.form["qty"])
    if qty <= 0:
        flash("Quantity must be positive.", "error")
        return redirect(url_for("orders"))
    avail = stock_balance("FG", product_id, db) // M
    shortage = max(0, qty - avail)
    status = "shortage" if shortage else "pending"
    cur = db.execute(
        "INSERT INTO orders(salesman_id,customer_id,product_id,qty,status,shortage_qty,"
        "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (u["id"], customer_id, product_id, qty, status, shortage, now_iso(), now_iso()))
    db.commit()
    audit(u["id"], "ORDER_CREATE", "order", cur.lastrowid,
          f"qty={qty} shortage={shortage}")
    flash(f"Order #{cur.lastrowid} created" +
          (f" — SHORTAGE: only {avail} packets in stock, short by {shortage}." if shortage
           else " — pending admin approval."), "warn" if shortage else "ok")
    return redirect(url_for("orders"))

@app.route("/orders/<int:oid>/approve", methods=["POST"])
@login_required
@role_required("admin")
def order_approve(oid):
    db = get_db()
    o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o or o["status"] not in ("pending", "shortage"):
        flash("Order cannot be approved in its current state.", "error")
        return redirect(url_for("orders"))
    avail = stock_balance("FG", o["product_id"], db) // M
    if o["qty"] > avail:
        db.execute("UPDATE orders SET status='shortage', shortage_qty=?, updated_at=? WHERE id=?",
                   (o["qty"] - avail, now_iso(), oid))
        db.commit()
        flash(f"Cannot approve: only {avail} packets in stock, short by {o['qty']-avail}.", "error")
        return redirect(url_for("orders"))
    db.execute("UPDATE orders SET status='approved', shortage_qty=0, updated_at=? WHERE id=?",
               (now_iso(), oid))
    db.commit()
    audit(current_user()["id"], "ORDER_APPROVE", "order", oid, "")
    flash(f"Order #{oid} approved.", "ok")
    return redirect(url_for("orders"))

@app.route("/orders/<int:oid>/reject", methods=["POST"])
@login_required
@role_required("admin")
def order_reject(oid):
    db = get_db()
    db.execute("UPDATE orders SET status='rejected', updated_at=? WHERE id=? AND status IN ('pending','shortage')",
               (now_iso(), oid))
    db.commit()
    audit(current_user()["id"], "ORDER_REJECT", "order", oid, "")
    return redirect(url_for("orders"))

# ---------------------------------------------------------------- invoices
@app.route("/orders/<int:oid>/invoice", methods=["POST"])
@login_required
@role_required("admin")
def order_invoice(oid):
    """Approve -> GST invoice (CGST+SGST intra-state, IGST inter-state)
    -> dispatch: finished-goods stock down via ledger movement."""
    db = get_db()
    u = current_user()
    o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o or o["status"] != "approved":
        flash("Only an approved order can be invoiced.", "error")
        return redirect(url_for("orders"))
    prod = db.execute("SELECT * FROM products WHERE id=?", (o["product_id"],)).fetchone()
    cust = db.execute("SELECT * FROM customers WHERE id=?", (o["customer_id"],)).fetchone()
    avail = stock_balance("FG", o["product_id"], db) // M
    if o["qty"] > avail:
        flash(f"Cannot dispatch: only {avail} packets in stock.", "error")
        return redirect(url_for("orders"))
    taxable = o["qty"] * prod["selling_price_paise"]
    intra = cust["state"].strip().lower() == "tamil nadu"
    cgst, sgst, igst = gst_split(taxable, prod["gst_rate_pct"], intra)
    total = taxable + cgst + sgst + igst
    n = db.execute("SELECT COUNT(*) c FROM invoices").fetchone()["c"] + 1
    inv_no = f"INV-2026-{n:04d}"
    today = date.today().isoformat()
    cur = db.execute(
        "INSERT INTO invoices(order_id,invoice_no,invoice_date,taxable_paise,cgst_paise,"
        "sgst_paise,igst_paise,total_paise,status,created_by,created_at)"
        " VALUES (?,?,?,?,?,?,?,?,'posted',?,?)",
        (oid, inv_no, today, taxable, cgst, sgst, igst, total, u["id"], now_iso()))
    inv_id = cur.lastrowid
    record_movement("FG", o["product_id"], -o["qty"] * M, "INVOICE", inv_id,
                    ref=inv_no, notes=f"Dispatch vs {inv_no} ({cust['name']})",
                    user_id=u["id"], db=db)
    db.execute("UPDATE orders SET status='dispatched', updated_at=? WHERE id=?",
               (now_iso(), oid))
    db.commit()
    audit(u["id"], "INVOICE_CREATE", "invoice", inv_id,
          f"{inv_no} total={total} cgst={cgst} sgst={sgst} igst={igst}")
    flash(f"Invoice {inv_no} raised: {fmt_money(total)} "
          f"({'CGST+SGST' if intra else 'IGST'}). Stock dispatched.", "ok")
    return redirect(url_for("invoice_view", inv_id=inv_id))

@app.route("/invoices")
@login_required
def invoices():
    db = get_db()
    rows = db.execute(
        "SELECT i.*, c.name cname, p.name pname, o.qty FROM invoices i"
        " JOIN orders o ON o.id=i.order_id JOIN customers c ON c.id=o.customer_id"
        " JOIN products p ON p.id=o.product_id ORDER BY i.id DESC").fetchall()
    return render_template("invoices.html", invoices=rows)

@app.route("/invoices/<int:inv_id>")
@login_required
def invoice_view(inv_id):
    db = get_db()
    inv = db.execute(
        "SELECT i.*, c.name cname, c.state cstate, c.address caddr, c.gstin cgstin,"
        " p.name pname, p.hsn, o.qty, u2.full_name sname, p.selling_price_paise price FROM invoices i"
        " JOIN orders o ON o.id=i.order_id JOIN customers c ON c.id=o.customer_id"
        " JOIN products p ON p.id=o.product_id JOIN users u2 ON u2.id=o.salesman_id"
        " WHERE i.id=?", (inv_id,)).fetchone()
    if not inv:
        return "Invoice not found", 404
    notes = db.execute("SELECT * FROM credit_notes WHERE invoice_id=?", (inv_id,)).fetchall()
    return render_template("invoice.html", inv=inv, notes=notes)

@app.route("/invoices/<int:inv_id>/pdf")
@login_required
def invoice_pdf(inv_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    import io
    db = get_db()
    inv = db.execute(
        "SELECT i.*, c.name cname, c.state cstate, c.address caddr, c.gstin cgstin,"
        " p.name pname, p.hsn, o.qty, p.selling_price_paise price FROM invoices i"
        " JOIN orders o ON o.id=i.order_id JOIN customers c ON c.id=o.customer_id"
        " JOIN products p ON p.id=o.product_id WHERE i.id=?", (inv_id,)).fetchone()
    if not inv:
        return "Invoice not found", 404
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18*mm, bottomMargin=18*mm)
    st = getSampleStyleSheet()
    rows = [
        [Paragraph("<b>South Indian Snacks Co.</b><br/>Factory, Tamil Nadu<br/>GSTIN: 33XXXXX0000X1Z5", st["Normal"]),
         Paragraph(f"<b>TAX INVOICE</b><br/>{inv['invoice_no']}<br/>Date: {inv['invoice_date']}<br/>Status: {inv['status']}", st["Normal"])],
        [Paragraph(f"<b>Bill to:</b><br/>{inv['cname']}<br/>{inv['caddr'] or ''}<br/>{inv['cstate']}<br/>GSTIN: {inv['cgstin'] or 'Unregistered'}", st["Normal"]),
         Paragraph(f"Place of supply: {inv['cstate']}", st["Normal"])],
    ]
    t = Table(rows, colWidths=[85*mm, 85*mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BOX", (0, 0), (-1, -1), 0.5, colors.grey)]))
    items = [["Item", "HSN", "Qty", "Rate", "Taxable"]]
    items.append([inv["pname"], inv["hsn"] or "-", str(inv["qty"]),
                  fmt_money(inv["price"]), fmt_money(inv["taxable_paise"])])
    it = Table(items, colWidths=[70*mm, 25*mm, 20*mm, 25*mm, 30*mm])
    it.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    tax_rows = [["Taxable value", fmt_money(inv["taxable_paise"])]]
    if inv["cgst_paise"]:
        tax_rows += [["CGST @ 2.5%", fmt_money(inv["cgst_paise"])],
                     ["SGST @ 2.5%", fmt_money(inv["sgst_paise"])]]
    if inv["igst_paise"]:
        tax_rows.append(["IGST @ 5%", fmt_money(inv["igst_paise"])])
    tax_rows.append(["<b>Total</b>", f"<b>{fmt_money(inv['total_paise'])}</b>"])
    tt = Table(tax_rows, colWidths=[140*mm, 30*mm])
    tt.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"),
                            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]))
    doc.build([t, Spacer(1, 8*mm), it, Spacer(1, 6*mm), tt,
               Spacer(1, 10*mm), Paragraph("E. &amp; O.E. — Computer-generated invoice.", st["Normal"])])
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"{inv['invoice_no']}.pdf")

@app.route("/invoices/<int:inv_id>/cancel", methods=["POST"])
@login_required
@role_required("admin", "owner")
def invoice_cancel(inv_id):
    """Posted invoices are NEVER deleted: cancel via credit note + stock back."""
    db = get_db()
    u = current_user()
    inv = db.execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
    if not inv or inv["status"] != "posted":
        flash("Only a posted invoice can be cancelled.", "error")
        return redirect(url_for("invoices"))
    reason = request.form.get("reason", "Cancelled by admin")
    n = db.execute("SELECT COUNT(*) c FROM credit_notes").fetchone()["c"] + 1
    cn_no = f"CN-2026-{n:04d}"
    db.execute("INSERT INTO credit_notes(invoice_id,credit_no,amount_paise,reason,created_by,created_at)"
               " VALUES (?,?,?,?,?,?)", (inv_id, cn_no, inv["total_paise"], reason, u["id"], now_iso()))
    db.execute("UPDATE invoices SET status='cancelled' WHERE id=?", (inv_id,))
    o = db.execute("SELECT * FROM orders WHERE id=?", (inv["order_id"],)).fetchone()
    record_movement("FG", o["product_id"], o["qty"] * M, "INVOICE", inv_id,
                    ref=cn_no, notes=f"Stock returned on cancellation {cn_no}",
                    user_id=u["id"], db=db)
    db.execute("UPDATE orders SET status='approved', updated_at=? WHERE id=?", (now_iso(), o["id"]))
    db.commit()
    audit(u["id"], "INVOICE_CANCEL", "invoice", inv_id, f"{cn_no}: {reason}")
    flash(f"Invoice {inv['invoice_no']} cancelled via credit note {cn_no}. Stock returned.", "ok")
    return redirect(url_for("invoices"))

# ---------------------------------------------------------------- payments
@app.route("/payments", methods=["GET", "POST"])
@login_required
@role_required("admin", "accountant")
def payments():
    db = get_db()
    if request.method == "POST":
        if not can_write():
            return "Accountant is read-only.", 403
        inv_id = int(request.form["invoice_id"])
        amount = money_to_paise(request.form["amount"])
        inv = db.execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
        if not inv or amount <= 0:
            flash("Invalid payment.", "error")
        else:
            db.execute("INSERT INTO payments(customer_id,invoice_id,amount_paise,method,"
                       "payment_date,received_by,notes) VALUES (?,?,?,?,?,?,?)",
                       (inv and db.execute("SELECT customer_id FROM orders WHERE id=?",
                        (inv["order_id"],)).fetchone()["customer_id"],
                        inv_id, amount, request.form.get("method", "Bank"),
                        request.form.get("payment_date") or date.today().isoformat(),
                        current_user()["id"], request.form.get("notes", "")))
            db.commit()
            audit(current_user()["id"], "PAYMENT", "invoice", inv_id, f"amount={amount}")
            flash(f"Payment of {fmt_money(amount)} recorded.", "ok")
        return redirect(url_for("payments"))
    rows = db.execute(
        "SELECT i.*, c.name cname, o.qty FROM invoices i JOIN orders o ON o.id=i.order_id"
        " JOIN customers c ON c.id=o.customer_id WHERE i.status='posted' ORDER BY i.id DESC").fetchall()
    out = []
    for r in rows:
        paid = db.execute("SELECT COALESCE(SUM(amount_paise),0) p FROM payments WHERE invoice_id=?",
                          (r["id"],)).fetchone()["p"]
        out.append((r, paid, r["total_paise"] - paid))
    pays = db.execute("SELECT p.*, c.name cname FROM payments p JOIN customers c"
                      " ON c.id=p.customer_id ORDER BY p.id DESC LIMIT 20").fetchall()
    return render_template("payments.html", outstanding=out, payments=pays)

# --------------------------------------------------------------- production
@app.route("/production", methods=["GET", "POST"])
@login_required
@role_required("production", "admin")
def production():
    db = get_db()
    u = current_user()
    if request.method == "POST":
        if not can_write():
            return "Read-only role.", 403
        product_id = int(request.form["product_id"])
        expected = int(request.form["expected_packets"])
        good = int(request.form["good_packets"])
        damaged = int(request.form.get("damaged_pouches") or 0)
        cartons = int(request.form.get("cartons_used") or 0)
        labour = money_to_paise(request.form.get("labour") or 0)
        overhead = money_to_paise(request.form.get("overhead") or 0)
        bom_rows = db.execute("SELECT b.*, m.name mname, m.unit, m.avg_rate_mp"
                              " FROM bom b JOIN raw_materials m ON m.id=b.raw_material_id"
                              " WHERE b.product_id=?", (product_id,)).fetchall()
        consumption = []
        for b in bom_rows:
            qty_milli = qty_to_milli(request.form.get(f"qty_{b['raw_material_id']}",
                                      Decimal(b["qty_milli_per_batch"]) / M))
            if qty_milli <= 0:
                continue
            if qty_milli > stock_balance("RM", b["raw_material_id"], db):
                flash(f"Insufficient stock of {b['mname']} for this run.", "error")
                return redirect(url_for("production"))
            amt = int((Decimal(qty_milli) * Decimal(b["avg_rate_mp"]) / Decimal(1000000)
                       ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            consumption.append((b, qty_milli, amt))
        material_cost = sum(a for _, _, a in consumption)
        total_cost = material_cost + labour + overhead
        cpp = int((Decimal(total_cost) / Decimal(good)).quantize(Decimal("1"),
                   rounding=ROUND_HALF_UP)) if good else 0
        cur = db.execute(
            "INSERT INTO production_runs(product_id,run_date,expected_packets,good_packets,"
            "damaged_pouches,cartons_used,labour_paise,overhead_paise,material_cost_paise,"
            "total_cost_paise,cost_per_packet_paise,created_by,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (product_id, date.today().isoformat(), expected, good, damaged, cartons,
             labour, overhead, material_cost, total_cost, cpp, u["id"], now_iso()))
        run_id = cur.lastrowid
        for b, qty_milli, amt in consumption:
            db.execute("INSERT INTO run_consumption(run_id,raw_material_id,qty_milli,rate_mp,amount_paise)"
                       " VALUES (?,?,?,?,?)", (run_id, b["raw_material_id"], qty_milli, b["avg_rate_mp"], amt))
            record_movement("RM", b["raw_material_id"], -qty_milli, "PRODUCTION", run_id,
                            ref=f"RUN-{run_id}", notes=f"Issued to run #{run_id}",
                            user_id=u["id"], db=db)
        # pouches + cartons are raw materials too (in BOM); damaged pouches
        # were consumed but produced nothing — already counted in consumption.
        record_movement("FG", product_id, good * M, "PRODUCTION", run_id,
                        ref=f"RUN-{run_id}", notes=f"{good} good packets produced",
                        user_id=u["id"], db=db)
        db.commit()
        audit(u["id"], "PRODUCTION_RUN", "production_run", run_id,
              f"good={good} expected={expected} cpp={cpp}")
        flash(f"Run #{run_id} recorded: {good} good packets, cost/packet {fmt_money(cpp)}.", "ok")
        return redirect(url_for("production"))
    products = db.execute("SELECT * FROM products").fetchall()
    runs = db.execute("SELECT r.*, p.name pname FROM production_runs r JOIN products p"
                      " ON p.id=r.product_id ORDER BY r.id DESC").fetchall()
    enriched = []
    for r in runs:
        cons = db.execute(
            "SELECT rc.*, m.name mname, m.unit, b.qty_milli_per_batch std"
            " FROM run_consumption rc JOIN raw_materials m ON m.id=rc.raw_material_id"
            " JOIN bom b ON b.product_id=? AND b.raw_material_id=rc.raw_material_id"
            " WHERE rc.run_id=?", (r["product_id"], r["id"])).fetchall()
        yv = (Decimal(r["good_packets"]) - Decimal(r["expected_packets"])) \
            / Decimal(r["expected_packets"]) * 100
        enriched.append((r, cons, yv))
    return render_template("production.html", products=products, runs=enriched)

# --------------------------------------------------------------- purchases
@app.route("/purchases", methods=["GET", "POST"])
@login_required
@role_required("admin", "production")
def purchases():
    db = get_db()
    u = current_user()
    if request.method == "POST":
        if not can_write():
            return "Read-only role.", 403
        supplier_id = int(request.form["supplier_id"])
        rm_id = int(request.form["raw_material_id"])
        qty_milli = qty_to_milli(request.form["qty"])
        rate_mp = int((Decimal(request.form["rate"]) * 100000
                       ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))  # Rs/unit -> milli-paise per unit
        amount = int((Decimal(qty_milli) * Decimal(rate_mp) / Decimal(1000000)
                      ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        cur = db.execute("INSERT INTO purchases(supplier_id,purchase_date,bill_no,created_by,created_at)"
                         " VALUES (?,?,?,?,?)", (supplier_id, date.today().isoformat(),
                         request.form.get("bill_no", ""), u["id"], now_iso()))
        pid = cur.lastrowid
        db.execute("INSERT INTO purchase_lines(purchase_id,raw_material_id,qty_milli,rate_mp,amount_paise)"
                   " VALUES (?,?,?,?,?)", (pid, rm_id, qty_milli, rate_mp, amount))
        old = db.execute("SELECT avg_rate_mp FROM raw_materials WHERE id=?", (rm_id,)).fetchone()
        old_qty = stock_balance("RM", rm_id, db)
        new_avg = weighted_avg_rate(old_qty, old["avg_rate_mp"], qty_milli, rate_mp)
        db.execute("UPDATE raw_materials SET avg_rate_mp=? WHERE id=?", (new_avg, rm_id))
        record_movement("RM", rm_id, qty_milli, "PURCHASE", pid,
                        ref=request.form.get("bill_no", ""), notes="Purchase received",
                        user_id=u["id"], db=db)
        db.commit()
        audit(u["id"], "PURCHASE", "purchase", pid, f"rm={rm_id} qty={qty_milli} amt={amount}")
        flash(f"Purchase recorded: {fmt_money(amount)}. New weighted-avg rate "
              f"{fmt_money(new_avg/1000)} per unit.", "ok")
        return redirect(url_for("purchases"))
    rows = db.execute(
        "SELECT p.*, s.name sname, m.name mname, m.unit, pl.qty_milli, pl.rate_mp, pl.amount_paise"
        " FROM purchases p JOIN suppliers s ON s.id=p.supplier_id"
        " JOIN purchase_lines pl ON pl.purchase_id=p.id"
        " JOIN raw_materials m ON m.id=pl.raw_material_id ORDER BY p.id DESC").fetchall()
    return render_template("purchases.html", purchases=rows,
                           suppliers=db.execute("SELECT * FROM suppliers").fetchall(),
                           materials=db.execute("SELECT * FROM raw_materials").fetchall())

# -------------------------------------------------------------------- stock
@app.route("/stock")
@login_required
def stock():
    db = get_db()
    rm = [(m, stock_balance("RM", m["id"], db)) for m in
          db.execute("SELECT * FROM raw_materials ORDER BY name")]
    fg = [(p, stock_balance("FG", p["id"], db)) for p in
          db.execute("SELECT * FROM products ORDER BY name")]
    ledger = db.execute(
        "SELECT sm.*, u.full_name uname FROM stock_movements sm LEFT JOIN users u"
        " ON u.id=sm.created_by ORDER BY sm.id DESC LIMIT 100").fetchall()
    return render_template("stock.html", rm=rm, fg=fg, ledger=ledger)

# ------------------------------------------------------------------ reports
@app.route("/reports")
@login_required
def reports():
    db = get_db()
    month = request.args.get("month") or date.today().isoformat()[:7]
    sales = db.execute(
        "SELECT i.*, c.name cname, c.state cstate, p.name pname, o.qty FROM invoices i"
        " JOIN orders o ON o.id=i.order_id JOIN customers c ON c.id=o.customer_id"
        " JOIN products p ON p.id=o.product_id WHERE i.status='posted'"
        " AND substr(i.invoice_date,1,7)=? ORDER BY i.invoice_date", (month,)).fetchall()
    gst = {"taxable": sum(r["taxable_paise"] for r in sales),
           "cgst": sum(r["cgst_paise"] for r in sales),
           "sgst": sum(r["sgst_paise"] for r in sales),
           "igst": sum(r["igst_paise"] for r in sales),
           "total": sum(r["total_paise"] for r in sales)}
    ageing = []
    for r in db.execute(
            "SELECT i.*, c.name cname FROM invoices i JOIN orders o ON o.id=i.order_id"
            " JOIN customers c ON c.id=o.customer_id WHERE i.status='posted'"):
        paid = db.execute("SELECT COALESCE(SUM(amount_paise),0) p FROM payments WHERE invoice_id=?",
                          (r["id"],)).fetchone()["p"]
        bal = r["total_paise"] - paid
        if bal > 0:
            days = (date.today() - date.fromisoformat(r["invoice_date"])).days
            bucket = "0-30 days" if days <= 30 else ("31-60 days" if days <= 60 else "60+ days")
            ageing.append((r, bal, days, bucket))
    return render_template("reports.html", month=month, sales=sales, gst=gst, ageing=ageing,
                           alerts=variance_alerts(db))

@app.route("/reports/sales-register.csv")
@login_required
def sales_register_csv():
    db = get_db()
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Invoice", "Date", "Customer", "State", "Product", "Qty",
                "Taxable (Rs)", "CGST (Rs)", "SGST (Rs)", "IGST (Rs)", "Total (Rs)", "Status"])
    for r in db.execute(
            "SELECT i.*, c.name cname, c.state cstate, p.name pname, o.qty FROM invoices i"
            " JOIN orders o ON o.id=i.order_id JOIN customers c ON c.id=o.customer_id"
            " JOIN products p ON p.id=o.product_id ORDER BY i.invoice_date"):
        w.writerow([r["invoice_no"], r["invoice_date"], r["cname"], r["cstate"], r["pname"],
                    r["qty"], paise_to_rs(r["taxable_paise"]), paise_to_rs(r["cgst_paise"]),
                    paise_to_rs(r["sgst_paise"]), paise_to_rs(r["igst_paise"]),
                    paise_to_rs(r["total_paise"]), r["status"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sales_register.csv"})

@app.route("/reports/sales-register.xlsx")
@login_required
def sales_register_xlsx():
    from openpyxl import Workbook
    import io
    db = get_db()
    wb = Workbook(); ws = wb.active; ws.title = "Sales Register"
    ws.append(["Invoice", "Date", "Customer", "State", "Product", "Qty",
               "Taxable (Rs)", "CGST (Rs)", "SGST (Rs)", "IGST (Rs)", "Total (Rs)", "Status"])
    for r in db.execute(
            "SELECT i.*, c.name cname, c.state cstate, p.name pname, o.qty FROM invoices i"
            " JOIN orders o ON o.id=i.order_id JOIN customers c ON c.id=o.customer_id"
            " JOIN products p ON p.id=o.product_id ORDER BY i.invoice_date"):
        ws.append([r["invoice_no"], r["invoice_date"], r["cname"], r["cstate"], r["pname"],
                   r["qty"], float(paise_to_rs(r["taxable_paise"])),
                   float(paise_to_rs(r["cgst_paise"])), float(paise_to_rs(r["sgst_paise"])),
                   float(paise_to_rs(r["igst_paise"])), float(paise_to_rs(r["total_paise"])),
                   r["status"]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="sales_register.xlsx")

@app.route("/reports/stock.csv")
@login_required
def stock_csv():
    import csv, io
    db = get_db()
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Kind", "Item", "Unit", "Balance"])
    for m in db.execute("SELECT * FROM raw_materials"):
        w.writerow(["Raw material", m["name"], m["unit"],
                    float(Decimal(stock_balance("RM", m["id"], db)) / M)])
    for p in db.execute("SELECT * FROM products"):
        w.writerow(["Finished good", p["name"], "packets",
                    stock_balance("FG", p["id"], db) // M])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=stock_report.csv"})

# ------------------------------------------------------------------ masters
@app.route("/masters")
@login_required
@role_required("admin", "owner")
def masters():
    db = get_db()
    return render_template("masters.html",
        products=db.execute("SELECT * FROM products").fetchall(),
        customers=db.execute("SELECT * FROM customers").fetchall(),
        materials=db.execute("SELECT * FROM raw_materials").fetchall(),
        boms=db.execute("SELECT b.*, p.name pname, m.name mname, m.unit FROM bom b"
                        " JOIN products p ON p.id=b.product_id"
                        " JOIN raw_materials m ON m.id=b.raw_material_id").fetchall())

@app.route("/audit")
@login_required
@role_required("admin", "owner", "accountant")
def audit_trail():
    db = get_db()
    rows = db.execute("SELECT a.*, u.full_name uname FROM audit_log a LEFT JOIN users u"
                      " ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200").fetchall()
    return render_template("audit.html", rows=rows)

# ---------------------------------------------------------------------- API
@app.route("/api/stock/<kind>/<int:item_id>")
@login_required
def api_stock(kind, item_id):
    if kind not in ("RM", "FG"):
        return jsonify({"error": "bad kind"}), 400
    return jsonify({"kind": kind, "item_id": item_id,
                    "balance_milli": stock_balance(kind, item_id)})

@app.route("/api/order", methods=["POST"])
@login_required
@role_required("salesman", "admin")
def api_order():
    """Mobile-friendly JSON order entry for salesmen."""
    data = request.get_json(force=True)
    db = get_db()
    qty = int(data["qty"])
    avail = stock_balance("FG", int(data["product_id"]), db) // M
    shortage = max(0, qty - avail)
    cur = db.execute(
        "INSERT INTO orders(salesman_id,customer_id,product_id,qty,status,shortage_qty,"
        "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (current_user()["id"], int(data["customer_id"]), int(data["product_id"]), qty,
         "shortage" if shortage else "pending", shortage, now_iso(), now_iso()))
    db.commit()
    return jsonify({"order_id": cur.lastrowid, "status": "shortage" if shortage else "pending",
                    "available": avail, "shortage": shortage}), 201

if __name__ == "__main__":
    init_db()
    from seed import seed_if_empty
    seed_if_empty()
    app.run(host="127.0.0.1", port=5000, debug=False)
