# WHAT WILL BREAK — spec gaps, technical failure points, over-engineering, cut list

Read before planning each phase. Each item: **symptom → cause → prevention → viva fallback**.

---

## A. Gaps and traps in the spec document itself (and how we interpret them)

| # | Spec text | The problem | Our interpretation / mitigation |
|---|---|---|---|
| A1 | "Partially functional … 15 marks" vs "Fully functional … 20" | **5 marks hinge on the live demo working.** That's worth more than innovation (2) and advanced features (3) combined. | Walking skeleton first (PRD P1). Freeze features 3 days before the demo. Rehearse 3 times. Keep a backup recording. |
| A2 | "GitHub Hook Trigger for GITScm Polling" | GitHub can't reach `localhost:8080` on a laptop behind campus NAT. | Webhook through **smee.io** (no account) or **ngrok**. Fallback: Poll SCM `H/2 * * * *`. Mention both in the report. |
| A3 | "Deploying the Docker images to a target deployment system" | Not defined. Is a laptop minikube "a target"? | Yes: Kubernetes (minikube) is the target; Ansible is the deploy mechanism. State it explicitly in the report. |
| A4 | "Upon refreshing the application, the new changes should be visible seamlessly" | Browser cache, `:latest` tags and slow rollouts all make "refresh" show the **old** version. | SHA tags, `index.html` no-cache, `?v=SHA` assets, a **visible version footer**, and wait for `rollout status` before saying "refresh". |
| A5 | "Use tools like Vault" | Ambiguous: HashiCorp Vault or `ansible-vault`? Evaluators differ. | **Both:** HashiCorp Vault for runtime app secrets (main claim), `ansible-vault` for Ansible bootstrap vars. Costs about 30 minutes extra. |
| A6 | "Live patching" | In Linux, "live patching" means kernel patching (kpatch). Here it clearly means zero-downtime app updates. | Rolling update + readiness + preStop, **proved** by `zero_downtime_check.sh` showing 0 failures. Say "live patching = zero-downtime rolling update" in the report. |
| A7 | "Usage of Vault, Roles in Ansible, and Kubernetes HPA: 3 Marks" | Probably all-or-nothing in practice. One missing piece may cost all 3. | Treat all three as Must (PRD AR-1…3). |
| A8 | "Domain-specific … instead of generic full-stack or web applications" | Niyam *has* a web UI. An evaluator may see "a web app". | Lead the demo and report with **Finance + LLMOps**: regulatory corpus, model/prompt versioning, retrieval quality gates. The UI is just the window. |
| A9 | "ELK Stack" listed; "equivalent tools … if justified" | Tempting to swap in Loki/Grafana (lighter). That risks the evaluator's checklist. | Use real ELK (Elasticsearch, Logstash, Kibana + Filebeat), deployed in the cluster next to the app. |
| A10 | No deadline, team size, report format or repo rules | Planning blind. | Ask the faculty/TA this week (PRD §12). Assume team of 2, demo mid-December. |
| A11 | "Running automated tests" | A token `assert True` test is a known viva trap. | Real unit tests (chunker, refusal, citation parsing, schema validation) + an integration test + the eval gate. |

## B. Technical failure points (ranked by likelihood × damage)

