# ────────────────────────────────────────────────────────────
# 智伴幼师 · Dockerfile
# 适配 Google Cloud Run（自动读取 PORT 环境变量）
# 同样可用于阿里云容器服务 ACK / 函数计算
# ────────────────────────────────────────────────────────────

FROM python:3.11-slim

# 系统依赖（python-docx 需要 lxml，Cloud Run 基础镜像已含）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码（.dockerignore 会排除 .env 等敏感文件）
COPY . .

# 发布前做一次轻量源码字符检查，避免弯引号等污染字符进入镜像
RUN python scripts/check_source_chars.py

# Cloud Run 通过 PORT 环境变量动态指定端口（默认 8080）
# 本地 docker run 时可传 -e PORT=8000
ENV PORT=8080

EXPOSE ${PORT}

# 使用 shell 形式以便读取运行时 $PORT
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
