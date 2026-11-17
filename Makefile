.PHONY: dev up down seed seed-pilot seed-offline eval test lint migrate docs reference-docs showcase cuad cuad-full video demo-video presentation-video
dev:      ; docker compose up --build
up:       ; docker compose up -d --build
down:     ; docker compose down
migrate:  ; docker compose exec api alembic upgrade head
docs:     ; docker compose exec api python -m app.docgen.generate
reference-docs: ; cd backend && SCHEDULER_ENABLED=0 python ../scripts/gen_reference_docs.py   # on the host (backend installed, DATABASE_URL set or the Docker db on :5432): regenerate docs/reference/API.md and DATABASE.md
seed:     ; docker compose exec api python /scripts/seed.py
seed-pilot: ; docker compose exec api python -m app.seed --pilot
seed-hotel: ; docker compose exec api python -m app.seed --hotel
seed-offline: ; docker compose exec -e LLM_PROVIDER=offline api python /scripts/seed.py
eval:     ; docker compose exec api sh -c "python /evals/extraction_eval.py && python /evals/redline_eval.py && cd /evals && python ask_eval.py"
test:     ; docker compose exec -e LLM_PROVIDER=offline api sh -c "python /scripts/seed.py && pytest -q"   # tests need the deterministic offline-seeded data
lint:     ; docker compose exec api sh -c "ruff check . && black --check ."

showcase: ; docker compose up -d --build && docker compose exec api alembic upgrade head && docker compose exec api python -m app.seed --hotel   # clone -> running hotel demo in one command (data/hotel, corpus/hotel)
cuad:     ; cd backend && python ../evals/cuad_eval.py ../data/cuad/CUAD_v1 --split test --vmo   # real-contract accuracy on the bundled CUAD text (LLM_PROVIDER=offline for rules)
cuad-full: ; sh scripts/fetch_cuad.sh   # download the full CUAD including PDFs
video:    ; node scripts/demo_e2e.js reports/e2e   # records the end-to-end walkthrough (needs the app running and Playwright)
demo-video: ; node scripts/demo_storyboard.js reports/demo   # records the DEMO.md story (hotel data, SIMULATORS=1, app running): reports/demo/contractiq-demo.mp4
presentation-video: ; node scripts/presentation_storyboard.js reports/presentation/video   # records the leadership demo: the paper-to-rows page, then the product on the same rows
