# AGENTS.md — rules for any coding agent (Claude Code, Codex, Cursor, Copilot) and for humans

This is the canonical instruction file. `CLAUDE.md` imports it. Keep it short, current and true.

## 1. What this repo is
**Niyam**: a RAG Q&A app over RBI/SEBI circulars, plus a DevOps framework for the CSE 816 final project.
The **DevOps pipeline is the graded product**; the app is intentionally small.

## 2. Source-of-truth order (higher wins)
1. `context/SPEC.md` / `context/spec.pdf`: course spec (30 marks). **Never contradict it.**
2. `context/PRD.md`: requirements with IDs (FR-, DR-, AR-, IR-).
3. `context/ARCHITECTURE.md`: how it's built; decisions in §12.
4. `context/DATA_MODEL_AND_SCAFFOLDING.md`: schemas, folder layout, file skeletons.
5. `context/WHAT_WILL_BREAK.md`: known pitfalls. **Read §B before touching infra.**
6. This file.

If a request conflicts with 1–3, stop and say so; don't silently pick one.

## 3. Repo map
```
context/           planning documents (spec, PRD, architecture, data model, pitfalls)
docs/              documents written during the build (ADRs, HANDOFF.md, final report, evidence screenshots)
services/api/      FastAPI app, RAG pipeline, ingest CLI, tests (Python 3.12)
services/web/      nginx + static HTML/JS UI
data/corpus/       manifest.yaml + raw PDFs (real corpus)     data/fixtures/  3-doc CI corpus
eval/              golden.jsonl, thresholds.yaml, run_eval.py
ansible/           playbooks/ (site, deploy, rollback, ingest, teardown) + roles/ (8 roles, K8s manifests live in roles/*/templates)
infra/             logstash pipeline, ES index template, Kibana dashboards.ndjson (ELK manifests: ansible/roles/elk/templates)
scripts/           smoke, zero_downtime_check, load_test, demo helpers
Jenkinsfile        the CI/CD pipeline     docker-compose.yml (dev)     docker-compose.ci.yml (eval gate)
```

## 4. Commands
Run these inside Ubuntu (WSL) from the repo root.
```bash
make dev            # docker compose up: api, web (qdrant joins in P2; uses host Ollama)
make down           # stop the Compose stack
make test           # lint + unit tests inside Docker (same as CI)
make test-local     # unit tests in a managed local virtual environment
make lint           # ruff check + ruff format --check
make cluster-up     # start minikube and update the kubeconfig
make agent-install  # install and start the Ubuntu Jenkins agent service
make bootstrap TAG=<sha>  # ansible-playbook ansible/playbooks/site.yml
make deploy TAG=<sha>     # ansible-playbook ansible/playbooks/deploy.yml -e image_tag=<sha>
# Added by later milestones:
make eval           # P2: run eval/run_eval.py against the dev stack
make vault-reseed   # P4: re-run vault role (dev-mode Vault loses data on restart)
make rollback       # P5: ansible-playbook ansible/playbooks/rollback.yml
```

## 5. Hard rules (MUST / MUST NOT)
- **MUST NOT add tools outside the spec stack** (Argo CD, Prometheus, Grafana, OpenTelemetry, Helm charts for *our* app, Terraform, Kafka, Postgres, GitHub Actions) without a human-approved ADR. Third-party Helm charts (Vault) installed *by Ansible* are allowed.
- **MUST NOT commit secrets.** Secrets go in HashiCorp Vault (runtime) or `ansible/group_vars/all/vault.yml` encrypted with `ansible-vault`.
- **MUST NOT use the `:latest` tag** in any manifest, compose file or script that deploys. Tags are git short SHAs.
- **MUST keep one deploy path:** `ansible/playbooks/deploy.yml`. No `kubectl apply` in the Jenkinsfile or scripts.
- **MUST NOT put `replicas:` in the `niyam-api` Deployment template** (the HPA owns it).
- **MUST log JSON to stdout** only, using the schema in DATA_MODEL §4. Every line has `ts, level, service, app_version, event`. No `print()`.
- **MUST keep readiness independent of Ollama.**
- **MUST wrap Go-template Vault annotations in `{% raw %}…{% endraw %}`** inside Ansible Jinja templates.
- **MUST keep everything runnable on one 16 GB laptop.** New containers need a memory request and limit, and a line in ARCHITECTURE §11.
- **MUST keep Ansible tasks idempotent** (use modules, not `shell`, where a module exists; when `shell` is unavoidable, set `changed_when`).
- **MUST NOT weaken eval thresholds** to make a build pass. Fix the cause, or get human sign-off in the PR.

## 6. Coding conventions
- Python: ruff (line length 100), type hints everywhere, pydantic v2 models in `app/models/schemas.py`, settings via `pydantic-settings` in `app/config.py` (env prefix `NIYAM_`). Secrets are read from `*_FILE` paths.
- Tests: pytest. Unit tests mock Qdrant and Ollama. Integration tests are marked `@pytest.mark.integration` and need Compose.
- Prompts: versioned files `services/api/app/rag/prompts/v{N}.txt`. Changing behaviour = new file + bump `NIYAM_PROMPT_VERSION`. Never edit an old version in place.
- Ansible: roles `defaults/main.yml` hold every tunable; templates end in `.yaml.j2`; one K8s object per template.
- Shell scripts: `set -euo pipefail`, shellcheck clean.
- Commits: Conventional Commits (`feat(api): …`, `ci(jenkins): …`, `feat(ansible): …`), small and frequent, following "Git & commit protocol" in `CLAUDE.md`. Humans make every commit. **Both teammates commit every week.** It is graded in the viva.

## 7. Definition of done for any change
1. `make lint test` passes locally.
2. If the API behaviour or prompt changed: `make eval` passes thresholds.
3. If infra changed: `make bootstrap` (or the relevant role) runs twice; the second run is (near) `changed=0`.
4. Docs updated: if you changed a decision, port, env var, schema or command, update ARCHITECTURE/DATA_MODEL/this file in the **same PR**.
5. The demo script (PRD §10) still works. If you touched the pipeline, run the full push-to-deploy once.

## 8. Ownership (for review and viva)
| Area | Owner | Reviewer |
|---|---|---|
| Repo setup; P1 walking skeleton: api/web skeleton, Docker, Compose, Ansible roles `common`, `minikube`, `app`, base `Jenkinsfile`, smoke test | Teammate 1 | Teammate 2 |
| P2 RAG app: roles `ollama`, `qdrant`, `ingest`, corpus manifest + fixtures, embedder, `/search`, `/ask`, refusal, citations UI, feedback, documents | Teammate 1 | Teammate 2 |
| Golden eval set and `eval/run_eval.py` | Teammate 1 | Teammate 2 |
| P3: ELK in Kubernetes (`elk` role, `infra/`) + Kibana dashboard | Teammate 2 | Teammate 1 |
| P4: Vault + injector (including securing Qdrant), HPA + load test, zero-downtime check | Teammate 2 | Teammate 1 |
| P5: Jenkins eval-gate stage, Trivy, post-deploy verify, `mark_good`/rollback, Kibana release-quality panel | Teammate 2 | Teammate 1 |
| P6: demo rehearsal, report, backup recording | Shared | Each other |

Each teammate reviews the other's PRs. Both must be able to explain everything in the viva.

## 9. When to stop and ask a human
- A spec requirement seems impossible or ambiguous.
- A change needs a new tool, service, or more than about 500 MB of extra RAM.
- Anything touching Docker Hub credentials, the webhook relay, or deleting cluster/ELK data.
- Eval thresholds would need to change.
