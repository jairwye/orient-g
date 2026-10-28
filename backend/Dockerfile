FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# 生产 backend 不打包 docling（解析由 docker/docling-sidecar 承担，见 DOCLING_MODE=http）
# 默认国内 PyPI 镜像；海外可 --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY backend/requirements-base.txt ./requirements.txt
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" -r requirements.txt

COPY backend/ ./backend/
COPY .env.example .env
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
