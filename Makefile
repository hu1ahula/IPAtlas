.PHONY: install test run docker-up

install:
	uv sync

test:
	uv run pytest

run:
	uv run uvicorn app.main:app --reload

docker-up:
	docker compose up --build
