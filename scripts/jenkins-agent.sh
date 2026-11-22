#!/usr/bin/env bash
# Connects this Ubuntu WSL machine to the Jenkins controller running on Windows.
set -euo pipefail

agent_name="${JENKINS_AGENT_NAME:-niyam-wsl}"
work_dir="${JENKINS_AGENT_WORKDIR:-$HOME/jenkins-agent}"
secret_file="${JENKINS_AGENT_SECRET_FILE:-$HOME/.niyam-jenkins-agent-secret}"
port="${JENKINS_PORT:-8080}"

if [[ ! -s "$secret_file" ]]; then
  echo "FAIL: agent secret not found at $secret_file" >&2
  exit 2
fi

# The WSL default gateway is the Windows host, and its address can change after a restart.
windows_host="${JENKINS_HOST:-$(ip route show default | awk '{print $3; exit}')}"
if [[ -z "$windows_host" ]]; then
  echo "FAIL: could not find the Windows host address" >&2
  exit 1
fi
url="http://${windows_host}:${port}/"

mkdir -p "$work_dir"
jar="$work_dir/agent.jar"
download="$(mktemp "$work_dir/agent.jar.XXXXXX")"
trap 'rm -f "$download"' EXIT

# Download on every start so the agent always matches the controller version.
curl --fail --silent --show-error --location --max-time 60 \
  --output "$download" "${url}jnlpJars/agent.jar"
mv "$download" "$jar"
trap - EXIT

exec java -jar "$jar" \
  -url "$url" \
  -name "$agent_name" \
  -secret "@$secret_file" \
  -webSocket \
  -workDir "$work_dir"
