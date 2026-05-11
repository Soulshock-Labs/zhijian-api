#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

usage() {
  cat <<'USAGE'
用法：
  bash scripts/deploy_google_cloud_run.sh \
    --project <GCP_PROJECT_ID> \
    --region <REGION> \
    --service <CLOUD_RUN_SERVICE> \
    --repo <ARTIFACT_REGISTRY_REPO> \
    --image <IMAGE_NAME> \
    --secret-value <DASHSCOPE_API_KEY>

可选参数：
  --base-url <URL>           AI 基础地址，默认 https://api.deepseek.com/v1
  --ai-model <MODEL>         默认 deepseek-chat
  --app-version <VERSION>    默认读取 main.py 当前版本或 latest
  --allow-mock <0|1>         默认 0
  --enable-aspose <0|1>      默认 0
  --port <PORT>              默认 8080
  --memory <SIZE>            默认 1Gi
  --cpu <COUNT>              默认 1
  --min-instances <N>        默认 0
  --max-instances <N>        默认 3
  --timeout <SECONDS>        默认 300
  --concurrency <N>          默认 20
  --service-account <EMAIL>  指定 Cloud Run 运行身份
  --ingress <MODE>           默认 all
  --env-file <FILE>          从文件补齐 DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL / AI_MODEL
  --skip-build               仅重新部署现有镜像
  --dry-run                  只打印关键变量，不执行部署

示例：
  bash scripts/deploy_google_cloud_run.sh \
    --project my-prod-123456 \
    --region asia-east1 \
    --service smart-teacher-api \
    --repo smart-teacher \
    --image api \
    --env-file .env
USAGE
}

PROJECT_ID=""
REGION="asia-east1"
SERVICE_NAME="smart-teacher-api"
REPOSITORY="smart-teacher"
IMAGE_NAME="api"
SECRET_NAME="DASHSCOPE_API_KEY"
SECRET_VALUE=""
BASE_URL="https://api.deepseek.com/v1"
AI_MODEL="deepseek-chat"
APP_VERSION=""
ALLOW_MOCK_CONTENT="0"
ENABLE_ASPOSE_WORDS="0"
PORT="8080"
MEMORY="1Gi"
CPU="1"
MIN_INSTANCES="0"
MAX_INSTANCES="3"
TIMEOUT="300"
CONCURRENCY="20"
SERVICE_ACCOUNT=""
INGRESS="all"
ENV_FILE=""
SKIP_BUILD="0"
DRY_RUN="0"

CLI_SECRET_VALUE=""
CLI_BASE_URL=""
CLI_AI_MODEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --service) SERVICE_NAME="$2"; shift 2 ;;
    --repo) REPOSITORY="$2"; shift 2 ;;
    --image) IMAGE_NAME="$2"; shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --secret-value) SECRET_VALUE="$2"; CLI_SECRET_VALUE="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; CLI_BASE_URL="$2"; shift 2 ;;
    --ai-model) AI_MODEL="$2"; CLI_AI_MODEL="$2"; shift 2 ;;
    --app-version) APP_VERSION="$2"; shift 2 ;;
    --allow-mock) ALLOW_MOCK_CONTENT="$2"; shift 2 ;;
    --enable-aspose) ENABLE_ASPOSE_WORDS="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --cpu) CPU="$2"; shift 2 ;;
    --min-instances) MIN_INSTANCES="$2"; shift 2 ;;
    --max-instances) MAX_INSTANCES="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --concurrency) CONCURRENCY="$2"; shift 2 ;;
    --service-account) SERVICE_ACCOUNT="$2"; shift 2 ;;
    --ingress) INGRESS="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD="1"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERROR] 未知参数: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v gcloud >/dev/null 2>&1; then
  echo "[ERROR] gcloud 未安装。先安装 Google Cloud SDK。" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker 未安装。先安装并启动 Docker。" >&2
  exit 1
fi

