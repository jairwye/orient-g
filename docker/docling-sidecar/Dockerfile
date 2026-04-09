# syntax=docker/dockerfile:1
# 参照官方：https://github.com/docling-project/docling/blob/main/Dockerfile
# 差异：Python 3.12；额外安装 FastAPI/uvicorn（侧车 HTTP）；保留可选 PIP_INDEX_URL 构建参数。
# 基础镜像钉 bookworm，避免 python:3.12-slim 漂到 trixie 时 apt 拉 mesa/llvm 更易触发构建 OOM。
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=600 \
    HF_HOME=/tmp/ \
    TORCH_HOME=/tmp/ \
    OMP_NUM_THREADS=4

ARG PIP_INDEX_URL=
ARG PIP_EXTRA_INDEX_URL=
# 可选：Debian apt 镜像根（无尾斜杠），如 https://mirrors.tuna.tsinghua.edu.cn；用于缓解 deb.debian.org 慢/断连
ARG DEBIAN_MIRROR=
ARG USE_LOCAL_WHEELS=0
# 默认 1：跳过构建期 docling-tools models download（需 Hugging Face 联网，内网/被墙环境易失败）；设为 0 则与官方一致预下载模型（镜像更大）
ARG SKIP_MODEL_DOWNLOAD=1

# 与官方一致的运行时包（含 curl/wget/git/procps）；若设 DEBIAN_MIRROR 则先替换 sources 再 apt-get update
RUN set -eux; \
    if [ -n "$DEBIAN_MIRROR" ]; then \
      for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do \
        [ -f "$f" ] || continue; \
        sed -i -E "s|https?://deb\\.debian\\.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" "$f"; \
        sed -i -E "s|https?://deb\\.debian\\.org/debian|${DEBIAN_MIRROR}/debian|g" "$f"; \
      done; \
    fi; \
    apt-get update \
    && apt-get install -y libgl1 libglib2.0-0 curl wget git procps \
    && rm -rf /var/lib/apt/lists/*

# 可选：构建时注入 PyPI 镜像（仅影响本镜像构建期的 pip）
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "$PIP_INDEX_URL" ]; then pip config set global.index-url "$PIP_INDEX_URL"; fi && \
    if [ -n "$PIP_EXTRA_INDEX_URL" ]; then pip config set global.extra-index-url "$PIP_EXTRA_INDEX_URL"; fi

COPY requirements.txt ./requirements.txt

# 若存在本地 wheels 目录且显式启用 USE_LOCAL_WHEELS=1，则优先使用离线 wheels；
# 否则走在线安装路径（含 PyTorch CPU wheel 源）。两种路径都复用 BuildKit pip 缓存。
COPY vendor/docling-wheels/ /wheels/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    if [ "$USE_LOCAL_WHEELS" = "1" ] && [ -d /wheels ]; then \
        pip install --no-index --find-links=/wheels \
            -r requirements.txt \
            --extra-index-url https://download.pytorch.org/whl/cpu; \
    else \
        pip install --retries 30 --default-timeout 600 --progress-bar off --prefer-binary \
            -r requirements.txt \
            --extra-index-url https://download.pytorch.org/whl/cpu; \
    fi

# 可选：预下载模型（SKIP_MODEL_DOWNLOAD=0 时执行；默认跳过，运行时首次解析再拉或挂载缓存）
RUN if [ "$SKIP_MODEL_DOWNLOAD" = "1" ]; then \
      echo "SKIP_MODEL_DOWNLOAD=1: skipping docling-tools models download"; \
    else \
      docling-tools models download; \
    fi

COPY main.py ./main.py

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
