#!/usr/bin/env bash
# 将本机 knowledge_base/（约 1.7GB）同步到 Google Cloud Storage。
# 使用前：gcloud auth login && gcloud config set project <PROJECT_ID>
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-apt-decorator-473807-t1}"
REGION="${GCP_REGION:-asia-east1}"
BUCKET="${GCS_KNOWLEDGE_BUCKET:-${PROJECT_ID}-knowledge}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT}/knowledge_base"
DEST_PREFIX="knowledge_base"

if [[ ! -d "$SRC" ]]; then
  echo "[ERROR] 未找到目录: $SRC" >&2
  exit 1
fi

echo "[INFO] PROJECT_ID=$PROJECT_ID"
echo "[INFO] BUCKET=gs://${BUCKET}"
echo "[INFO] SOURCE=$SRC"
echo "[INFO] DEST=gs://${BUCKET}/${DEST_PREFIX}/"

gcloud config set project "$PROJECT_ID" >/dev/null

if ! gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  echo "[INFO] 创建桶..."
  gcloud storage buckets create "gs://${BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --uniform-bucket-level-access
fi

echo "[INFO] 开始 rsync（大文件请耐心等待）..."
gcloud storage rsync -r "$SRC" "gs://${BUCKET}/${DEST_PREFIX}"

echo "[SUCCESS] 完成。对象前缀: gs://${BUCKET}/${DEST_PREFIX}/"
echo "[HINT] 在 .env 中可设: KNOWLEDGE_GCS_URI=gs://${BUCKET}/${DEST_PREFIX}"
