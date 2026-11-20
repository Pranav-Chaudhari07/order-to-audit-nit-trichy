# BUILD_NOTES — Order-to-Audit System (NIT Trichy CDI, Winter 2026)

## Stack actually used
- **Python 3.12 + Flask 3.1.3 + SQLite** (Flask was missing on the VM; installed
  with `pip install --break-system-packages flask reportlab` — see
  `requirements.txt`). No other framework.
- **GST invoice PDF: reportlab 5.1.0** (real PDF, not printable HTML).
- **Excel export: openpyxl** (already present on the VM; listed in
  `requirements.txt` unpinned). CSV exports use only the stdlib.
- Frontend: server-rendered Jinja templates + one small CSS file
  (`static/style.css`), mobile-friendly (viewport meta, large inputs, single
  column on small screens). A JSON API (`POST /api/order`, `GET /api/stock/...`)
  exists for the salesman mobile view.
- Money: **integer paise everywhere** (never floats). Quantities: integer
  milli-units (kg/L/pcs × 1000). Rates stored as milli-paise per whole unit,
  so Rs 43.125/kg = 4,312,500 exactly.

## How to run (single command)
```bash
cd nit-trichy-cdi-order-to-audit
python3 app.py        # or: ./run.sh
# open http://127.0.0.1:5000
```
First run creates `data.db` and seeds the benchmark master data automatically.
To re-seed from scratch: `python3 seed.py --reset` (deletes `data.db`).
Install deps first if on a fresh machine: `pip install -r requirements.txt`.

## Test logins (all password `demo1234`)
| Username | Role | Sees / can do |
|---|---|---|
| `salesman_a` | Salesman A | Own orders, mobile order entry (`/api/order`) |
| `salesman_b` | Salesman B | Own orders |
| `admin` | Factory admin / billing | Approve orders, raise GST invoices + dispatch, payments, purchases, masters |
| `production` | Production in-charge | Production runs, purchases, stock |
| `accountant` | Accountant / auditor | **Read-only** — reports, invoices, audit trail; write attempts return 403 |
| `owner` | Owner | Everything incl. dashboard, masters, audit trail |

## Endpoints (main)
- `/login`, `/logout`, `/dashboard` (role dashboard + variance alerts)
- `/orders` (+ `POST /orders/new`, `/orders/<id>/approve|reject|invoice`)
- `/invoices`, `/invoices/<id>`, `/invoices/<id>/pdf`, `/invoices/<id>/cancel`
- `/payments` (record payment; outstanding per invoice)
- `/production` (new run; variances shown per run)
- `/purchases` (raw-material inwards; updates weighted-avg rate)
- `/stock` (summary + full ledger), `/reports` (sales register, GST summary, ageing)
- `/reports/sales-register.csv`, `/reports/sales-register.xlsx`, `/reports/stock.csv`
- `/masters`, `/audit`
- `/api/stock/<RM|FG>/<id>`, `POST /api/order`

## Schema (explainable, in `app.py` SCHEMA)
- `users`, `products`, `customers`, `suppliers`, `raw_materials`
  (`avg_rate_mp` = weighted-average rate, milli-paise/unit), `bom`
  (qty per batch + expected output).
- `purchases` + `purchase_lines`; `production_runs` + `run_consumption`.
- `orders` (status pending/approved/rejected/dispatched/shortage +
  `shortage_qty`), `invoices` (taxable/cgst/sgst/igst/total, status
  posted/cancelled), `credit_notes`, `payments`.
- `stock_movements` — **the single source of truth for stock**. Every balance
  is `SUM(qty_milli)` over this ledger; there is no stored balance column
  anywhere. Each movement links to its source (`source_type`:
  OPENING/PURCHASE/PRODUCTION/INVOICE/ADJUSTMENT + `source_id` + `ref`).
- `audit_log` — every order/invoice/payment/purchase/production action with
  user and timestamp. Posted invoices are **never deleted**: cancel creates a
  credit note, flips status to `cancelled`, and returns the stock via a
  ledger movement.

## Valuation & costing method (as required by the task)
- **Raw-material valuation: weighted-average cost.** Each purchase re-averages:
  `new_avg = (old_qty×old_rate + new_qty×new_rate) / (old_qty+new_qty)`.
  Benchmark: flour (100×42 + 60×45)/160 = **Rs 43.125/kg**.
- **Cost per packet** = (materials at weighted-avg rates + labour + gas/power
  overhead) ÷ good packets only. Damaged pouches are charged as material
  consumed (they were used), cartons at actual count used.
- Benchmark run: materials Rs 4,055.00 (flour 40×43.125=1,725.00; oil
  10.5×140=1,470.00; spice 1.2×200=240.00; pouches 194×2.50=485.00 incl. the
  6 damaged; cartons 9×15=135.00) + overheads Rs 1,800.00 = Rs 5,855.00 ÷ 188
  good packets = **Rs 31.14/packet** (Rs 31.138… rounded half-up to paise).
  This matches the task's expected figure exactly — no difference to explain.

## GST rules implemented
- Place of supply = customer state. Tamil Nadu (factory state) → **CGST+SGST**
  (5% split 2.5/2.5); any other state → **IGST 5%**. Total tax rounded
  half-up to the paise, then split as evenly as possible (odd paise to CGST).
- Benchmark: Retailer A (TN) 150×Rs 50 = Rs 7,500 taxable + Rs 187.50 CGST +
  Rs 187.50 SGST = **Rs 7,875**. Distributor B (Karnataka) would be IGST if
  invoiced.

## Variance rules
- Yield variance = (good − expected)/expected; consumption variance per
  material = (actual − BOM standard)/standard. Anything with |variance| > **3%**
  is flagged in red on the production page, the dashboard, and the reports
  page. Benchmark: yield −6.0% flagged; oil +5.0% flagged.

## Tests — result
```
$ python3 -m unittest discover -s tests -v
Ran 8 tests in ~4s — OK
```
- 5 unit tests: GST CGST/SGST vs IGST, odd-paise split, weighted-average
  flour rate, money-is-Decimal (never float).
- 3 end-to-end tests through the Flask test client on a fresh seeded DB:
  the **full benchmark scenario** (asserts flour 120 kg, oil 19.5 L, spice
  3.8 kg, pouches 306, cartons 21, FG 238 after run / 88 after dispatch,
  invoice 7,500 + 187.50 + 187.50 = 7,875, outstanding 3,875 after the
  Rs 4,000 payment, Distributor B shortage of 32, cost/packet Rs 31.14,
  material cost Rs 4,055, and that the PDF/CSV/XLSX exports return 200);
  invoice cancellation via credit note restores stock; accountant is
  read-only (403 on write).

## Live smoke test (20 Nov 2026)
Started `python3 app.py`, logged in as `admin`, dashboard rendered,
`/api/stock/FG/1` returned 50,000 milli (50 packets), opening flour showed
100 kg. Server stopped afterwards.

## Known gaps / honest notes
- Single-file Flask app (`app.py`, ~700 lines) — fine for the prototype and
  the demo, but a production build would split routes into blueprints.
- The production form's quantity fields are keyed by raw-material id
  (`qty_1`…`qty_5` for the seeded data); if masters are edited the form
  labels stay correct but the field names follow the ids — works, just not
  pretty.
- No user registration / password reset UI (logins are seeded demo accounts);
  `SECRET_KEY` defaults to a dev value — set the env var in production.
- Stock-ledger item column shows numeric ids, not names (names are on the
  summary tables above it).
- Runs on `127.0.0.1:5000` only; no TLS / production WSGI server configured.
- Nothing has been submitted to NIT Trichy and no GitHub repo was created.
