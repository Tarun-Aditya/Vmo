#!/usr/bin/env sh
# Download the FULL CUAD v1 (510 contracts as PDF and text, expert labels, CC BY 4.0) next to the bundled text subset.
# The repo already contains the plain-text contracts, master_clauses.csv and index.csv in data/cuad/CUAD_v1, which is all the evals need
# (except `--pdf`, which reads the PDFs). Source: https://zenodo.org/records/4595826
set -e
DEST="${1:-data/cuad/full}"
mkdir -p "$DEST"
curl -L -o "$DEST/CUAD_v1.zip" "https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1"
unzip -q -o "$DEST/CUAD_v1.zip" -d "$DEST"
echo "Full CUAD in $DEST (use: python evals/cuad_eval.py $DEST/CUAD_v1 --pdf --split test)"
