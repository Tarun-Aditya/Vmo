# Claude-mode measurement on the hotel corpus (32 documents)

Engine: Claude through the `claude_code` CLI, Demo mode off, full seed of `data/hotel` (about 5 minutes).
Scored against `data/hotel/labels_hotel.json` with `evals/pilot_eval.py`; redlines with `evals/hotel_redline_eval.py`.

| Measure | Claude | Offline rules |
|---|---|---|
| Field extraction | 451/457 = 98.7% | 98.2% |
| Document metadata | 126/128 = 98.4% | 98.4% |
| Values and limits | 82/85 = 96.5% | not recorded |
| Planted redline deviations found | 16/17 | 16/17 |
| Clean control draft, high/critical findings | 0 | 0 |
| Findings per draft | about 17 | about 7 |

Weakest field: `processes_personal_data` (26/31).
Claude finds the same planted deviations as the rules but reports about twice as many findings per draft, mostly
differences from the standard that were not planted. Whether those are useful or noise has not been reviewed.
One run, one corpus, fictional documents: this is not evidence about real contracts.