| # | Symptom | Cause | Prevention | Fallback |
|---|---|---|---|---|
| B1 | Pods can't reach Ollama (`ConnectError`) | Ollama binds `127.0.0.1` by default; firewall | `OLLAMA_HOST=0.0.0.0` in a systemd override; `ufw allow from 192.168.49.0/24 to any port 11434`; Endpoints IP set by the `ollama` role | `/search` still works; demo `/ask` from a local compose stack |
| B2 | Jenkins can't `kubectl` / `ansible` → "unable to connect" or cert errors | Kubeconfig belongs to your user, Jenkins runs as `jenkins`; minikube certs referenced by path | `minikube config set embed-certs true` **before** `minikube start`; `common` role copies the kubeconfig to `/var/lib/jenkins/.kube/config` (0600) | Run the deploy stage manually in the viva and explain |
| B3 | Jenkins `docker: permission denied` | `jenkins` user not in the `docker` group | `usermod -aG docker jenkins && systemctl restart jenkins` (in the `common` role) | — |
| B4 | Elasticsearch pod crash-loops or is OOMKilled | `vm.max_map_count` too low (the minikube docker node shares the host kernel); memory limit ≈ heap | `node.store.allow_mmap: false` in the ES config (removes the sysctl need); heap 1g with limit 2Gi; `fsGroup: 1000` so ES can write its PVC | `kubectl logs -n logging elasticsearch-0`; re-run the `elk` role |
| B5 | ES 8 refuses connections / TLS errors | Security on by default with auto TLS | ES env: `xpack.security.enabled=true`, `xpack.security.http.ssl.enabled=false`, `xpack.security.transport.ssl.enabled=false`, `discovery.type=single-node`; `ELASTIC_PASSWORD_FILE` from the Vault injector | Disable security for the demo and say so honestly |
| B6 | Laptop freezes or OOM kills during the demo | RAM budget (ARCH §11) exceeded | **docker driver** (memory is a cap, not reserved); ES heap 1g, Logstash 512m; close the IDE; lite mode for small laptops (ARCH §11) | Pre-recorded video |
| B7 | Refresh shows the old version | `:latest` tag / `IfNotPresent` / browser cache / refreshed before rollout finished | AGENTS §5 rules; footer shows the SHA; wait for `rollout status` | Hard refresh; show `kubectl get pods -L version` |
| B8 | HPA shows `<unknown>/60%` | metrics-server addon off, or no CPU requests | `minikube addons enable metrics-server`; requests in the template | — |
| B9 | HPA never scales | Load sent to `/ask` (I/O bound) | Load-test `/search` with `hey -z 60s -c 20` | Temporarily lower the target to 30% for the demo (and say so) |
| B10 | Replica count jumps back to 2 after every deploy | `replicas:` in the Deployment fights the HPA | Omit `replicas` (AGENTS §5) | — |
| B11 | Ansible template error `'Data' is undefined` | Vault Go templates `{{ … }}` parsed by Jinja | `{% raw %}…{% endraw %}` | — |
| B12 | New pods stuck `Init:0/1` | Vault dev mode lost data after a restart; K8s auth role or policy missing | `make vault-reseed`; `deploy.yml` always runs the `vault` role first (fast, idempotent) | — |
| B13 | 504 Gateway Timeout on `/ask` | nginx ingress default 60s timeout vs CPU LLM | `proxy-read-timeout: "120"`; `num_predict: 256`; model ≤ 1.5B | Show `/search` + a cached answer |
| B14 | Eval gate takes 15+ minutes | Running every golden question through a CPU LLM | All questions retrieval-only; generation subset of 8; `OLLAMA_KEEP_ALIVE=30m` so the model stays loaded | Reduce the subset to 5 |
| B15 | Flaky eval → random red builds | LLM non-determinism | `temperature 0.1`, `seed 42`; gate on retrieval metrics + citation presence + refusal (deterministic); keyword recall threshold with margin | Re-run build once; if flaky twice, fix the question |
| B16 | Webhook works at home, not on campus | Relay blocked / changed URL (ngrok free URL changes on restart) | smee.io stable channel URL, or ngrok reserved domain; Poll SCM fallback always configured | "Build Now" + explain |
| B17 | Docker Hub push/pull slow or rate-limited on campus Wi-Fi | ~700 MB api image; anonymous pull limits | Layer order: deps → model download → code (only the last layer changes); `docker login` inside minikube; public repos | Phone hotspot; pre-pull |
| B18 | `fastembed` downloads the model at runtime → slow start / offline failure | Model not baked into the image | Download in the Dockerfile `RUN` step into `/models`; `NIYAM_EMBED_CACHE=/models` | — |
| B19 | Filebeat ships nothing | Missing RBAC (can't read pod metadata); wrong log paths; namespace filter typo; Logstash not Ready yet | ClusterRole for pods/namespaces/nodes; `logstash.logging.svc:5044`; check `kubectl logs -n logging ds/filebeat` | `kubectl logs` + explain |
| B20 | Kibana shows `message` as one big string | Logstash `json` filter missing, or the app logs non-JSON lines | `json { target => "app" }`; ruff rule banning `print`; uvicorn access log routed through the JSON logger | — |
| B21 | Kibana dashboard and old logs gone after `minikube delete` | Saved objects and logs live on the ES PVC inside the minikube node | Export to `infra/kibana/dashboards.ndjson`; `elk` role imports it on every run | — |
| B22 | Ingest creates duplicate chunks | Random point IDs | `uuid5(doc_id + ":" + chunk_index)` point IDs (DATA_MODEL §2) | Delete the collection, re-ingest |
| B23 | Ingest Job name conflict on redeploy | Jobs are immutable | Job name `niyam-ingest-<sha8>`; `ttlSecondsAfterFinished: 600` | `kubectl delete job` |
| B24 | Scanned PDFs give empty text → useless answers | RBI PDFs are sometimes image scans | Ingest logs `ingest.doc_skipped` when chars/page < 200; curate the manifest | — |
| B25 | Trivy fails the build on base-image CVEs you can't fix | Unfixed CVEs | `--ignore-unfixed --severity CRITICAL`; `.trivyignore` with reasons | Make the scan non-blocking temporarily and say so |
| B26 | Single-author git history | One person built everything | Ownership split in AGENTS §8 and PRD §11 (Teammate 1: foundation, P1, P2, eval runner; Teammate 2: P3, P4, P5; P6 shared); each commits their own milestone branch and reviews the other's PRs; weekly check of `git shortlog -sn` | — |
| B27 | Works on one laptop only | Hard-coded paths/IPs; different OS | Everything in `ansible/group_vars`; the demo machine is fixed as Windows 11 + Ubuntu 24.04 on WSL2 and named in the README; test B1 and B19 on it early | Demo on the fixed machine only |
| B28 | Minikube on Windows behaves differently | Docker Desktop networking: the node IP is not reachable from the browser | Publish ingress with `--ports=127.0.0.1:80:80` and map `niyam.local` to `127.0.0.1` (ARCH §3.1) | Check `docker port niyam 80/tcp` |
| B29 | Rollback never runs after a failed deploy | `DEPLOYED` declared in the Jenkinsfile `environment{}` block, which can't be reassigned from `script{}` | Set `env.DEPLOYED` only inside `script{}` (DATA_MODEL §9.4) | `make rollback` |
| B30 | Rollback reverts the wrong thing | `kubectl rollout undo` on a Deployment the failed release never changed goes back one revision too far | Redeploy `last_good_tag` from ConfigMap `niyam-release` (DATA_MODEL §6) | Deploy a known SHA by hand |
| B31 | `niyam-web` pods crash-loop in K8s | Dev nginx config proxies to host `api`, which doesn't resolve in the cluster, and nginx refuses to start | Image ships the K8s `nginx.conf` (no proxy); Compose mounts `nginx.dev.conf` | — |
| B32 | Secrets leak into the Jenkins console | Groovy double-quoted `sh "…$DH_PASS…"` interpolation | Single-quoted `sh '…'` everywhere; `--password-stdin` | Rotate the Docker Hub token |
| B34 | ELK pods stuck `Init:0/1` after a laptop reboot | Dev-mode Vault restarted empty; the injector can't fetch ELK passwords | `make vault-reseed`, then `kubectl delete pod -n logging --all` | — |
| B35 | Kibana "not ready" for minutes; demo starts before it's up | Kibana takes 1–3 min to boot on a laptop | Generous startupProbe; bring the cluster up 15 min before the demo; **don't restart pods right before the viva** | Show `kubectl get pods -n logging` and wait |
| B36 | Indices suddenly read-only, logs stop | ES disk watermark: node disk > 95% full (minikube default disk is 20 GB) | `minikube start --disk-size=40g`; ES `cluster.routing.allocation.disk.threshold_enabled: false` (single-node laptop only); delete old daily indices | `DELETE niyam-app-<old>` |
| B33 | Eval results can't be written in CI | `eval/` volume is not writable by container uid 10001 | `chmod o+w eval/results` in `ci_eval.sh`, or `--user root` for that one run | — |
| B37 | Ansible ignores `ansible.cfg` | The repo on `/mnt/c` appears world-writable, and Ansible refuses a config in such a directory | Makefile and Jenkinsfile set `ANSIBLE_CONFIG=ansible/ansible.cfg` | `ansible-config dump --only-changed` |
| B38 | `scripts/*.sh: Permission denied` in Jenkins | Windows git has `core.filemode=false`, so the executable bit is not recorded | Stage scripts with `git add --chmod=+x`; call them through `bash` | `git ls-files -s scripts/` shows `100755` |
| B39 | `minikube start` fails with `K8S_UNHEALTHY_CONTROL_PLANE` after a WSL restart; Jenkins can't reach the cluster | The API server's published port changes on restart | `make cluster-up` retries once and refreshes the Jenkins kubeconfig | Run `minikube start -p niyam` again |
| B40 | `niyam.local` resolves in Windows but not in Ubuntu | WSL does not copy the loopback entry from the Windows hosts file | Scripts use `curl --resolve niyam.local:80:127.0.0.1` | `curl -H 'Host: niyam.local' http://127.0.0.1/` |
| B41 | Build waits forever for `niyam-wsl` | The Ubuntu agent is offline because WSL stopped or the Windows Jenkins restarted | Agent runs as a restarting user service; check it before the demo | `systemctl --user restart niyam-jenkins-agent` |

## C. Over-engineering: what we deliberately do **not** build

The spec rewards a **working, automated, explainable** pipeline. Each item below costs days, adds failure
points and has to be defended in a viva, for little or no marks.

| Temptation | Why it's cut | What we do instead |
|---|---|---|
| Argo CD / GitOps | Spec names Jenkins + Ansible for deploy. A second CD system blurs who deploys. | Jenkins → Ansible `deploy.yml` |
| Argo Rollouts canary with metric analysis | Needs Prometheus + a rollout controller; minikube canaries with 2 pods are theatre | Eval gate + post-deploy verify + redeploy `last_good_tag` |
| Prometheus + Grafana | Spec monitoring = ELK. A parallel stack doubles RAM and splits the story. | Kibana panels from logs (latency, errors, versions, eval) |
| OpenTelemetry / Tempo / Jaeger | Not in spec; heavy on a laptop | `request_id` + per-stage latency fields in logs |
| Helm chart for our own app | Extra tool alongside Ansible templates | Jinja2 templates in roles (Vault Helm chart is fine) |
| Terraform | Nothing cloud to provision | Ansible `minikube` role |
| Postgres | No relational data (ARCH ADR-8) | Manifest + Qdrant payload + logs |
| Kafka / queues / async workers | No throughput need | Synchronous API; ingest as a K8s Job |
| Ollama inside K8s / GPU scheduling | 2 GB model in the VM, slow, fragile | Ollama on host behind a K8s Service |
| LLM-as-judge evaluation | Slow and noisy on CPU; can't gate CI | Deterministic metrics (DATA_MODEL §5) |
| ECK operator / Elastic Helm charts | Extra operator + CRDs to explain; ECK keeps its own passwords in K8s Secrets (cuts across the Vault story); Elastic's Helm charts are deprecated | Plain ES/Logstash/Kibana/Filebeat manifests templated by the Ansible `elk` role |
| React/Next.js frontend | Build tooling, bigger image, nothing graded | Static HTML/JS on nginx |
| Login / auth / multi-tenant | Not graded; adds secrets and bugs | Public demo app + disclaimer |
| Cosign / SBOM / Kyverno / OPA | Nice DevSecOps, but the spec's security ask is Vault | Trivy scan only (cheap). Cosign is a stretch goal **only** after P6 |
| Multi-node cluster, multi-cluster | Laptop RAM | Single-node minikube |
| Streaming responses, chat memory, reranker models | App complexity isn't graded | One-shot Q&A with citations |
| Hybrid BM25 + vector, query rewriting | Quality tuning rabbit hole | Plain vector search + refusal threshold |

**Borderline, keep only if cheap:** Trivy (keep: one stage, ~30 lines); filters by regulator/year (keep: a payload filter, about 1 hour); feedback endpoint (keep: feeds a Kibana panel).

## D. Cut order if time runs out (cut from the top; never cut below the line)

1. Cosign / any stretch item
2. Feedback endpoint + its panel
3. Regulator/year filters
4. Trivy stage
5. Post-deploy live eval (keep `/version` verify + rollback)
6. Generation part of the eval gate (keep retrieval-only gate)

──────── **never cut below this line** ────────

7. Webhook → Jenkins → tests → Docker Hub → Ansible → K8s (20 marks)
8. ELK + Kibana dashboard (mandatory spec item 3)
9. Zero-downtime rolling update + version footer (spec item 2 + live patching)
10. Vault + Ansible roles + HPA (3 marks)
11. Finance/LLMOps framing (5 marks)
12. Retrieval eval gate (innovation, 2 marks)
