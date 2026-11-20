# Design — Order-to-Audit System

## 1. Data model

One SQLite database. Money is stored as **integer paise** (never floats);
quantities as decimals with explicit units. Every stock movement is a row
in `stock_ledger` linked to the document that caused it.

### Core tables

| Table | Key fields | Purpose |
|---|---|---|
| `users` | id, username, password_hash, role | Login; roles: salesman, admin, production, accountant (read-only), owner |
| `customers` | id, name, state, gstin, type (retailer/distributor) | State decides CGST+SGST vs IGST |
| `items` | id, name, unit, kind (raw / packing / finished), gst_rate, selling_price_paise | Masters for flour, oil, spice, pouches, cartons, Murukku 200 g |
| `bom` | id, finished_item_id, raw_item_id, qty_per_batch, expected_output | Standard consumption per 200-packet batch |
| `purchases` | id, item_id, qty, rate_paise, supplier, date, created_by | Goods receipt; drives weighted-average rate |
| `production_runs` | id, bom_id, date, expected_output, good_output, damaged_pouches, cartons_used, labour_paise, overhead_paise, created_by | One run; holds the costing inputs |
| `run_issues` | id, run_id, item_id, qty_issued | Actual material consumed by a run |
| `orders` | id, customer_id, salesman_id, item_id, qty, rate_paise, status (draft → verified → invoiced → dispatched / short), date | Salesman order; verified by admin |
| `invoices` | id, order_id, taxable_paise, cgst_paise, sgst_paise, igst_paise, total_paise, date | One invoice per order; GST split by customer state |
| `dispatches` | id, invoice_id, qty, date | Reduces finished-goods stock |
| `payments` | id, invoice_id, amount_paise, date, mode | Reduces the receivable |
| `stock_ledger` | id, item_id, txn_type, qty_change, ref_type, ref_id, balance_after, date, created_by | **The single source of truth for stock** |
| `audit_log` | id, user_id, action, entity, entity_id, old_value, new_value, timestamp | Who did what, when, to which document |

### ER sketch (text)

```
users 1───* orders ───1 invoices ───1 dispatches
            │              │  │
            │              │  └──* payments
            │              └──* stock_ledger (finished goods, ref=dispatch)
customers 1───* orders / invoices
items 1───* bom ───* production_runs ───* run_issues
items 1───* purchases ───* stock_ledger (raw/packing, ref=purchase)
production_runs ───* stock_ledger (finished goods +, ref=run; raw −, ref=issue)
users 1───* audit_log ───* (every table above)
```

## 2. How stock and BOM consumption are computed

**Ledger-based, never a stored balance.** Closing stock is always
derived, never typed in:

```
closing = opening + receipts − issues − sales ± adjustments
```

- *Receipts* — purchases and good production output (positive
  `stock_ledger` rows, `ref_type` = `purchase` / `production_run`).
- *Issues* — BOM issues on a run and dispatches (negative rows,
  `ref_type` = `run_issue` / `dispatch`).
- *Adjustments* — damaged pouches and write-offs (negative rows,
  `ref_type` = `adjustment`, with a reason). Damaged pouches are
  deducted from pouch stock; they never become finished goods.
- Every row carries `balance_after`, so the auditor can replay the
  ledger line by line from opening to closing, and every row points
  back to its source document (`ref_type` + `ref_id`: a purchase, a
  run, an invoice, a dispatch). No stock change exists without a
  document, and no document changes stock without a ledger row —
  the two are written in one database transaction.
- **BOM consumption:** a run declares the batch (200 packets
  expected). Standard issue = the BOM quantities (flour 40 kg, oil
  10 L, spice 1.2 kg, pouches 200, cartons 10). The production user
  records the *actual* issue (40 kg, 10.5 L, 1.2 kg in the benchmark);
  variance per material = (actual − standard) / standard, flagged
  when it exceeds the app's 3% alert tolerance. Yield variance =
  (good output − expected) / expected (benchmark: (188 − 200)/200 =
  −6%, flagged). Shortage is checked at order time: if ordered qty >
  finished-goods balance, the order is flagged short by the
  difference (benchmark: 120 − 88 = 32) and cannot be invoiced in
  full.

## 3. Costing and valuation

- **Weighted-average valuation.** Each raw/packing item carries a
  running average rate: (opening value + purchase values) / (opening
  qty + purchased qty). The rate changes only on a purchase. Issues
  are valued at the current average (benchmark flour:
  (100 × ₹42 + 60 × ₹45) / 160 = **₹43.125/kg**; 40 kg issued =
  ₹1,725). Opening flour is seeded at ₹42/kg.
- **Cost per packet** for a run = (materials at weighted-average
  rates + labour + gas/power) / good packets produced. Benchmark:
  (₹4,055 + ₹1,200 + ₹600) / 188 = ₹5,855 / 188 ≈ **₹31.14**.
  Labour and gas/power are allocated in full to the run and spread
  over good output only (188, not the 200 expected). Margin =
  selling price − cost per packet (₹50 − ₹31.14 ≈ **₹18.86**).
- **Integer-paise money maths.** All amounts are integer paise (or
  `decimal`); GST is rounded to the nearest paise per invoice, and
  the 5% GST splits exactly into CGST/SGST halves for intra-state
  sales (₹187.50 + ₹187.50 on ₹7,500) or a single IGST line
  inter-state. No binary floats touch money anywhere.
- **Receivables:** invoice total − payments = outstanding (benchmark
  ₹7,875 − ₹4,000 = **₹3,875**), aged per customer on the monthly
  report.

## 4. Audit trail and role-based access

- **Audit trail:** every create/verify/invoice/dispatch/payment/run
  writes an `audit_log` row (user, action, entity, before/after
  values, timestamp). The monthly auditor's report lists the ledger
  and the log side by side, so any stock figure can be traced to the
  person and document behind it. Nothing is hard-deleted; corrections
  are new reversing/adjustment entries.
- **Role-based access:** enforced server-side on every route, not
  just by hiding buttons. Salesmen create orders only; admin verifies,
  invoices and dispatches; production records purchases and runs;
  accountant and owner are read-only on transactions (accountant sees
  reports and the audit trail; owner additionally sees margins and
  variances). A user who tries a URL outside their role gets a
  denial, logged in the audit trail.
