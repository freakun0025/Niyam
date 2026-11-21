# CLAUDE.md

@AGENTS.md

The file above holds the shared rules for every agent; they all apply. Below are Claude Code–specific additions only.

## Before you start any task
- Read the PRD row(s) the task maps to (`docs/PRD.md`, IDs like DR-9, AR-3) and say which ones you're implementing.
- For anything in `ansible/`, `infra/`, `Jenkinsfile` or K8s templates: read `docs/WHAT_WILL_BREAK.md` §B first and name which pitfalls apply.
- For multi-file or infra changes, use plan mode and show the plan before editing.

## How to work in this repo
- Prefer editing existing files over creating new ones. Follow the tree in `docs/DATA_MODEL_AND_SCAFFOLDING.md` §8 exactly. Don't invent new top-level folders.
- Implement in thin vertical slices that keep the pipeline green (the walking skeleton first: PRD §11 P1).
- After code changes, run `make lint test`. After prompt/RAG changes, also run `make eval` and paste the metrics table in your summary.
- After Ansible changes, run the affected role twice and report the `changed=` count of the second run.
- You cannot see the evaluator's screen. When you finish infra work, list the exact commands a human should run to verify it visually (kubectl / Kibana / browser).

## Things Claude tends to get wrong here (check yourself)
- Adding `replicas:` back to the api Deployment, or using `image: …:latest`.
- Writing `{{ .Data.data.x }}` Vault templates in `.j2` files without `{% raw %}`.
- Making `/readyz` call Ollama.
- Using `print()` or unstructured logging instead of `app/logging.py`.
- Generating Kibana dashboards by hand as JSON. Build them in the Kibana UI, export to `infra/kibana/dashboards.ndjson`, commit.
- Proposing Prometheus/Grafana/Argo/OTel "improvements". Out of scope (AGENTS §5).
- Lowering `eval/thresholds.yaml` to get green.

## Useful subagent splits
- "Explore" agent: find every place a setting is used (e.g. `NIYAM_QDRANT_URL`) before renaming.
- Separate review pass on any Jenkinsfile/Ansible diff, run against WHAT_WILL_BREAK §B, before declaring done.

## Response style for this repo
End each task with: what changed (files), how you verified it (commands + results), the PRD IDs advanced, and any new risk to add to WHAT_WILL_BREAK.
