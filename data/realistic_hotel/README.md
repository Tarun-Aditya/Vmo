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

`src/*.md` are the sources; `labels.json` holds the values stated in each document (including both signatories); `sources.json` the category and property.

**Use them**
* Score the engine: `REAL_SET=realistic_hotel python ../evals/real_hotel_eval.py` (from `backend/`; `LLM_PROVIDER=offline` for the rules, unset for Claude).
* Add them to a running hotel demo: `python ../scripts/load_realistic_hotel.py` (from `backend/`, hotel environment). A re-seed removes them again,
  because the demo's walkthrough and Ask evals count the seeded portfolio.
* `backend/tests/test_realistic_contracts.py` pins every labelled field.

**Result (offline rules, 2026-11-15):** 72% of labelled fields when first written, 100% (60/60, signatories included) after the fixes they prompted.
They were written by the same author as the fixes, so they show the engine reads this kind of paper; they are not an independent test. Claude has not been
run on them (no Claude access in the session that wrote them).
