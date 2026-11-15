# Claude mode on the hotel corpus

Engine: Claude through the `claude_code` CLI (the logged-in subscription), Demo mode off.

## Full seed read by Claude, 2026-11-15 (United States corpus, 32 documents)

`python -m app.seed --hotel` with `LLM_PROVIDER=auto`, scored with `evals/pilot_eval.py` and `evals/hotel_redline_eval.py`.

| Measure | Claude | Offline rules |
|---|---|---|
| Field extraction | **455/457 = 99.6%** | 456/457 = 99.8% |
| Document metadata | 126/128 = 98.4% | 126/128 = 98.4% |
| Values and limits | 84/85 = 98.8% | 84/85 = 98.8% |
| Planted redline deviations found | 17/17 | 17/17 |
| Clean control draft, high/critical findings | 0 | 0 |
| Findings per draft | about 15 | about 7 |

The weakest field was "processes personal data" (25/31 on 2026-11-14). Claude read "to the extent the Supplier processes personal data ..."
as a statement that it does. The prompt now says conditional wording is a generic clause; it is 30/31. The remaining miss is a housekeeping
schedule whose staff "have access to guest data", which is a fair reading either way.

## Real hotel-world contracts (12 public-record documents, 54 labelled fields)

`python ../evals/real_hotel_eval.py` (see `data/real_hotel/README.md`). Raw output in `reports/real_hotel/`.

| | First sight | After the fixes these documents prompted |
|---|---|---|
| Claude | 44/55 = 80% | **52/54 = 96%** |
| Offline rules | 37/55 = 67% | 49/54 = 91% |

What changed for Claude: it now returns the supplier's name (used only when the name appears in the document word for word), and its prompt says how
to treat a blank in a template (no name, no start date), a start date stated in the term clause, option years, a city's state named only in its title,
and conditional personal-data wording. The "after" column is measured on the same documents the fixes were made from, so it is optimistic.

## Redline of the five vendor drafts

* Every failed playbook rule is in a Claude redline even when Claude did not raise it (it once missed a 180-day renewal notice).
* A clause the template already carries is not reported a second time as a library clause.
* A missing library clause is a finding only where the house requires it of that document; a spa supplier is not told it lacks food-safety clauses.
* The prompts speak for the configured customer; they used to name the original demo customer.

The findings that remain on the two vendor-paper drafts (24 each) are differences of substance from the house position: payment terms, warranties,
indemnities, insurance, IP, assignment. Whether a reviewer wants all of them has not been tested with a real reviewer.

One run each. Fictional and public documents, not a hotel group's own contracts.