if [[ -n "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "[ERROR] env 文件不存在: $ENV_FILE" >&2
    exit 1
  fi

  ENV_SECRET_VALUE="$(grep -E '^DASHSCOPE_API_KEY=' "$ENV_FILE" | tail -n 1 | cut -d '=' -f2- || true)"
  ENV_BASE_URL="$(grep -E '^DASHSCOPE_BASE_URL=' "$ENV_FILE" | tail -n 1 | cut -d '=' -f2- || true)"
  ENV_AI_MODEL="$(grep -E '^AI_MODEL=' "$ENV_FILE" | tail -n 1 | cut -d '=' -f2- || true)"

  if [[ -z "$CLI_SECRET_VALUE" && -n "$ENV_SECRET_VALUE" ]]; then
    SECRET_VALUE="$ENV_SECRET_VALUE"
  fi
  if [[ -z "$CLI_BASE_URL" && -n "$ENV_BASE_URL" ]]; then
    BASE_URL="$ENV_BASE_URL"
  fi
  if [[ -z "$CLI_AI_MODEL" && -n "$ENV_AI_MODEL" ]]; then
    AI_MODEL="$ENV_AI_MODEL"
  fi
fi

if [[ -z "$PROJECT_ID" ]]; then
  echo "[ERROR] 必填参数缺失: --project" >&2
  usage
  exit 1
fi

if [[ -z "$SECRET_VALUE" ]]; then
  echo "[ERROR] 必填参数缺失: --secret-value 或 --env-file 中的 DASHSCOPE_API_KEY" >&2
  exit 1
fi

if [[ -z "$APP_VERSION" ]]; then
  APP_VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path('main.py').read_text(encoding='utf-8')
m = re.search(r'APP_VERSION\s*=\s*os\.getenv\("APP_VERSION",\s*"([^"]+)"\)', text)
print(m.group(1) if m else 'latest')
PY
)"
fi

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${APP_VERSION}"
LATEST_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:latest"

printf '\n[INFO] 项目目录: %s\n' "$PROJECT_ROOT"
printf '[INFO] GCP 项目: %s\n' "$PROJECT_ID"
printf '[INFO] 部署区域: %s\n' "$REGION"
printf '[INFO] Cloud Run 服务: %s\n' "$SERVICE_NAME"
printf '[INFO] Artifact Registry: %s\n' "$REPOSITORY"
printf '[INFO] AI Base URL: %s\n' "$BASE_URL"
printf '[INFO] AI Model: %s\n' "$AI_MODEL"
printf '[INFO] 镜像标签: %s\n\n' "$APP_VERSION"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "[DRY RUN] IMAGE_URI=$IMAGE_URI"
  echo "[DRY RUN] LATEST_URI=$LATEST_URI"
  exit 0
fi

if ! gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q .; then
  echo "[ERROR] 当前没有激活的 gcloud 账号。先执行: gcloud auth login" >&2
  exit 1
fi

gcloud config set project "$PROJECT_ID" >/dev/null

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com >/dev/null

if ! gcloud artifacts repositories describe "$REPOSITORY" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="smart-teacher-assistant images"
fi

if gcloud secrets describe "$SECRET_NAME" >/dev/null 2>&1; then
  printf '%s' "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" --data-file=- >/dev/null
else
  printf '%s' "$SECRET_VALUE" | gcloud secrets create "$SECRET_NAME" --replication-policy=automatic --data-file=- >/dev/null
fi

if [[ "$SKIP_BUILD" != "1" ]]; then
  gcloud builds submit --tag "$IMAGE_URI"
  gcloud artifacts docker tags add "$IMAGE_URI" "$LATEST_URI" >/dev/null
fi

DEPLOY_CMD=(
  gcloud run deploy "$SERVICE_NAME"
  --image "$IMAGE_URI"
  --region "$REGION"
  --platform managed
  --allow-unauthenticated
  --port "$PORT"
  --memory "$MEMORY"
  --cpu "$CPU"
  --min-instances "$MIN_INSTANCES"
  --max-instances "$MAX_INSTANCES"
  --timeout "$TIMEOUT"
  --concurrency "$CONCURRENCY"
  --ingress "$INGRESS"
  --set-env-vars "DASHSCOPE_BASE_URL=$BASE_URL,AI_MODEL=$AI_MODEL,ALLOW_MOCK_CONTENT=$ALLOW_MOCK_CONTENT,ENABLE_ASPOSE_WORDS=$ENABLE_ASPOSE_WORDS,APP_VERSION=$APP_VERSION"
  --set-secrets "DASHSCOPE_API_KEY=${SECRET_NAME}:latest"
)

if [[ -n "$SERVICE_ACCOUNT" ]]; then
  DEPLOY_CMD+=(--service-account "$SERVICE_ACCOUNT")
fi

"${DEPLOY_CMD[@]}"

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')"

echo
printf '[SUCCESS] Cloud Run 已发布: %s\n' "$SERVICE_URL"
printf '[SUCCESS] 健康检查: %s/health\n' "$SERVICE_URL"
printf '[SUCCESS] 镜像地址: %s\n' "$IMAGE_URI"
