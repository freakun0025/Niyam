# Niyam handoff: Teammate 1 to Teammate 2

Teammate 1's build work is complete. Teammate 2 now owns **P3 (ELK), P4 (Vault and HPA) and P5 (release gate)**. P6 (demo rehearsal, report and backup recording) is shared.

Start with `context/SPEC.md`, `AGENTS.md`, `CLAUDE.md` and this file. If documents disagree, `context/SPEC.md` wins.

## 1. Current state

**Release:** `v0.2.0`, commit and image tag `1d920d2`, live at `http://niyam.local` on the demo laptop.

| Area | Status |
|---|---|
| App | Search, cited answers, refusal, filters, feedback, document list and web UI |
| Corpus | 30 documents (6 RBI, 24 SEBI), 2,003 passages |
| CI/CD | GitHub webhook through ngrok → Jenkins → tests → Docker Hub → Ansible → minikube → smoke test |
| Ansible roles | `common`, `minikube`, `ollama`, `qdrant`, `app`, `ingest` |
| Evaluation | `eval/golden.jsonl`, `eval/thresholds.yaml`, `eval/run_eval.py` |
| Not built yet | ELK, Vault, HPA, load and zero-downtime scripts, Jenkins eval gate, Trivy, `mark_good`, rollback |

**How `v0.2.0` was verified**

- Jenkins build #6 was started by the GitHub webhook and passed every stage.
- All 187 unit tests passed in Docker.
- `make bootstrap` ran twice on the demo laptop. The second run reported `changed=0`.
- The live evaluation passed: retrieval 100%, citations 100%, correct answer-or-refusal 90%, search p95 87 ms.

**Known issues**

1. **Answer quality is moderate.** The small CPU model still makes mistakes. For example, on the CI set it wrongly says apps may access a borrower's contact list with consent.
2. **The CI eval margin is thin.** `keyword_recall` is `0.625` against a `0.60` limit, so one changed answer can fail the gate. Do not lower a threshold to get a green build (`AGENTS.md` §5).
3. **The first answer after idle is slow,** about 30 to 40 seconds while Ollama loads the model. Ask a warm-up question before the demo.
4. **Qdrant has no API key yet.** Securing it is part of P4.
5. **Setup has only been tested on the demo laptop.** See section 2 if your machine differs.

## 2. Set up your laptop

**Target:** Windows 11, Ubuntu 24.04 on WSL2, Docker Desktop with WSL integration, and 16 GB RAM. Run project commands inside Ubuntu.

### 2.1 Windows

Create or update `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=12GB
swap=8GB
processors=8
```

In an **Administrator PowerShell**, add the hostnames and restart WSL. Then start Docker Desktop:

```powershell
Add-Content C:\Windows\System32\drivers\etc\hosts "`r`n127.0.0.1 niyam.local kibana.niyam.local"
wsl --shutdown
```

Check inside Ubuntu that `free -h` shows about 12 GB and `docker version` shows a server.

### 2.2 Ubuntu tools

```bash
sudo apt-get update
sudo apt-get install -y git make curl jq python3-venv
sudo snap install ollama
mkdir -p ~/.local/bin

cd /tmp
curl -fLO https://github.com/kubernetes/minikube/releases/download/v1.39.0/minikube-linux-amd64
curl -fLO https://github.com/kubernetes/minikube/releases/download/v1.39.0/minikube-linux-amd64.sha256
echo "$(cat minikube-linux-amd64.sha256)  minikube-linux-amd64" | sha256sum -c -
install -m 0755 minikube-linux-amd64 ~/.local/bin/minikube

curl -fLO https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl
curl -fLO https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl.sha256
echo "$(cat kubectl.sha256)  kubectl" | sha256sum -c -
install -m 0755 kubectl ~/.local/bin/kubectl
rm -f minikube-linux-amd64 minikube-linux-amd64.sha256 kubectl kubectl.sha256

python3 -m venv ~/.local/share/niyam-ansible
~/.local/share/niyam-ansible/bin/pip install "ansible==11.7.0" "kubernetes==31.0.0" "jsonpatch==1.33"
for tool in ansible ansible-config ansible-galaxy ansible-inventory ansible-playbook ansible-vault; do
  ln -sf ~/.local/share/niyam-ansible/bin/$tool ~/.local/bin/$tool
done
exec bash -l
```

Both `sha256sum` lines must print `OK`.

### 2.3 Repository and vault password

Teammate 1 will send the Ansible Vault password through a private channel. Never put it in GitHub, a commit, a group chat or a coding assistant.

```bash
git clone https://github.com/freakun0025/Niyam.git ~/Niyam
cd ~/Niyam
git config user.name "Your Name"
git config user.email "your-github-linked-email@example.com"
(umask 077; read -rsp 'Vault password: ' p; echo; printf '%s\n' "$p" > ~/.niyam-vault-pass; unset p)
ansible-vault view --vault-password-file ~/.niyam-vault-pass ansible/group_vars/all/vault.yml > /dev/null && echo "vault OK"
ansible-galaxy collection install -r ansible/requirements.yml
```

