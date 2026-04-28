.PHONY: setup install auth up down status logs key models systemd clean test

PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

# Default: friendly one-command journey.
.DEFAULT_GOAL := setup

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip wheel
	$(BIN)/pip install -e .

install: $(BIN)/python
	bash scripts/cloudflared-install.sh
	@echo "✅ install done. Next: 'make setup' (or 'make auth' && 'make up')."

setup: $(BIN)/python
	$(BIN)/c2p setup

auth:
	npx --yes copilot-api@latest auth

up:
	$(BIN)/c2p start

down:
	$(BIN)/c2p stop

status:
	$(BIN)/c2p status

logs:
	$(BIN)/c2p logs --tail 50 --follow

key:
	@echo 'usage: ./bin/c2p key add --name <label>'

models:
	$(BIN)/c2p models

systemd:
	bash scripts/install-systemd.sh

clean:
	rm -rf $(VENV) data __pycache__ src/*.egg-info build dist

test:
	$(BIN)/pytest -q
