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
RUNTIME_ENV_RELATIVE_PATH="backend/.env"

echo "Packing project from: ${SCRIPT_DIR}"
cd "$PROJECT_PARENT"
tar \
  --exclude="${PROJECT_NAME}/.git" \
  --exclude="${PROJECT_NAME}/venv" \
  --exclude="${PROJECT_NAME}/backend/.env" \
  --exclude="${PROJECT_NAME}/backend/app.db" \
  --exclude="${PROJECT_NAME}/backend/chroma_db" \
  --exclude="${PROJECT_NAME}/backend/__pycache__" \
  --exclude="${PROJECT_NAME}/frontend/node_modules" \
  --exclude="${PROJECT_NAME}/frontend/dist" \
  --exclude="${PROJECT_NAME}/.DS_Store" \
  --exclude="${PROJECT_NAME}/._*" \
  -czf "$ARCHIVE_NAME" "$PROJECT_NAME"

echo "Uploading archive to ${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/"
scp "$ARCHIVE_PATH" "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/"

echo "Deploying backend only on server..."
ssh "${SERVER_USER}@${SERVER_HOST}" <<EOF
set -euo pipefail
cd "${SERVER_PATH}"
if [ -f "${SERVER_PATH}/${PROJECT_NAME}/${RUNTIME_ENV_RELATIVE_PATH}" ]; then
  cp "${SERVER_PATH}/${PROJECT_NAME}/${RUNTIME_ENV_RELATIVE_PATH}" "${SERVER_PATH}/${PROJECT_NAME}.backend.env.bak"
fi
rm -rf "${SERVER_PATH}/${PROJECT_NAME}"
tar -xzf "${ARCHIVE_NAME}"
if [ -f "${SERVER_PATH}/${PROJECT_NAME}.backend.env.bak" ]; then
  mkdir -p "${SERVER_PATH}/${PROJECT_NAME}/backend"
  mv "${SERVER_PATH}/${PROJECT_NAME}.backend.env.bak" "${SERVER_PATH}/${PROJECT_NAME}/${RUNTIME_ENV_RELATIVE_PATH}"
fi
cd "${SERVER_PATH}/${PROJECT_NAME}"
docker-compose stop backend || true
docker ps -a --format '{{.Names}}' | grep -E '(^|_)ai_backend_1$|backend' | xargs -r docker rm -f 2>/dev/null || true
docker-compose up -d --build backend
docker-compose ps
EOF

echo "Backend deployment finished."
echo "API: http://${SERVER_HOST}:8000"
