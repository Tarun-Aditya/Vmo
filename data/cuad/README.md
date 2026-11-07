# CUAD v1 (public real-world contracts)

Included here so the real-contract accuracy results can be reproduced from a plain clone:

* `CUAD_v1/full_contract_txt/` — the 510 contracts as text
* `CUAD_v1/master_clauses.csv` — expert clause labels
* `CUAD_v1/index.csv` — our index: file, agreement type (folder in the original PDF set), and the **train/test split**
  (`md5(file name) % 10 < 7` = train; tuning used only train, test was never tuned on)
* `CUAD_v1/CUAD_v1_README.txt` — the dataset's own readme

Not bundled (large, not needed by the evals): the PDFs and `CUAD_v1.json`. Fetch everything with `scripts/fetch_cuad.sh`.

**Source and licence.** The Atticus Project, *Contract Understanding Atticus Dataset (CUAD) v1*,
https://zenodo.org/records/4595826, licensed **CC BY 4.0**. Redistributed unmodified with attribution.
Hendrycks, Burns, Chen, Ball, *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review*, NeurIPS 2021.

Run: `python evals/cuad_eval.py data/cuad/CUAD_v1 --split test` (add `--vmo` for the services/outsourcing/hosting agreement types,
`LLM_PROVIDER=offline` for the rules engine). CUAD is not VMO-shaped (many licence and distribution agreements); it measures
robustness on messy real text.
