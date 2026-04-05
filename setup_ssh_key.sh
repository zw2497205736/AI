#!/usr/bin/env bash

set -euo pipefail

SERVER_USER="${SERVER_USER:-root}"
SERVER_HOST="${SERVER_HOST:-101.133.137.152}"
KEY_PATH="${KEY_PATH:-$HOME/.ssh/id_ed25519}"

if [[ ! -f "$KEY_PATH" ]]; then
  echo "Generating SSH key: $KEY_PATH"
  ssh-keygen -t ed25519 -f "$KEY_PATH" -N ""
fi

echo "Copying SSH key to ${SERVER_USER}@${SERVER_HOST}"
ssh-copy-id -i "${KEY_PATH}.pub" "${SERVER_USER}@${SERVER_HOST}"

echo "Testing passwordless SSH"
ssh "${SERVER_USER}@${SERVER_HOST}" "echo SSH key setup ok"
