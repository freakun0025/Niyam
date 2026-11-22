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
NGROK_ARCHIVE := https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
VAULT_PASS_FILE ?= $(HOME)/.niyam-vault-pass
VAULT_FLAGS ?= $(if $(wildcard $(VAULT_PASS_FILE)),--vault-password-file "$(VAULT_PASS_FILE)",--ask-vault-pass)

.PHONY: help dev down test test-local lint bootstrap cluster-up deploy check-tag agent-install relay-install

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

agent-install: ## Install and start the Ubuntu Jenkins agent service
	@test -s "$(HOME)/.niyam-jenkins-agent-secret" || { echo "Save the agent secret to ~/.niyam-jenkins-agent-secret first" >&2; exit 2; }
	install -D -m 0755 scripts/jenkins-agent.sh "$(HOME)/.local/bin/niyam-jenkins-agent"
	install -D -m 0644 scripts/niyam-jenkins-agent.service "$(HOME)/.config/systemd/user/niyam-jenkins-agent.service"
	systemctl --user daemon-reload
	systemctl --user enable niyam-jenkins-agent.service
	systemctl --user restart niyam-jenkins-agent.service
	loginctl enable-linger "$$(id -un)"

relay-install: ## Install and start the ngrok GitHub webhook tunnel
	@command -v ngrok >/dev/null || { mkdir -p "$(HOME)/.local/bin"; curl -fsSL "$(NGROK_ARCHIVE)" | tar -xz -C "$(HOME)/.local/bin" ngrok; }
	@mkdir -p "$(HOME)/.config/ngrok"
	@test -s "$(HOME)/.config/ngrok/ngrok.yml" || { w="$$(wslpath "$$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')")/ngrok/ngrok.yml"; test -s "$$w" && ln -sf "$$w" "$(HOME)/.config/ngrok/ngrok.yml"; } || { echo "Run: ngrok config add-authtoken <token>" >&2; exit 2; }
	install -D -m 0644 scripts/ngrok-webhook-policy.yml "$(HOME)/.config/niyam/ngrok-webhook-policy.yml"
	install -D -m 0755 scripts/webhook-relay.sh "$(HOME)/.local/bin/niyam-webhook-relay"
	install -D -m 0644 scripts/niyam-webhook-relay.service "$(HOME)/.config/systemd/user/niyam-webhook-relay.service"
	systemctl --user daemon-reload
	systemctl --user enable niyam-webhook-relay.service
	systemctl --user restart niyam-webhook-relay.service
