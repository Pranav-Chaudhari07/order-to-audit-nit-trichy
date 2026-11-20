# Demo Video Notes — Order-to-Audit System (NIT Trichy CDI, Winter 2026)

## File

- `demo-video.mp4` — H.264 1280×720, 30 fps, AAC audio, **5 min 05 sec
  (305 s, 6.8 MB)**, verified with ffprobe. Limit is 8 minutes, so there are
  almost 3 minutes of spare.
- The video is **not** committed to git: `.gitignore` already excludes
  `*.mp4`. Upload it as an **unlisted YouTube** or **Google Drive** link for
  the CDI portal's Portfolio/demo URL field.

## How it was recorded

- Scripted screen capture of the **live app running on this VM**
  (Flask + SQLite, `python3 app.py` on http://127.0.0.1:5000), driven by
  Playwright with a stock Chromium headless shell — a real browser, not a
  mock-up. The database was reset to the exact section-5 seed data
  (`python3 seed.py --reset`) before recording, and **all 9 benchmark steps
  were performed for real through the UI** (purchase, production run, both
  salesman orders, admin approval, GST invoice, dispatch, ₹4,000 payment).
  Every number on screen comes from the live app; nothing was faked.
- Mobile salesman steps were recorded at a **390×844 phone viewport** and
  are shown pillarboxed inside the 1280×720 frame.
- Where a clip was shorter than its narration, the **last frame is held
  frozen** so the numbers stay readable while the voiceover explains them.
  No clip was sped up or slowed down.
- After recording, the workspace database was reset to clean seed data and
  the Flask server was stopped. Re-run `python3 app.py` and log in with any
  test login (password `demo1234`) to replay the scenario live.

## Narration — AI-generated, not Pranav's voice

- Voiceover is **AI narration** (Meta Shortwave TTS, default voice), read
  from `DEMO_SCRIPT.md` with numbers spelled out. It is **not Pranav
  speaking**. If he prefers his own voice, he can re-record just the
  voiceover against the same script and timings — the visuals and the
  section timings below stay valid.

## Sections (timestamps)

| Time | Section | What is shown |
|---|---|---|
| 0:00–0:26 | Intro | Admin dashboard, opening stock (FG 50 packets, flour 100 kg) |
| 0:26–1:08 | Steps 1–2: purchase + production run | Flour purchase 60 kg @ ₹45; run form (40 kg flour, 10.5 L oil, 1.2 kg spice, 188 good, 6 damaged, 9 cartons); stock page: flour **120 kg**, oil **19.5 L**, pouches **306**; finished goods **238** |
| 1:08–1:35 | Step 3: Retailer A order (mobile) | Salesman A on phone view orders 150 packets; order #1 **pending** admin approval |
| 1:35–2:29 | Steps 4–6: verify, invoice, pay, dispatch | Admin approves; tax invoice INV-2026-0001: ₹7,500 + ₹187.50 CGST + ₹187.50 SGST = **₹7,875**; payment ₹4,000 recorded, invoice shows due **₹3,875**; stock page: finished goods **88** |
| 2:29–3:03 | Step 7: Distributor B shortage | Salesman B (mobile) orders 120; flash + order list: "only 88 packets in stock, **short by 32**"; admin orders view shows status **shortage**; IGST note in narration |
| 3:03–3:34 | Step 8: variances | Production run card + reports page: yield **−6.0% FLAGGED**, oil **+5.0% FLAGGED** |
| 3:34–4:09 | Step 9: cost per packet | Run card: materials ₹4,055 + labour ₹1,200 + overhead ₹600 = ₹5,855 → **cost/packet ₹31.14** |
| 4:09–4:41 | Reports + audit trail | Monthly reports (sales register, GST summary, ageing), audit log |
| 4:41–5:05 | Roles, limits, close | Login screen (six demo logins), thank-you end card |

## Numbers checklist (all visible on screen)

- [x] Flour 120 kg, oil 19.5 L, pouches 306
- [x] Finished goods 238 after the run, 88 after dispatch
- [x] Yield −6% flagged, oil +5% flagged
- [x] Invoice ₹7,875 (₹7,500 + ₹187.50 CGST + ₹187.50 SGST)
- [x] Outstanding ₹3,875 (after ₹4,000 payment)
- [x] Shortage 32 (Distributor B; IGST if invoiced)
- [x] Cost per packet ₹31.14, margin ₹18.86

## Honest caveats

- The reports page also flags a **carton variance of −10%** (9 cartons used
  vs 10 standard). That is real app behaviour, not an error — the narration
  only calls out the yield and oil variances the task asks for.
- The stock page shows the flour weighted-average rate as **₹43.12/kg**
  (display rounding); the exact value is ₹43.125/kg, as stated in the README.
- The video was assembled from 10 recorded clips (one per section, plus two
  short scrolled stock views); cuts between sections are visible but the
  scenario runs in order with no skipped step.
