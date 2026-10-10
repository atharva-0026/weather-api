.PHONY: help install redis run test docker log

help:  ## List available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	pip install -r requirements.txt

redis:  ## Start a local Redis in the background (needs redis-server)
	redis-server --daemonize yes

run:  ## Run the API with auto-reload at http://localhost:8000/ui
	uvicorn main:app --reload --port 8000

test:  ## Run the test suite (needs Redis on localhost:6379)
	REDIS_URL=$${REDIS_URL:-redis://localhost:6379/0} OPENWEATHER_API_KEY=$${OPENWEATHER_API_KEY:-test_key} python -m pytest -q

docker:  ## Build and run the full stack with Docker Compose
	docker compose up --build

log:  ## Run the daily weather logger once against a running API
	python daily_log.py
