.PHONY: dev up down seed seed-pilot seed-offline eval test lint migrate docs showcase cuad cuad-full video
dev:      ; docker compose up --build
up:       ; docker compose up -d --build
down:     ; docker compose down
migrate:  ; docker compose exec api alembic upgrade head
docs:     ; docker compose exec api python -m app.docgen.generate
seed:     ; docker compose exec api python /scripts/seed.py
seed-pilot: ; docker compose exec api python -m app.seed --pilot
seed-offline: ; docker compose exec -e LLM_PROVIDER=offline api python /scripts/seed.py
eval:     ; docker compose exec api sh -c "python /evals/extraction_eval.py && python /evals/redline_eval.py && cd /evals && python ask_eval.py"
test:     ; docker compose exec -e LLM_PROVIDER=offline api sh -c "python /scripts/seed.py && pytest -q"   # tests need the deterministic offline-seeded data
lint:     ; docker compose exec api sh -c "ruff check . && black --check ."

showcase: ; docker compose up -d --build && docker compose exec api alembic upgrade head && docker compose exec api python -m app.seed --pilot   # clone -> running demo in one command
cuad:     ; cd backend && python ../evals/cuad_eval.py ../data/cuad/CUAD_v1 --split test --vmo   # real-contract accuracy on the bundled CUAD text (LLM_PROVIDER=offline for rules)
cuad-full: ; sh scripts/fetch_cuad.sh   # download the full CUAD including PDFs
video:    ; node scripts/demo_e2e.js reports/e2e   # records the end-to-end walkthrough (needs the app running and Playwright)
