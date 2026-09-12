.PHONY: help venv test test-fast lint fmt up down golden clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

venv:          ## create the dev virtualenv
	python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"

test:          ## full suite, including the exhaustive 720x720 sweep
	.venv/bin/pytest -q

test-fast:     ## skip the exhaustive sweep
	.venv/bin/pytest -q -m "not exhaustive"

lint:          ## ruff check
	.venv/bin/ruff check engine tests

fmt:           ## ruff format
	.venv/bin/ruff format engine tests

golden:        ## regenerate frozen golden vectors (bump algorithm_version first!)
	.venv/bin/python -m tests.make_golden

run:           ## start the game (reuses existing data)
	./scripts/dev.sh

demo:          ## reset, seed a played round + a live one, and start
	./scripts/dev.sh --fresh

stop:          ## stop the api server
	@pkill -f 'uvicorn api.main' 2>/dev/null || true

arch:          ## verify the dependency arrows point inward
	.venv/bin/python tools/check_layering.py

up:            ## start postgres + valkey
	docker compose up -d

down:
	docker compose down

clean:
	rm -rf .pytest_cache .ruff_cache .hypothesis **/__pycache__
