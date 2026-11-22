# PRD — Niyam: RBI/SEBI Circular Q&A Assistant with an LLMOps DevOps Pipeline

| | |
|---|---|
| **Course** | CSE 816 Software Production Engineering — Final Project (30 marks) |
| **Spec (source of truth)** | `context/spec.pdf` (text copy: `context/SPEC.md`). Spec beats this PRD on any conflict. |
| **Status** | Draft v1 — 21 Nov 2026 |
| **Team** | Two people. **Teammate 1:** app and foundation. **Teammate 2:** platform and release quality. Scope in §11. |
| **Product name** | **Niyam** (Hindi: "rule") |

---

## 1. One-paragraph summary

Niyam is a small web app where a user asks a question in plain English ("What is the cooling period for
digital lending loans?") and gets a short answer **with citations to the exact RBI/SEBI circular and page**.
It runs a Retrieval-Augmented Generation (RAG) pipeline on a small, locally hosted LLM. The app is
deliberately small; **the product being graded is the DevOps framework around it**:
every `git push` → Jenkins (via GitHub webhook) → tests + an LLM answer-quality gate → Docker images to
Docker Hub → Ansible roles deploy to Kubernetes with a zero-downtime rolling update → logs flow into ELK and
a Kibana dashboard shows what the app and each release are doing. Secrets live in HashiCorp Vault; the API
scales with HPA.

## 2. Why this project (scoring logic)

| Spec section | Marks | How Niyam earns it |
|---|---|---|
| Working project | 20 | Every mandatory item in spec §"Evaluation Expectations" implemented and demoable live (see §6 DR-1…DR-10). **This is the priority. Nothing else matters if this is "partially functional" (15).** |
| Advanced features | 3 | HashiCorp **Vault** (Agent Injector → pods), **Ansible roles** (8 roles), **K8s HPA** on the API. Live patching via rolling updates is covered under DR-9. |
| Innovation | 2 | **Eval-gated releases**: Jenkins runs a golden-question answer-quality test before pushing images and again after deploying, and **automatically rolls back** a release whose answers got worse. Results go to Kibana as a "Release quality" panel. |
| Domain-specific | 5 | Two listed domains at once: **Finance** (RBI/SEBI regulation) and **MLOps/AIOps** (LLM serving, retrieval, model/prompt versioning, quality gates). |

## 3. Users and problem

**Who is the product for (story for the report/viva):** compliance analysts, fintech developers and
finance students. They need to know what an RBI/SEBI circular says without reading 40-page PDFs, and they
need the source cited, because an uncited answer is useless in compliance work.

**Who it really has to satisfy:** the evaluator during a live demo and the individual viva. Every
requirement below traces either to the spec or to making that demo reliable.

## 4. Goals and non-goals

### Goals
- G1. Satisfy **every** mandatory spec item, automated end to end, demoable live on one laptop.
- G2. Earn all three "advanced feature" marks (Vault, Ansible roles, HPA) with real, working integrations rather than token ones.
- G3. One clearly explainable innovation (eval-gated release + auto-rollback).
- G4. A resume-worthy story: "LLM app + production-style DevOps pipeline".
- G5. Both members can explain every file (individual viva).

### Non-goals (explicitly out of scope)
- User accounts/login, chat history, streaming tokens, multi-turn conversation.
- Paid cloud, managed Kubernetes, paid LLM APIs.
- Tools not named in the spec (Argo CD, Prometheus/Grafana, OpenTelemetry, Helm charts for our own app,
  Terraform, Kafka). See `context/WHAT_WILL_BREAK.md` §C for why.
- OCR of scanned PDFs, Hindi-language support, legal-grade accuracy.

## 5. Functional requirements — the app

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| FR-1 | Ask a question (3–500 chars), get an answer ≤ ~200 words with numbered citations `[1]`, `[2]`. | Must | `POST /api/v1/ask` returns `answer` + ≥1 `citations[]` for in-scope questions. |
| FR-2 | Each citation shows regulator, circular number, title, issue date, page, a ≤300-char snippet, and the source URL. | Must | UI renders citation cards; links open the official PDF. |
| FR-3 | **Refusal:** if retrieval confidence is below threshold, reply with a fixed "not found in indexed circulars" message and **do not call the LLM**. | Must | Out-of-scope golden questions return `refused: true`. |
| FR-4 | Search-only mode: return top-k chunks without generation. Used by the UI "Sources only" toggle and by the HPA load test. | Must | `POST /api/v1/search` responds in < 1 s at p95 on the demo laptop. |
| FR-5 | Optional filters: regulator (RBI/SEBI) and year range. | Should | Filtered results only contain matching payloads. |
| FR-6 | Thumbs up/down feedback per answer. | Should | `POST /api/v1/feedback` → log event `feedback.received` visible in Kibana. |
| FR-7 | List indexed documents. | Should | `GET /api/v1/documents`. |
| FR-8 | **Version badge** in the UI footer showing the deployed git SHA and prompt version. | Must | It is how the evaluator *sees* "new changes visible on refresh" (spec item 2). |
| FR-9 | Disclaimer: "Unofficial. Not legal advice. Always check the source circular." | Must | Visible on every page. |
| FR-10 | Ingest pipeline: parse PDFs from `data/corpus/`, chunk, embed, upsert to the vector DB idempotently. | Must | Re-running ingest does not create duplicates; it runs as a K8s Job. |

**Corpus:** 30–60 **text-based** (not scanned) RBI Master Directions/Circulars and SEBI circulars, about 20 MB,
listed in `data/corpus/manifest.yaml`. A 3-document fixture corpus (`data/fixtures/`) is used in CI.

## 6. DevOps requirements — mapped 1:1 to the spec

| ID | Spec text | Requirement | Acceptance (demo-observable) |
|---|---|---|---|
| DR-1 | Git and GitHub | Monorepo on GitHub, protected `main`, one branch per milestone and owner, PRs merged with a merge commit and reviewed by the other teammate when possible, Conventional Commits, **both teammates committing throughout** (Teammate 1: foundation and app; Teammate 2: platform and release quality). | `git shortlog -sn` shows both teammates, spread across weeks. |
| DR-2 | GitHub Hook Trigger for GITScm Polling | GitHub webhook → Jenkins job with `githubPush()` trigger. Fallback: Poll SCM every 2 min. | Push → build starts within ~10 s (webhook) or 2 min (fallback). |
| DR-3 | Jenkins pipelines | Declarative `Jenkinsfile` in repo, with stages: Init → Unit tests → Build → Eval gate → Scan → Push → Deploy → Verify, and auto-rollback in `post { failure }`. | Stage view green; failing a stage stops the release. |
| DR-4 | Running automated tests | pytest unit tests (run inside a Docker `test` build target) + integration tests + RAG eval gate on Docker Compose. | A failing test fails the build. |
| DR-5 | Docker | Multi-stage Dockerfiles for `api` and `web`; non-root; images tagged with git short SHA. **Never deploy `:latest`.** | `docker images` shows `<sha>` tags. |
| DR-6 | Docker Compose | (a) `docker-compose.yml` local dev stack; (b) `docker-compose.ci.yml`, the throwaway environment Jenkins uses for integration tests + the eval gate. | Both come up with one command; Jenkins logs show the eval stack starting and stopping. |
| DR-7 | Pushing images to Docker Hub | Jenkins pushes `DOCKERHUB_NS/niyam-api:<sha>` and `niyam-web:<sha>` using Jenkins credentials. | Tags visible on hub.docker.com. |
| DR-8 | Ansible playbooks → deploy to target | `site.yml` (bootstrap everything) and `deploy.yml` (release a tag), built from **roles**. K8s manifests are Jinja2 templates inside roles. | `ansible-playbook deploy.yml -e image_tag=<sha>` is the only deploy path, both for Jenkins and for humans. |
| DR-9 | Kubernetes, plus "changes visible on refresh" and live patching | Minikube cluster, `RollingUpdate maxUnavailable: 0, maxSurge: 1`, readiness probes, preStop drain; `index.html` served `no-cache`. | `scripts/zero_downtime_check.sh` shows **0 failed requests** during a deploy; a browser refresh shows the new SHA. |
| DR-10 | ELK + Kibana dashboard | JSON logs → Filebeat DaemonSet → Logstash → Elasticsearch → Kibana, **all in the cluster (ns `logging`)**, with Kibana at `kibana.niyam.local` and dashboard **"Niyam — App & Releases"** with ≥8 panels (see ARCHITECTURE §7). | Asking a question in the UI shows up in Kibana within ~10 s. |

## 7. Advanced feature requirements

| ID | Requirement | Acceptance |
|---|---|---|
| AR-1 Vault | HashiCorp Vault in-cluster with KV v2, Kubernetes auth, per-service policies. API, ingest Job and Qdrant receive the Qdrant API key via **Vault Agent Injector** (file at `/vault/secrets/qdrant`). Elasticsearch, Logstash and Kibana get their passwords the same way (injected files in ns `logging`). Ansible-side bootstrap values are encrypted with `ansible-vault`. | `kubectl get secret -n niyam` shows **no** app secrets; `kubectl exec` shows the injected file; `git grep` finds no plaintext secrets. |
| AR-2 Ansible roles | Roles: `common`, `minikube`, `vault`, `elk`, `ollama`, `qdrant`, `app`, `ingest`. Each role is idempotent: a second run reports `changed=0` (or close to it). | A second `site.yml` run is near-idempotent. |
| AR-3 HPA | HPA on `niyam-api`: min 2, max 4, CPU target 60%. Embeddings run **inside** the API pod, so search load really uses CPU. | `scripts/load_test.sh` on `/search` → replicas go 2→3+ and back down. |
| AR-4 Live patching | Covered by DR-9 (rolling update without downtime). | As DR-9. |

## 8. Innovation requirement

| ID | Requirement | Acceptance |
|---|---|---|
| IR-1 Pre-release eval gate | In CI, run `eval/golden.jsonl` against the **freshly built image** on Compose with fixture data. Thresholds live in `eval/thresholds.yaml`. If any metric is below its threshold, the build fails before the push. | Demo: push a deliberately bad prompt or a bad chunking change → build fails at "Eval gate" with a readable metric table. |
| IR-2 Post-deploy verify + auto-rollback | After deploy, check `/version == <sha>` and run a 5-question live eval through the ingress. On failure, run `rollback.yml` (redeploys `last_good_tag` from ConfigMap `niyam-release`). | Demo: a change that passes CI but breaks live config → it is rolled back automatically and the old SHA is serving again. |
| IR-3 Release quality in Kibana | Every eval run emits an `eval.result` log event (sha, metrics, pass/fail). | Kibana panel shows quality per release. |

## 9. Non-functional requirements

| Area | Target |
|---|---|
| Latency (demo laptop, CPU LLM) | `/search` p95 < 1 s; `/ask` p95 < 20 s (generation capped at 256 tokens). |
| Availability during deploy | 0 failed requests in the zero-downtime check. |
| Resources | Whole stack runs on **one 16 GB RAM, 4+ core laptop**. Demo machine: Windows 11 + Ubuntu 24.04 on WSL2 (ARCHITECTURE §3.1). Budget in ARCHITECTURE §11. |
| Security | No plaintext secrets in git or K8s Secrets for app credentials; containers run as non-root; Trivy blocks CRITICAL fixable CVEs. |
| Observability | Every request has a `request_id`; every log line carries `app_version`; logs are searchable in Kibana within 10 s. |
| Reproducibility | `make bootstrap` on a clean machine (with prerequisites installed) brings up everything; a README lists the prerequisites. |

## 10. Demo script (doubles as acceptance test)

1. Show the architecture slide and the Kibana dashboard (yesterday's data already present).
2. Open `http://niyam.local`, ask 2 questions (one in scope, one out of scope → refusal). Show citations.
3. Start `scripts/zero_downtime_check.sh` in a terminal.
4. Change a visible UI string plus a prompt tweak, then `git commit && git push`.
5. Jenkins starts from the webhook. Walk through the stages, including the eval gate result table.
6. Images appear on Docker Hub; Ansible deploys; pods roll one by one (`kubectl get pods -w`).
7. Zero-downtime check prints `0 failed`. Refresh the browser → new text and new SHA in the footer.
8. Kibana: the new `app_version` appears, the request rate holds steady, and the eval panel shows the new release.
9. HPA: run `scripts/load_test.sh` → `kubectl get hpa -w` scales up.
10. Vault: show the injected secret file and that no K8s Secret holds it; show the Vault UI policy.
11. **Innovation:** push a known-bad prompt → the eval gate fails → no push, no deploy. (Have a pre-recorded rollback run as backup.)

## 11. Milestones (spec gives no dates; ask faculty for the demo date and fill it in)

Assume ~2.5 weeks if the demo window matches last year's (2nd week of December).

| Phase | Outcome | Owner | Target |
|---|---|---|---|
| P0 Setup | Repo, Docker Hub, Jenkins on host, minikube, ngrok/smee for webhook, Ollama on host | Teammate 1 | Day 1–2 |
| **P1 Walking skeleton** | api/web skeleton, Docker, Compose, base Ansible roles (`common`, `minikube`, `app`), base Jenkinsfile and smoke test going **push → Jenkins → Docker Hub → Ansible → K8s** end to end | Teammate 1 | **Day 3–5. This protects the 20 marks.** |
| P2 RAG app | `ollama`, `qdrant` and `ingest` roles, corpus manifest + fixtures, embedder, `/search`, `/ask`, refusal, citations UI, feedback, documents, tests, golden eval set and `eval/run_eval.py` | Teammate 1 | Day 4–9 |
| P3 ELK | `elk` role: ES StatefulSet, Logstash, Kibana + Ingress, Filebeat DaemonSet, users, index template, Kibana dashboard | Teammate 2 | Day 6–10 |
| P4 Advanced | Vault + injector (including securing Qdrant), HPA + load test, zero-downtime check | Teammate 2 (the app already reads the secret file) | Day 9–12 |
| P5 Release gate | Jenkins eval-gate stage, Trivy scan, post-deploy verify, `mark_good`/rollback, Kibana release-quality panel | Teammate 2 (uses Teammate 1's `eval/run_eval.py`) | Day 10–14 |
| P6 Hardening | Demo rehearsal ×3, backup screen recording, report, viva prep (`ARCHITECTURE_ESSENTIAL.md`) | Shared | Last 3 days |

Each teammate reviews the other's PRs, and both must be able to explain everything in the viva.

## 12. Open questions

1. Final demo date and report format/length (the spec is silent).
2. ~~Team size~~ **Resolved:** two teammates (see §11).
3. Does "Vault" mean HashiCorp Vault or `ansible-vault`? **We do both** to be safe (see WHAT_WILL_BREAK §A).
4. ~~Where does ELK run?~~ **Resolved:** inside Kubernetes (ns `logging`). See ARCHITECTURE §3 and ADR-2.
5. Is a public Docker Hub repo OK? (Private repos need an imagePullSecret.)

## 13. Success criteria (definition of done for the project)

- [ ] Demo script §10 runs start to finish **three times in a row** without manual fixes.
- [ ] Every DR/AR/IR row has its acceptance evidence screenshot in `docs/report/evidence/`.
- [ ] Both members can whiteboard the architecture and explain the Jenkinsfile, one Ansible role, the HPA and the Vault flow without notes.
- [ ] Backup screen recording of the full pipeline run exists.
