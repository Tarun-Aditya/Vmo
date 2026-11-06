.PHONY: dev up down seed seed-offline eval test lint migrate docs
dev:      ; docker compose up --build
up:       ; docker compose up -d --build
down:     ; docker compose down
migrate:  ; docker compose exec api alembic upgrade head
docs:     ; docker compose exec api python -m app.docgen.generate
seed:     ; docker compose exec api python /scripts/seed.py
seed-offline: ; docker compose exec -e LLM_PROVIDER=offline api python /scripts/seed.py
eval:     ; docker compose exec api sh -c "python /evals/extraction_eval.py && python /evals/redline_eval.py && cd /evals && python ask_eval.py"
test:     ; docker compose exec -e LLM_PROVIDER=offline api sh -c "python /scripts/seed.py && pytest -q"   # tests need the deterministic offline-seeded data
lint:     ; docker compose exec api sh -c "ruff check . && black --check ."
