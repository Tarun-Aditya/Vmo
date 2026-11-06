.PHONY: dev up down seed eval test lint migrate
dev:      ; docker compose up --build
up:       ; docker compose up -d --build
down:     ; docker compose down
migrate:  ; docker compose exec api alembic upgrade head
seed:     ; docker compose exec api python /scripts/seed.py
eval:     ; docker compose exec api sh -c "python /evals/extraction_eval.py && python /evals/redline_eval.py"
test:     ; docker compose exec api pytest -q
lint:     ; docker compose exec api sh -c "ruff check . && black --check ."
