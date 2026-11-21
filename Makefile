# Run these targets inside Ubuntu (WSL) from the repository root.
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

# Ansible ignores a config in a world-writable directory such as /mnt/c unless it is named here.
export ANSIBLE_CONFIG := $(CURDIR)/ansible/ansible.cfg

VENV ?= $(HOME)/.local/share/niyam-api-dev
VENV_STAMP := $(VENV)/.installed
API_REQUIREMENTS := services/api/requirements.txt services/api/requirements-dev.txt
PLAYBOOK := ansible-playbook -i ansible/inventory/hosts.ini
VAULT_FLAGS ?= --ask-vault-pass

.PHONY: help dev down test test-local lint bootstrap cluster-up deploy check-tag

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev: ## Build and run the local Compose stack
	docker compose up --build

down: ## Stop the local Compose stack
	docker compose down

test: ## Run lint and unit tests inside Docker, as CI does
	docker build -f services/api/Dockerfile --target test -t niyam-api-test:local .

$(VENV_STAMP): $(API_REQUIREMENTS)
	python3 -m venv "$(VENV)"
	"$(VENV)/bin/pip" install --quiet --disable-pip-version-check $(addprefix -r ,$(API_REQUIREMENTS))
	touch "$@"

test-local: $(VENV_STAMP) ## Run unit tests in a local virtual environment
	cd services/api && PYTHONDONTWRITEBYTECODE=1 "$(VENV)/bin/python" -m pytest -q -p no:cacheprovider

lint: $(VENV_STAMP) ## Check Python lint and formatting
	cd services/api && "$(VENV)/bin/ruff" check --no-cache . && "$(VENV)/bin/ruff" format --no-cache --check .

check-tag:
	@[[ "$(TAG)" =~ ^[0-9a-f]{7,40}$$ ]] || { echo "TAG must be a git SHA, for example: make $(firstword $(MAKECMDGOALS)) TAG=$$(git rev-parse --short=7 HEAD)" >&2; exit 2; }

bootstrap: check-tag ## Set up the whole platform: make bootstrap TAG=<sha>
	$(PLAYBOOK) ansible/playbooks/site.yml -e image_tag=$(TAG) --ask-become-pass $(VAULT_FLAGS)

cluster-up: ## Start the cluster and refresh the Jenkins kubeconfig
	$(PLAYBOOK) ansible/playbooks/site.yml --tags cluster --ask-become-pass $(VAULT_FLAGS)

deploy: check-tag ## Release one image tag: make deploy TAG=<sha>
	$(PLAYBOOK) ansible/playbooks/deploy.yml -e image_tag=$(TAG) $(VAULT_FLAGS)
