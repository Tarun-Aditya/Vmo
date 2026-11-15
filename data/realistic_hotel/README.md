# Five realistic hotel supplier contracts (fictional)

Written on 2026-11-15 to read like the contracts a US hotel owner actually signs: supplier paper and owner paper, order forms, rate tables, service levels,
insurance schedules, conformed signatures (`/s/`), exhibits. Every company and person is fictional; addresses and phone numbers are made up (555 numbers,
`.example` domains). The statutes cited are real US laws. The documents are free to use, so they are committed with the repository, unlike the public
contracts in `data/real_hotel`.

| File | What it is | Hotel | What makes it realistic |
|---|---|---|---|
| `docs/northshore_food_supply.pdf` | Prime-vendor food distribution agreement | All six | Cost-plus mark-up table, 80% volume commitment, fill-rate credits, recalls, rebate pass-through, audit right, 90-day non-renewal notice |
| `docs/adirondack_hvac_maintenance.docx` | HVAC, chiller, boiler and kitchen-refrigeration maintenance | Lakeside Resort | Equipment schedule, response times by priority (4 h / 8 h / next day), labour rates, refrigerant rules, **notice to stop renewal due 2 Dec 2026** |
| `docs/yieldline_rms_subscription.pdf` | Revenue-management software: order form + subscription terms + SLA + data processing addendum | All six | Per-property pricing, non-cancellable fees, 99.5% uptime credits, guest personal data, a separate higher cap for data breaches |
| `docs/keystone_valet_parking.docx` | Valet parking and garage management | Harbor Hotel | Management fee + reimbursed payroll + incentive, vehicle damage, garage-keepers insurance, **no liability cap**, **ends 31 Dec 2026, does not renew** |
| `docs/prairie_waste_services.pdf` | Waste hauling and recycling (the hauler's own form) | Airport Inn | 36-month evergreen renewal with a 180-to-90-day cancellation window, **window already missed (1 Sep 2026)**, liquidated damages, unilateral price increases |

**The folder** (`folder.json`, read with Admin → Pipeline → *Demo sample folder*) adds a cleaning contractor's paper so linking and change detection show:

| File | What it is | What it shows |
|---|---|---|
| `docs/meridian_nda.docx` | Mutual NDA, signed before the work started | Expires 17 Nov 2026; "may end this Agreement on 30 days' notice" |
| `docs/meridian_msa.pdf` | Master services agreement (contract cleaning), all hotels | 2x fees cap, 45-day payment, 90-day non-renewal notice |
| `docs/meridian_sow_harbor.pdf` | Statement of Work No. 1, Harbor Hotel | Linked under the master agreement; start date only in a table row |
| `docs/meridian_sow_midtown.docx` | Statement of Work No. 2, Midtown Suites | Linked under the master agreement; hourly rates with an estimate |
| `docs/meridian_amendment_1_scan.pdf` | Amendment No. 1, **an image-only scan** | Read by OCR; changes the master agreement's payment terms (30 days) and end date (2029) |
| `Northshore food supply - signed copy.pdf` | A byte-for-byte copy of the food contract | Caught as a duplicate, not stored twice |

`src/*.md` are the sources; `labels.json` holds the values stated in each document (including both signatories); `sources.json` the category and property.

**Recorded results for Demo mode.** `recorded.json` holds the terms extracted from each sample document and the answers to the questions in
`demo_questions.json`, keyed by content fingerprint; Demo mode replays them (`backend/app/recorded.py`). Re-record with Claude:
`python ../scripts/record_demo.py` from `backend/`, Demo mode off. The committed file was recorded with the offline engine.

**Use them**
* Score the engine: `REAL_SET=realistic_hotel python ../evals/real_hotel_eval.py` (from `backend/`; `LLM_PROVIDER=offline` for the rules, unset for Claude).
* Add them to a running hotel demo: `python ../scripts/load_realistic_hotel.py` (from `backend/`, hotel environment). A re-seed removes them again,
  because the demo's walkthrough and Ask evals count the seeded portfolio.
* `backend/tests/test_realistic_contracts.py` pins every labelled field.

**Result (offline rules, 2026-11-15):** the five core contracts: 72% of labelled fields when first written, 100% after the fixes they prompted; with the folder's five documents, 80/80 scored fields (signatories are checked by `backend/tests/test_realistic_contracts.py`).
They were written by the same author as the fixes, so they show the engine reads this kind of paper; they are not an independent test. Claude has not been
run on them (no Claude access in the session that wrote them).