Use an email linked to your GitHub account, otherwise your commits will not count on your profile.

### 2.4 Bootstrap

```bash
make bootstrap TAG=1d920d2
bash scripts/smoke.sh 1d920d2
make eval-live
```

`make bootstrap` asks for your Ubuntu password. The first run downloads images and the 1.8 GB model, then indexes the corpus, so allow 15 to 30 minutes. Then open `http://niyam.local` in Windows. The footer should show `1d920d2`.

If `dpkg was interrupted` appears, run `sudo dpkg --configure -a` and retry.

**Not on Windows + WSL + Docker Desktop?** This path is untested. The `ollama` role expects `host.docker.internal`. On native Linux, set `OLLAMA_HOST=0.0.0.0` for Ollama and pass `-e ollama_host_name=host.minikube.internal`. Ingress and Docker networking may also need changes.

### 2.5 Test a deploy without Jenkins

Jenkins, its Ubuntu agent and the ngrok tunnel run only on the demo laptop. On your laptop, commit your change, then:

```bash
TAG=$(git rev-parse --short=7 HEAD)
docker build -f services/api/Dockerfile --target runtime --build-arg APP_VERSION=$TAG -t freakun/niyam-api:$TAG .
docker build --build-arg APP_VERSION=$TAG -t freakun/niyam-web:$TAG services/web
minikube image load -p niyam freakun/niyam-api:$TAG freakun/niyam-web:$TAG
make deploy TAG=$TAG
bash scripts/smoke.sh $TAG
```

Commit before building. Pods use `IfNotPresent`, so rebuilding the same SHA may not replace the running image.

After a WSL restart, run `make cluster-up`.

## 3. Your scope

Work in this order. **Start P3 now.** Merge each milestone to `main` before starting the next.

| Branch | Milestone | Deliver | PRD | Read first in `WHAT_WILL_BREAK` |
|---|---|---|---|---|
| `feat/p3-elk` | ELK in Kubernetes | `elk` role, Logstash pipeline, index template, Filebeat, Kibana ingress, dashboard with at least 8 panels exported to `infra/kibana/dashboards.ndjson` | DR-10 | B4, B5, B19, B20, B21, B35, B36 |
| `feat/p4-vault-hpa` | Vault, HPA, live patching proof | `vault` role and injector, Qdrant API key, ELK passwords, `api-hpa.yaml.j2`, `scripts/load_test.sh`, `scripts/zero_downtime_check.sh`, `make vault-reseed` | AR-1, AR-3, AR-4, DR-9 | B8, B9, B10, B11, B12, B34 |
| `feat/p5-release-gate` | Release quality | `docker-compose.ci.yml`, `scripts/ci_eval.sh`, Eval gate and Scan stages, `scripts/live_eval.sh`, `mark_good.yml`, `rollback.yml`, `make rollback`, `post { failure }`, Kibana release-quality panel | DR-3, IR-1, IR-2, IR-3 | B14, B15, B25, B29, B30, B33 |

Commented extension points are already in `ansible/playbooks/site.yml`, `ansible/playbooks/deploy.yml`, `ansible/group_vars/all/main.yml`, `Jenkinsfile` and the API, ingest and Qdrant templates.

**Keep the histories balanced.** Teammate 1 finishes with about 46 commits. Use small, logical commits across P3 to P5 and aim for a similar count, without splitting work artificially. Check with `git shortlog -sn`.

## 4. Git workflow and shared files

Follow "Git & commit protocol" in `CLAUDE.md`. Use one branch per milestone, and reach `main` only through a GitHub PR merged with a **merge commit**. Each teammate reviews the other's PRs when possible.

These files are the most likely to conflict:

- `ansible/playbooks/site.yml`
- `ansible/group_vars/all/main.yml`
- `Jenkinsfile`
- `Makefile`

Rules for them:

1. Make small, separate commits.
2. Update from `main` daily.
3. Merge `main` into your branch before opening a PR.

```bash
git switch main
git pull
git switch feat/p3-elk
git merge main
```

## 5. Interface contracts

### 5.1 Logs

The API, ingest Job and web server write one JSON object per line to stdout. The schema is in `context/DATA_MODEL_AND_SCAFFOLDING.md` §4.

```json
{"ts":"2026-11-21T19:49:50.984Z","level":"INFO","service":"niyam-api","app_version":"1d920d2","pod":"niyam-api-abc","event":"request.completed","request_id":"uuid","method":"POST","path":"/api/v1/ask","status":200,"latency_ms":{"embed":10,"retrieve":4,"generate":900,"total":915},"refused":false,"top_score":0.78}
```

