#!/usr/bin/env bash
# Gives Ansible the vault password from the Jenkins credential binding.
set -euo pipefail

printf '%s\n' "${ANSIBLE_VAULT_PASS:?ANSIBLE_VAULT_PASS is not set}"
