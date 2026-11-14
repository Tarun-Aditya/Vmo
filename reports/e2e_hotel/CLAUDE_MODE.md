# Claude-mode measurement on the hotel corpus (32 documents)

## Redline of the five vendor drafts, 2026-11-14 (United States corpus)

Engine: Claude through the `claude_code` CLI, Demo mode off; each draft re-run with `POST /api/redline/{id}/rerun`
and scored with `evals/hotel_redline_eval.py`. Extraction was not re-run with Claude on this date.

| Measure | Claude | Offline rules |
|---|---|---|
| Planted redline deviations found | 17/17 | 17/17 |
| Clean control draft, high/critical findings | 0 | 0 |
| Findings per draft | about 15 | about 7 |
| Of those, high or critical (shown first in Review) | about 8 | about 6 |

What changed since the first measurement (16/17, about 17 findings per draft, later about 20 once the house clauses were in the templates):

* Every failed playbook rule is now in a Claude redline even when Claude did not raise it (the missed 180-day renewal notice).
* A clause the template already carries is no longer reported a second time as a library clause.
* A missing library clause is a finding only where the house requires it of that document: a rule decides where one exists
  (so a spa supplier is not told its contract lacks food-safety or payment-card clauses), otherwise only a clause rated high or critical.
* The prompts speak for the configured customer; they used to name the original demo customer.

The findings that remain on the two vendor-paper drafts (24 each) are differences of substance from the house position: payment terms,
warranties, indemnities, insurance, IP, assignment. Whether a reviewer wants all of them has not been tested with a real reviewer.

## Full seed with Claude, earlier measurement (before the changes above, mixed-country corpus)

| Measure | Claude | Offline rules |
|---|---|---|
| Field extraction | 451/457 = 98.7% | 98.2% then; 99.8% now |
| Document metadata | 126/128 = 98.4% | 98.4% |
| Values and limits | 82/85 = 96.5% | 98.8% now |

One run each, one corpus, fictional documents: this is not evidence about real contracts.
