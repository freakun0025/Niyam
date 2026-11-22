#!/usr/bin/env bash
# Exposes only the Jenkins GitHub webhook endpoint through ngrok.
set -euo pipefail

policy="${NGROK_POLICY:-$HOME/.config/niyam/ngrok-webhook-policy.yml}"
config="${NGROK_CONFIG:-$HOME/.config/ngrok/ngrok.yml}"
port="${JENKINS_PORT:-8080}"

if ! command -v ngrok >/dev/null; then
  echo "FAIL: ngrok is not installed" >&2
  exit 2
fi
if [[ ! -s "$config" ]]; then
  echo "FAIL: ngrok config not found at $config" >&2
  exit 2
fi
if [[ ! -s "$policy" ]]; then
  echo "FAIL: ngrok traffic policy not found at $policy" >&2
  exit 2
fi

# The WSL default gateway is the Windows host, and its address can change after a restart.
windows_host="${JENKINS_HOST:-$(ip route show default | awk '{print $3; exit}')}"
if [[ -z "$windows_host" ]]; then
  echo "FAIL: could not find the Windows host address" >&2
  exit 1
fi

# A fixed ngrok domain keeps the GitHub webhook URL valid across restarts.
domain_file="${NGROK_DOMAIN_FILE:-$HOME/.niyam-ngrok-domain}"
url_args=()
if [[ -s "$domain_file" ]]; then
  domain="$(tr -d '[:space:]' <"$domain_file")"
  domain="${domain#https://}"
  if [[ ! "$domain" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]]; then
    echo "FAIL: invalid ngrok domain in $domain_file" >&2
    exit 2
  fi
  url_args=(--url "https://${domain}")
fi

exec ngrok http "http://${windows_host}:${port}" \
  "${url_args[@]}" \
  --config "$config" \
  --traffic-policy-file "$policy" \
  --log stdout \
  --log-format logfmt
