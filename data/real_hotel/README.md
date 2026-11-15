# Real hotel-world contracts (public records)

Twelve real contracts of the kinds a hotel owner signs, published by the public bodies that are party to them. They are **not stored in this
repository**: `sh scripts/fetch_real_hotel.sh` downloads them into `data/real_hotel/docs/` from the links in `sources.json`. `labels.json` holds the
correct values for the fields that could be read with certainty (written down by reading each document; not expert labels).

Score the engine on them from `backend/`:

```
LLM_PROVIDER=offline python ../evals/real_hotel_eval.py     # the rules alone
python ../evals/real_hotel_eval.py                          # Claude (subscription CLI or API key)
```

## What is in the set

| File | What it is | Why it matters to a hotel owner |
|---|---|---|
| `hotel_mgmt_mdanderson.pdf` | Hotel management agreement for a hospital-owned hotel (112 pages, a bid template) | The owner's main contract: ten-year term, operating standards, budgets, what the manager may spend |
| `housekeeping_lucas_county.pdf` | Housekeeping and laundry service at hotels | A short services contract with a two-week exit for the buyer |
| `linen_michigan_fortcuster.pdf` | Linen exchange and laundry for a 244-bed lodging centre | Per-item laundry pricing, one year plus four option years |
| `elevator_hialeah_schindler.pdf` | Elevator maintenance (scanned, with handwritten strike-outs) | The manufacturer's own paper with the buyer's changes written over it |
| `elevator_miami_ok.pdf` | Elevator maintenance (a form with blanks) | The buyer's own short form; renewal is expressly not automatic |
| `elevator_berkeley_mo.pdf` | A city ordinance with the elevator agreement behind it | Contract terms buried in an approval document |
| `elevator_nixa.pdf` | Elevator "Gold Service Agreement" on the vendor's paper | 36 months, renews by itself month to month, no exit except for the vendor's breach |
| `hilton_colostate.pdf` | Master services contract between a university and a hotel | The hotel as supplier: automatic five-year renewal, termination for convenience |
| `pest_ocala.pdf` | Citywide pest control | Two years plus two optional years, exit for convenience |
| `pest_vendorregistry.pdf` | Pest control, general services contract | Five years from the last signature, 30 days' notice to exit |
| `hotel_shared_tech_overlandpark.pdf` | Shared technology services between a city-owned convention hotel and its convention centre (draft) | A multi-party operating agreement; read, not scored |
| `hotel_lodging_sandiego.pdf` | Hotel lodging and meeting services for a city | The hotel's group-sales paper inside the buyer's contract |

## What real contracts do that the fictional ones do not

* **Blanks.** Templates and bid forms leave the supplier's name and the start date empty (`[INSERT NAME]`, `as of the ___ day of April 2020`).
  The right answer is "not stated", not the nearest date or a role word.
* **The parties are introduced by role**: `("Contractor")`, `hereinafter called the "CONTRACTOR"`, `("TBS")`, with the legal form in between
  (`Massey Services, Inc, a Florida Corporation`).
* **Dates sit in the term clause, not the heading**: `effective for 36 months starting November 01, 2022`, `through and including January 26, 2025`.
  The date on the cover is a proposal, bid or resolution date.
* **Vendor paper**: an elevator company's agreement renews itself and gives the buyer no exit. This is the contract the product exists to catch.
* **Scans and mark-up**: handwritten strike-outs, initials and stamps survive in the text as noise.
* **Wrappers**: a council resolution or ordinance comes first, the contract after it.
* **One document can contradict itself**: the Michigan contract ends on 30 October on its cover and 31 October in its terms.

## Results (2026-11-14, 54 labelled fields)

| Engine | Before the fixes these documents prompted | After |
|---|---|---|
| Offline rules | 37/55 = 67% | 49/54 = 91% |
| Claude | 44/55 = 80% | 52/54 = 96% |

The "after" figures are on the same twelve documents the fixes were made from, so they overstate what a thirteenth document would get: the "before"
column is the honest first-sight number. Raw output: `reports/real_hotel/`. The fixes did not hurt the 133 public hold-out contracts (governing law there rose from 89% to 92%).
