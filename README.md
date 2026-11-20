# Order-to-Audit System for a Small Food Manufacturer

A working prototype that takes a small South Indian snacks maker from a
salesman's order to the monthly auditor's report — built for the
**Centre for Digital Infrastructure (CDI), NIT Tiruchirappalli —
Software Developer Intern, Winter 2026** shortlisting task
(Internship ID `cmwj0x6w00ozlp0lhpbd74d9`, closes 27 Nov 2026, 5:00 PM).

Two loops meet at finished-goods stock:

- **Sales loop** — order → verification → GST invoice → dispatch →
  finished-goods stock down → receivables.
- **Production loop** — purchase → issued per BOM → production run →
  finished-goods stock up → variance and cost per packet.

Both loops feed the monthly reports (stock, sales/GST, production,
receivables, audit trail).

## Setup — run it locally

```bash
python app.py
```

Then open the URL printed in the terminal (by default
`http://127.0.0.1:5000`).

> **Check `BUILD_NOTES.md` first if it exists in this folder.** The app
> builder documents the real run command there; if it differs from
> `python app.py` (for example a different entry point, a virtual
> environment, or a seed/reset command), follow `BUILD_NOTES.md` instead.
> No other setup is needed: the app creates its SQLite database and seed
> data on first run.

## Stack and why

**Python + Flask + SQLite** (see `BUILD_NOTES.md` for the exact run
and seed commands).

Flask keeps the whole system in one small, readable codebase that a
single intern can explain line by line in the interview; SQLite needs no
server, so the prototype runs with a single command and the database file
itself is the audit record; Python's `decimal` module gives exact
integer-paise money maths with no floating-point rounding. The stack was
chosen for auditability and zero-install friction, not for scale — it is
a prototype for one factory, not a multi-tenant product.

## Test logins

Password for **all** accounts: `demo1234`

| Login | Role | What they can do |
|---|---|---|
| `salesman_a` | Salesman | Create orders, view own orders and customers |
| `salesman_b` | Salesman | Same as above (separate salesman, for the two-order benchmark) |
| `admin` | Admin | Verify orders, create invoices, dispatch, manage masters (items, BOM, customers, rates) |
| `production` | Production | Record purchases, issue materials per BOM, record production runs |
| `accountant` | Accountant (read-only) | View reports, receivables and audit trail; cannot create or edit transactions |
| `owner` | Owner | Full view of reports, margins and variances; read-only on transactions |

## Features — against the section-6 tiers

> **Status note (20 Nov 2026, verified):** the app is built and the
> full test suite passes — `python3 -m unittest discover -s tests`
> gives **8 tests, OK**, including an end-to-end benchmark test that
> runs all 9 steps through the real app and asserts every number in
> the table below (stock closings, GST split, outstanding, shortage,
> both variances, cost per packet ₹31.14). Stack confirmed as Python
> + Flask + SQLite, run command `python app.py` (port 5000),
> integer-paise money maths, ledger-derived stock, weighted-average
> valuation, GST splitting, role checks, the audit trail, a GST
> invoice PDF and CSV/XLSX report exports.

### Must-have

| Feature | Status |
|---|---|
| Role-based login (salesman / admin / production / accountant read-only / owner) | Built & verified |
| Salesman order entry (mobile-friendly view) with customer, item, quantity, rate | Built & verified |
| Order verification by admin before invoicing | Built & verified |
| GST invoice: CGST + SGST for intra-state (Tamil Nadu), IGST for inter-state (Karnataka) | Built & verified |
| Dispatch reduces finished-goods stock; invoice creates a receivable | Built & verified |
| Purchase entry updates raw-material stock | Built & verified |
| BOM issue per production run, with variance vs standard BOM | Built & verified |
| Production run adds good packets to finished-goods stock; damaged pouches recorded separately | Built & verified |
| Stock ledger: opening + receipts − issues/sales ± adjustments = closing, every movement linked to its source document | Built & verified |
| Cost per packet (weighted-average materials + allocated labour and gas/power) | Built & verified |
| Monthly reports: stock, sales/GST, production, receivables, audit trail | Built & verified |
| Shortage flag when an order exceeds finished-goods stock | Built & verified |

### Should-have

| Feature | Status |
|---|---|
| Yield variance and material variance flags (e.g. −6% yield, +5% oil) | Built & verified |
| Receivables ageing / outstanding per customer | Built & verified |
| Audit trail: who did what, when, on which document | Built & verified |
| Mobile salesman view separate from the desktop admin view | Built & verified |
| Damaged-pouch and carton tracking on the run | Built & verified |

### Stretch

| Feature | Status |
|---|---|
| Offline sync for the salesman app | **Not built** — the prototype needs connectivity; see Known gaps |
| Tally export | **Not built** — reports are on-screen/downloadable from the app only; see Known gaps |
| Barcode / batch-wise traceability | **Not built** |

No stretch goal is claimed as built. If the finished app does add one,
update this table and `BUILD_NOTES.md` before submitting.

## Benchmark scenario — numbers the app must reproduce

Seed data (opening stock): flour 100 kg, oil 30 L, spice mix 5 kg,
pouches 500, cartons 30, finished Murukku 200 g packets 50.
BOM per batch (200 packets expected): flour 40 kg, oil 10 L, spice mix
1.2 kg, pouches 200, cartons 10.