- **Events:** `request.completed`, `request.failed`, `llm.error`, `ingest.doc_indexed`, `ingest.doc_skipped`, `ingest.completed`, `ingest.failed`, `feedback.received`, `http.access`.
- **Refusals:** `/ask` logs `refused` and `refusal_reason` (`low_score`, `llm_not_found` or `no_citation`).
- **Health checks** are not logged.
- **Timestamps:** the API uses a `Z` suffix and nginx uses `+00:00`. Both are ISO 8601.

### 5.2 Qdrant API key

The app already reads `NIYAM_QDRANT_API_KEY_FILE`, default `/vault/secrets/qdrant`.

- Inject the key file into **both** the API Deployment and the ingest Job, using service account `niyam-api`.
- The file must exist before the app starts, which the Vault init container guarantees.
- An empty file stops startup with a clear error.
- The Qdrant client reads the key at startup, so restart pods after rotating it.
- Qdrant reads its key from `QDRANT__SERVICE__API_KEY`, so wrap its entrypoint to export the injected file.
- `/readyz` on Qdrant does not need the key.
- Wrap Vault Go templates in `{% raw %}...{% endraw %}`.

### 5.3 Evaluation runner

```bash
python eval/run_eval.py --base-url <url> [--stage ci|live] [--subset fixture|corpus|all] \
  [--limit N] [--host-header <host>] [--out <file>]
```

| Exit code | Meaning | Pipeline action |
|---|---|---|
| `0` | Thresholds met | Continue |
| `1` | A quality threshold failed | Stop the release |
| `2` | Setup or service error, no verdict | Fail and investigate |

- **CI gate:** `--stage ci --subset fixture`, using the 3-document fixture corpus.
- **Live check:** `--base-url http://127.0.0.1 --host-header niyam.local --stage live --subset corpus --limit 5`.
- **Results:** default path is `eval/results/<app_version>.json`, with `app_version`, `stage`, `subset`, `started_at`, `passed`, `cases`, `metrics`, `thresholds`, `thresholds_version` and `failures`.
- **Output:** the readable table goes to stderr. Stdout carries one JSON `eval.result` event.
- **For the Kibana panel:** Filebeat only reads pod logs, so P5 must get this event from Jenkins into ELK.
- **In a container:** mount `eval/`, and make `eval/results` writable by uid 10001 (B33).

### 5.4 Release record

ConfigMap `niyam-release` holds `current_tag` and `deployed_at`. The `app` role **merges** into it, so a `last_good_tag` written by `mark_good.yml` survives later deploys.

### 5.5 Jenkins rules

- Use `agent { label 'niyam-wsl' }`.
- **Every `sh` step must start with `#!/bin/bash`.** The Windows controller's global shell setting points to a Windows path that does not exist on the agent.
- Use single-quoted `sh` strings so Groovy never expands secrets.
- Credential IDs are `dockerhub` and `ansible-vault-pass`.
- Set `env.DEPLOYED` only inside `script {}`.

## 6. Demo laptop checklist

Before any demo or end-to-end test on the demo laptop:

1. Start **Docker Desktop**.
2. Start the Windows **Jenkins** service. Its startup type is Manual.
3. In Ubuntu, run `make cluster-up`.
4. Confirm `systemctl --user is-active niyam-jenkins-agent niyam-webhook-relay` prints `active` twice.
5. Confirm `niyam-wsl` is online in Jenkins.
6. Open `http://niyam.local` and ask one warm-up question.

## 7. Starter prompt for your first session

Paste this into your coding session from the repository root:

```text
You are continuing the "Niyam" CSE 816 final project as Teammate 2, owner of the platform and release-quality work.

Before doing anything else:
1. Read context/SPEC.md, context/PRD.md, context/ARCHITECTURE.md, context/ARCHITECTURE_ESSENTIAL.md, context/DATA_MODEL_AND_SCAFFOLDING.md, context/WHAT_WILL_BREAK.md, AGENTS.md, CLAUDE.md and docs/HANDOFF.md. context/SPEC.md beats every other document.
2. Follow "Git & commit protocol" in CLAUDE.md exactly. I make every commit. Never run git commands that change the index, history, branches, tags, stash or remote. When a logical unit is finished, stop and give me a commit checkpoint. Commit messages must not name any AI tool or include Refs lines.
3. Run git config --get user.name and git config --get user.email, show me the result, and remind me that the email must be linked to my GitHub account.
4. Check that my machine matches docs/HANDOFF.md section 2. Give me numbered steps for anything needing sudo, accounts or tokens.

My scope is P3 ELK, then P4 Vault and HPA, then P5 release gate, as listed in docs/HANDOFF.md section 3. Do not rebuild Teammate 1's app or pipeline. Use the interface contracts in section 5.

Start with P3 on branch feat/p3-elk. Tell me to update main first, name the PRD IDs and WHAT_WILL_BREAK items that apply, then use plan mode and wait for my approval before editing. Use small commits so our git histories stay about equal.
```
