# Demo Video Script — Order-to-Audit System (NIT Trichy CDI, Winter 2026)

**Total length: ≤ 8 minutes.** Record in one take if possible; speak
plainly, show the screen, and read the numbers out loud exactly as
written — those are the figures the evaluators will check.
**Submit as an unlisted YouTube link or a Google Drive link** (either is
fine; unlisted, not public, not private).

**Presenter:** Pranav Chaudhari, B.Tech CSE (Data Science), R.C. Patel
Institute of Technology, Shirpur.

> **Know every part of the code before you record.** Shortlisted
> candidates get a 30-minute interview with a live walkthrough and a
> small on-the-spot change (for example, adding a 500 g pack size that
> shares the same BOM) — so don't just memorise this script; be able to
> explain and change any line.

## 0:00–0:40 — Intro (40 sec)

*(Admin dashboard on screen.)*

> "Hi, I'm Pranav Chaudhari, a third-year B.Tech Computer Science and
> Data Science student. This is my Order-to-Audit System for a small
> South Indian snacks maker, built for the CDI Winter Internship task.
> It takes the factory from a salesman's order all the way to the
> monthly auditor's report. Two loops — sales and production — meet at
> finished-goods stock. I'll walk through the full benchmark scenario
> in order, starting on the salesman's mobile view."

## 0:40–1:20 — Step 1: Purchase, and Step 2: the production run (40 sec)

*(Admin/production view. Record the flour purchase, then the run.)*

> "First, production buys 60 kilos of flour at 45 rupees a kilo.
> Opening flour was 100 kilos, so we're at 160. Then the production
> run: the BOM for a batch of 200 Murukku packets needs 40 kilos of
> flour, 10 litres of oil, and 1.2 kilos of spice mix. We actually
> issued 40 kilos of flour, 10.5 litres of oil, and 1.2 kilos of
> spice — and we got 188 good packets, with 6 pouches damaged and
> 9 cartons used."

**Say exactly:** "Flour closing is **120 kilos**. Oil closing is
**19.5 litres**. Pouches closing is **306**. Finished stock after the
run is **238 packets**."

*(Show the stock screen with 120, 19.5, 306, 238 visible.)*

## 1:20–2:10 — Step 3: Retailer A's order, on the mobile salesman view (50 sec)

*(Switch to the phone/mobile view, logged in as `salesman_a`.)*

> "Now the sales side — this is what the salesman sees on his phone.
> I'm logged in as salesman_a. Retailer A in Tamil Nadu orders
> 150 packets at 50 rupees. I place the order, and it goes to the
> admin for verification — a salesman can't invoice his own order.
> That's the first control in the system."

*(Place the order; show it sitting as unverified.)*

## 2:10–3:10 — Steps 4–6: Verify, invoice, pay, dispatch (60 sec)

*(Back to the desktop admin view.)*

> "As admin, I verify the order, then raise the invoice. Tamil Nadu
> is intra-state, so GST splits into CGST and SGST."

**Say exactly:** "150 packets at 50 rupees is **7,500 rupees**, plus
**187 rupees 50 paise CGST** and **187 rupees 50 paise SGST** — invoice
total **7,875 rupees**."

> "Retailer A pays 4,000 rupees against it."

**Say exactly:** "Outstanding is **3,875 rupees**."

> "Now I dispatch the 150 packets, and finished stock drops."

**Say exactly:** "Finished stock after dispatch is **88 packets** —
238 minus 150."

*(Show the invoice, the payment, the receivables screen with ₹3,875,
and stock at 88.)*

## 3:10–4:00 — Step 7: Distributor B and the shortage flag (50 sec)

*(Mobile view as `salesman_b`, then admin view.)*

> "Distributor B in Karnataka orders 120 packets. We only have 88 in
> stock — the system flags it instead of letting us promise stock we
> don't have."

**Say exactly:** "Shortage of **32 packets** — 120 ordered, only 88 in
stock. And because B is in Karnataka, any invoice here would carry
**IGST**, not CGST and SGST."

*(Show the shortage flag on the order.)*

## 4:00–5:00 — Step 8: Variances (60 sec)

*(Production/variance report on screen.)*

> "Back to production. The run was supposed to make 200 packets and
> made 188 — and it used more oil than the BOM said."

**Say exactly:** "Yield variance is **minus 6 percent** — flagged.
Oil variance is **plus 5 percent** — flagged. Both show up on the
production report so the owner sees them before the month ends."

*(Show both flags on the variance report.)*

## 5:00–6:00 — Step 9: Cost per packet (60 sec)

*(Costing screen on screen.)*

> "Finally, costing. Flour is valued at a weighted average — opening
> 100 kilos at 42 rupees and the new 60 kilos at 45 gives 43 rupees
> 12.5 paise a kilo. Materials for the run come to 4,055 rupees, plus
> 1,200 labour and 600 for gas and power — 5,855 in total, spread over
> the 188 good packets."

**Say exactly:** "Cost per packet is **31 rupees 14 paise**, and
against a selling price of 50 rupees that's a margin of **18 rupees
86 paise** per packet."

*(Show the costing breakdown: ₹4,055 + ₹1,200 + ₹600 = ₹5,855 ÷ 188.)*

## 6:00–7:00 — Reports and the audit trail (60 sec)

*(Monthly reports + audit log on screen.)*

> "Everything feeds the monthly reports — stock, sales and GST,
> production, receivables, and the audit trail. Every stock movement
> links back to the document that caused it — a purchase, a run, an
> invoice, a dispatch — and every action records who did it and when.
> The accountant login is read-only, so the auditor's view can't
> change the numbers it's checking. That's the whole loop: order to
> audit."

*(Flip through the stock report, the GST summary, receivables, and one
audit-log entry.)*

## 7:00–7:40 — Roles, limits, close (40 sec)

*(Login screen, or the role list.)*

> "There are six logins — two salesmen, admin, production, a read-only
> accountant, and the owner — all on password demo1234. Two honest
> limits: there's no offline sync yet, so the salesman view needs
> connectivity, and there's no Tally export — reports come from the
> app itself. The code, the design note and the benchmark numbers are
> in the repo. Thank you."

*(End screen: repo/README visible, or a simple thank-you slide.)*

## Timing check

| Section | Time |
|---|---|
| Intro | 0:40 |
| Purchase + production run | 0:40 |
| Retailer A order (mobile) | 0:50 |
| Verify, invoice, pay, dispatch | 1:00 |
| Distributor B + shortage | 0:50 |
| Variances | 1:00 |
| Cost per packet | 1:00 |
| Reports + audit trail | 1:00 |
| Roles, limits, close | 0:40 |
| **Total** | **7:40** (20 sec spare) |

## Numbers to say out loud (checklist — all must appear on screen)

- [ ] Flour **120 kg**, oil **19.5 L**, pouches **306**
- [ ] Finished **238** after the run, then **88** after dispatch
- [ ] Yield **−6%** flagged, oil **+5%** flagged
- [ ] Invoice **₹7,875** (₹7,500 + ₹187.50 CGST + ₹187.50 SGST)
- [ ] Outstanding **₹3,875**
- [ ] Shortage **32** (Distributor B, IGST if invoiced)
- [ ] Cost per packet **₹31.14**, margin **₹18.86**

## Before recording

1. Reset the database to the seed data and run the 9 steps once
   end-to-end, so every number on screen matches this script.
2. Confirm the costing screen shows ₹31.14 (it depends on the seeded
   flour rate of ₹42/kg — see README).
3. Keep both views ready: mobile salesman view (narrow window or
   phone) and desktop admin view — the script switches between them
   three times.