| Step | What happens | Expected result |
|---|---|---|
| 1. Purchase | 60 kg flour @ ₹45/kg | Flour stock 160 kg |
| 2. Production run | Issue 40 kg flour, 10.5 L oil, 1.2 kg spice; output 188 good packets, 6 pouches damaged, 9 cartons used | Flour **120 kg**, oil **19.5 L**, spice 3.8 kg, pouches **306**, cartons 21, finished **238** |
| 3. Order — Retailer A (Tamil Nadu) | 150 packets @ ₹50 | — |
| 4. Invoice — Retailer A | GST 5%, intra-state | ₹7,500 + ₹187.50 CGST + ₹187.50 SGST = **₹7,875** |
| 5. Payment — Retailer A | ₹4,000 received | Outstanding **₹3,875** |
| 6. Dispatch — Retailer A | 150 packets out | Finished **88** |
| 7. Order — Distributor B (Karnataka) | 120 packets | **Shortage of 32 flagged** (only 88 in stock); IGST if invoiced |
| 8. Variances | Yield and oil vs BOM | Yield **−6% flagged**, oil **+5% flagged** |
| 9. Costing | Cost per packet for the run | **≈ ₹31.14**, margin vs ₹50 selling price ≈ **₹18.86** |

All arithmetic above was verified by hand/computation while writing this
README (see "How the numbers were checked" below).

### Worked figures

- **Flour closing:** 100 + 60 − 40 = **120 kg**.
- **Oil closing:** 30 − 10.5 = **19.5 L**.
- **Pouches closing:** 500 − 188 (packed) − 6 (damaged) = **306**.
- **Finished stock:** 50 + 188 = **238** after the run; 238 − 150 = **88**
  after dispatch to Retailer A.
- **Yield variance:** (188 − 200) / 200 = **−6%**.
- **Oil variance:** (10.5 − 10) / 10 = **+5%**.
- **Retailer A invoice:** 150 × ₹50 = ₹7,500; 5% GST = ₹375, split
  ₹187.50 CGST + ₹187.50 SGST; total **₹7,875**.
- **Retailer A outstanding:** ₹7,875 − ₹4,000 = **₹3,875**.
- **Distributor B shortage:** 120 ordered − 88 in stock = **32 packets**.
  B is in Karnataka, so any invoice to B carries **IGST** (5%), not
  CGST + SGST.
- **Flour valuation (weighted average):** opening 100 kg @ ₹42/kg and
  purchase 60 kg @ ₹45/kg → (100 × 42 + 60 × 45) / 160 = ₹6,900 / 160 =
  **₹43.125/kg**. Flour consumed in the run: 40 × ₹43.125 = **₹1,725**.
- **Cost per packet:** materials ₹4,055 + labour ₹1,200 + gas/power ₹600
  = ₹5,855; ₹5,855 / 188 = ₹31.1436… ≈ **₹31.14**. Margin:
  ₹50 − ₹31.14 = **₹18.86** per packet.

### How the numbers were checked

Each figure above was recomputed independently (Python) while writing
this README and then asserted by the app's own end-to-end benchmark
test (8/8 tests pass, 20 Nov 2026): stock closings, GST split,
outstanding, shortage, both variances, the weighted-average rate, the
₹5,855 run total and the ₹31.14 / ₹18.86 results all reconcile exactly.
The two inputs the brief leaves implicit are confirmed in `seed.py`:
opening flour is valued at ₹42/kg, and the other seeded rates (oil
₹140/L, spice mix ₹200/kg, pouch ₹2.50, carton ₹15) reproduce the
₹4,055 materials total exactly.

## Assumptions

1. **Valuation method — weighted average.** Every material issue is
   valued at the running weighted-average rate for that item
   (opening stock value + purchases, divided by quantity on hand).
   The rate moves only when a purchase arrives, never on an issue.
2. **Overhead rule — labour + gas/power allocated to the run.** The
   run's labour (₹1,200) and gas/power (₹600) are charged in full to
   that production run and spread over the good packets produced
   (188), not over the 200 expected. No other overhead (rent,
   depreciation, admin) is included.
3. **Money maths — integer paise, no floats.** All money is stored and
   computed in paise (integer) or `decimal`; GST is rounded to the
   nearest paise per invoice line, and the CGST/SGST split is exact
   halves of the 5% GST.
4. **GST treatment.** 5% GST on Murukku 200 g packets; intra-state
   (Tamil Nadu) = CGST + SGST, inter-state (Karnataka) = IGST. The
   invoice total, not the taxable value, is what the customer owes.
5. **Damaged pouches consume stock but produce nothing.** The 6 damaged
   pouches are deducted from pouch stock and excluded from good output
   and from the cost-per-packet denominator.
6. **Cartons are packaging stock, not finished goods.** 9 cartons used
   on the run reduce carton stock (30 → 21) and do not affect packet
   counts.
7. **One order, one invoice, one dispatch** in the benchmark; partial
   dispatch and partial payment are supported by the design but are
   not exercised by the benchmark numbers.
8. **Single factory, single currency (INR), single GST rate (5%)**
   for the prototype. Multi-rate GST and multi-branch stock are out
   of scope.

## Known gaps (honest limits)

- **Offline sync is not built.** The salesman view needs connectivity;
  orders cannot be captured offline and synced later.
- **No Tally export.** Reports are viewed/printed from the app; there
  is no Tally-compatible export file.
- **No barcode or batch traceability.** Stock is tracked by item and
  quantity only, not by batch/lot or barcode.
- **No automated e-invoicing / e-way bill integration.** GST figures
  are computed for the invoice; nothing is filed with the GST portal.
- **Single-factory, single-user-at-a-time assumptions.** No
  concurrency locking beyond SQLite's own; two users editing the same
  stock item simultaneously can conflict.
- **Seeded rates drive the costing figure.** The ₹31.14 cost per packet
  reproduces exactly with the seed data in `seed.py` (opening flour
  ₹42/kg; oil ₹140/L, spice mix ₹200/kg, pouch ₹2.50, carton ₹15),
  confirmed by the end-to-end benchmark test.
- **Feature table above is verified** against the running build
  (8/8 tests pass, 20 Nov 2026, including the end-to-end benchmark).
