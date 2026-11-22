# ARCHITECTURE — ESSENTIAL (one page, learn this for the viva)

**Niyam** = RBI/SEBI circular Q&A with citations (RAG on a local LLM) + a full DevOps pipeline that follows `context/spec.pdf`.
**Domain marks:** Finance + MLOps/AIOps. **Innovation:** eval-gated release with auto-rollback.

```
 git push ─► GitHub ─webhook─► JENKINS (host)
                                 │ 1 unit tests (docker build --target test)
                                 │ 2 build api:SHA, web:SHA
                                 │ 3 EVAL GATE (compose: api:SHA + qdrant + fixtures) ── fail ⇒ stop
                                 │ 4 trivy scan
                                 │ 5 push ─► DOCKER HUB
                                 │ 6 ansible-playbook deploy.yml -e image_tag=SHA
                                 │ 7 verify /version + live eval ── fail ⇒ rollback.yml (redeploy last_good_tag)
                                 ▼
 MINIKUBE ns niyam:  Ingress niyam.local ─► web (nginx)   /api ─► api (FastAPI, HPA 2–4) ─► qdrant
                                                                    │ secrets: Vault Agent → /vault/secrets/qdrant
                                                                    └─► Ollama on host :11434 (LLM)
 MINIKUBE ns logging: Filebeat DS ─► Logstash ─► Elasticsearch (StatefulSet+PVC) ─► Kibana (kibana.niyam.local)
```

## The 5 flows in one line each
1. **Code → prod:** push → webhook → Jenkinsfile → tests → eval → scan → Docker Hub → Ansible roles → K8s rolling update.
2. **Request:** browser → ingress → api → embed (in pod) → Qdrant top-6 → low score? refuse : Ollama → answer + citations.
3. **Logs:** JSON stdout → Filebeat → Logstash (`json` filter, target `app`) → ES `niyam-app-*` → Kibana.
4. **Secrets:** ansible-vault (bootstrap) → Vault KV → K8s auth → Agent Injector → file in pod. No app secret lives in a K8s Secret.
5. **Scale / patch:** HPA on CPU 60% (min 2, max 4); RollingUpdate maxUnavailable 0 + readiness + preStop ⇒ zero downtime.

## 12 decisions you must defend
| Decision | One-line reason |
|---|---|
| Jenkins native, not in Docker | Avoids Docker-in-Docker and kubeconfig pain |
| App + ELK in K8s; Jenkins + Ollama on host | App and its observability on one platform; the CI server and model server are external dependencies |
| Manifests = Jinja2 templates in Ansible roles | Spec names Ansible; no extra Helm/Kustomize tool |
| Tag = git SHA, never `latest` | Traceable; guaranteed rollout; trivial rollback |
| Vault dev mode + re-seed role | Laptop-friendly; prod would be Raft + auto-unseal |
| Embeddings inside the api pod | Makes CPU-based HPA meaningful |
| HPA demo on `/search`, not `/ask` | `/ask` is bound by the single host LLM; more pods won't help |
| Readiness ignores Ollama | One external hiccup must not take all pods out |
| Refuse below score 0.68, no LLM call | Cheap, deterministic, reduces hallucination; uncited LLM answers are refused too |
| Deterministic eval metrics, not LLM-judge | Fast and stable enough to gate CI |
| `replicas` omitted when HPA exists | Stops Ansible and the HPA fighting over replica count |
| `index.html` no-cache + `?v=SHA` assets | "Refresh shows the change" (spec item 2) |

## Ports
`niyam.local:80` app · `localhost:8080` Jenkins · `kibana.niyam.local` Kibana · `elasticsearch.logging.svc:9200` · `logstash.logging.svc:5044` · `:11434` Ollama · `qdrant:6333` · Vault UI `kubectl port-forward -n vault svc/vault 8200`

## Commands to know cold
```bash
make bootstrap                 # ansible-playbook site.yml: cluster, vault, elk, ollama, qdrant, app, ingest
make deploy TAG=<sha>          # ansible-playbook deploy.yml -e image_tag=<sha>
make rollback                  # ansible-playbook rollback.yml
kubectl get pods,hpa -n niyam -w
kubectl rollout history deploy/niyam-api -n niyam
scripts/zero_downtime_check.sh # run during a deploy → expect "0 failed"
scripts/load_test.sh           # hey on /api/v1/search → watch HPA
kubectl exec -n niyam deploy/niyam-api -c api -- cat /vault/secrets/qdrant   # proves injection
```

## Likely viva questions (short answers)
- *What happens if two people push at once?* `disableConcurrentBuilds()` queues them; each SHA deploys in order.
- *How is this zero-downtime?* maxUnavailable 0 + readiness gate + preStop sleep; proven by the zero-downtime script showing 0 failures.
- *Where are secrets?* Vault KV v2; pods authenticate with their ServiceAccount; the agent writes a file; Jenkins creds live in the Jenkins credential store; Ansible bootstrap values are ansible-vault encrypted.
- *Why does HPA not scale on `/ask`?* Generation is I/O-wait on Ollama; you'd scale the LLM server, not the API.
- *Why is ELK in Kubernetes but Jenkins isn't?* Jenkins builds and deploys the cluster, so it must survive a cluster rebuild. ELK is the app's own observability stack, so it lives with the app and uses cluster DNS and Vault.
- *What is ELK showing that `kubectl logs` can't?* History across pod restarts, all replicas in one place, aggregations (p95, refusal rate, per-version traffic).
- *How do you roll back?* Automatically in Jenkins `post{failure}` or `make rollback`: Ansible redeploys `last_good_tag` (stored in ConfigMap `niyam-release`, set only after Verify passes) through the same `app` role. Better than `rollout undo`, which could revert a Deployment the failed release never changed.
- *What's the innovation?* Answer-quality tests are a release gate. A worse prompt or chunking never reaches users, and a bad live release rolls itself back.
- *Why is this domain-specific?* Finance regulation corpus + LLMOps concerns (model/prompt versioning, retrieval quality, eval gating).
