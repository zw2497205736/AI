#!/usr/bin/env bash

set -euo pipefail

SERVER_USER="${SERVER_USER:-root}"
SERVER_HOST="${SERVER_HOST:-101.133.137.152}"
SERVER_PATH="${SERVER_PATH:-/root}"
PROJECT_NAME="${PROJECT_NAME:-AI}"
ARCHIVE_NAME="${ARCHIVE_NAME:-AI.tar.gz}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_PARENT="$(dirname "$SCRIPT_DIR")"
ARCHIVE_PATH="${PROJECT_PARENT}/${ARCHIVE_NAME}"

echo "Packing project from: ${SCRIPT_DIR}"
cd "$PROJECT_PARENT"
tar -czf "$ARCHIVE_NAME" "$PROJECT_NAME"

echo "Uploading archive to ${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/"
scp "$ARCHIVE_PATH" "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/"

echo "Deploying on server..."
ssh "${SERVER_USER}@${SERVER_HOST}" <<EOF
set -euo pipefail
cd "${SERVER_PATH}"
rm -rf "${SERVER_PATH}/${PROJECT_NAME}"
tar -xzf "${ARCHIVE_NAME}"
cd "${SERVER_PATH}/${PROJECT_NAME}"
docker-compose down
docker rm -f ai_backend_1 ai_frontend_1 ai_redis_1 2>/dev/null || true
docker-compose up -d --build
docker-compose ps
EOF

echo "Deployment finished."
echo "Open: http://${SERVER_HOST}:3000"
