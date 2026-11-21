# CLAUDE.md

@AGENTS.md

The file above holds the shared rules for every agent; they all apply. Below are Claude Code–specific additions only.

## Git & commit protocol

These rules apply to whichever teammate is at the keyboard. **The human makes every commit. Claude is never the author of a commit.**

1. **Never run git commands that change the index, history, branches, tags, stash or remote:** no `git add`, `commit`, `push`, `pull`, `fetch`, `merge`, `rebase`, `reset`, `restore --staged`, `tag`, `stash`, `switch`, `checkout`, `branch -d`, `cherry-pick`, `revert` or `remote add`. Read-only git is fine: `git status`, `diff`, `log`, `show`, `branch --list`, `config --get`. `.claude/settings.json` enforces this with a deny list.
2. **When a logical unit of work is finished, stop and print a commit checkpoint, then wait for the human's reply.** Use a colored `diff` block for the banner and keep commands in separate `powershell` or `bash` blocks, so a leading `+` is never copied:

   ````markdown
   ```diff
   + ━━━━━━━━━━━━━━━━━━ COMMIT CHECKPOINT ━━━━━━━━━━━━━━━━━━
   + Why now: <one line: what this unit achieves>
   + PRD IDs: <e.g. DR-5, FR-8>
   - Leave for next checkpoint: <paths, or "nothing">
   ```

   **Stage (explicit paths only, never `git add .` or `-A`):**
   ```powershell
   git add <path1> <path2> ...
   ```

   **Review:**
   ```powershell
   git diff --staged --stat
   ```

   **Commit:**
   ```powershell
   git commit -m "<type>(<scope>): <imperative summary, ≤ 72 chars>" -m "<body: WHY this change, any trade-off. Refs: <PRD IDs>>"
   ```

   ```diff
   + Reply "done" when committed, or "skip" to fold these changes into the next checkpoint.
   ```
   ````
3. **After "done",** run `git log --oneline -3` and `git status --short` to confirm the commit landed and nothing from that unit was left unstaged. Then continue.
4. **What a good commit looks like:**
   - One logical change per commit, ideally 20–300 changed lines. Split bigger units into several checkpoints, and never let more than about an hour of work pile up without one.
   - Conventional Commits. Types: `feat`, `fix`, `test`, `refactor`, `docs`, `build`, `ci`, `chore`, `perf`. Scopes: `api`, `web`, `ingest`, `rag`, `eval`, `ansible`, `k8s`, `vault`, `elk`, `jenkins`, `docker`, `scripts`, `docs`.
   - Never mix app code and infra in one commit. Tests go in the same commit as the code they test, or in an immediately following `test(...)` commit.
   - Commit messages never say "wip", "update files" or "fix stuff", and never include Co-Authored-By, AI/tool attribution lines, or the name of any AI tool, in the subject, scope or body.
   - A bug fix gets its own `fix(...)` commit that explains the root cause in the body.
5. **Branching:** one branch per milestone and owner, such as `feat/p1-walking-skeleton` or `feat/p3-elk`. Changes reach `main` only through a GitHub PR merged with a **merge commit** (not squash), reviewed by the other teammate when possible. Give the human the exact commands to create and push a branch, open the PR, merge, and tag (`git tag -a vX.Y.Z -m "..."`, then `git push origin vX.Y.Z`). The human runs them. Before each new branch, tell the human to update main first (`git switch main`, then `git pull`).
6. **Never run sudo, install system packages, or create accounts or tokens.** For anything on the human's machine that needs those (Docker, minikube, Jenkins, Ollama, Docker Hub tokens, GitHub webhook, smee/ngrok), give numbered steps and how to check that each one worked.
7. **At the start of every session,** run `git config --get user.name` and `git config --get user.email`, show the result, and remind the human that the email must be linked to their GitHub account, otherwise their commits won't count on GitHub.

Planning docs live in `context/`. New docs (ADRs, `HANDOFF.md`, final report, evidence screenshots) go in `docs/`.

## Before you start any task
- Read the PRD row(s) the task maps to (`context/PRD.md`, IDs like DR-9, AR-3) and say which ones you're implementing.
- For anything in `ansible/`, `infra/`, `Jenkinsfile` or K8s templates: read `context/WHAT_WILL_BREAK.md` §B first and name which pitfalls apply.
- For multi-file or infra changes, use plan mode and show the plan before editing.

## How to work in this repo
- Prefer editing existing files over creating new ones. Follow the tree in `context/DATA_MODEL_AND_SCAFFOLDING.md` §8 exactly. Don't invent new top-level folders.
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
