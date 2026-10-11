# syntax=docker/dockerfile:1
#
# Production image for Hire AI: the FastAPI app served by uvicorn.
#
#   docker build -t hireai .
#   docker run --rm -p 8000:8000 --env-file .env hireai
#
# - Installs requirements.txt only. requirements-eval.txt and requirements-mcp.txt are never installed.
# - The embedding model (sentence-transformers/all-MiniLM-L6-v2) is downloaded at build time into
#   HF_HOME, so the container runs with HF_HUB_OFFLINE=1 and never contacts the Hugging Face Hub.
# - No secrets are baked in: DATABASE_URL and GOOGLE_API_KEY come from the environment
#   at run time (docker-compose.yml reads .env; Cloud Run reads Secret Manager).

ARG PYTHON_IMAGE=python:3.12-slim

# ---------------------------------------------------------------------------------------------
# Builder: a virtual environment with the core requirements, plus the pre-downloaded model.
# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf-cache

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# CPU-only PyTorch first, so sentence-transformers doesn't pull the multi-gigabyte CUDA build.
# The app never uses a GPU. pip then treats torch as already satisfied.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Download the embedding model with the app's own loader, so the cached name is exactly the one
# scorer.py asks for (config.EMBEDDING_MODEL). Fails the build if the model can't be loaded.
WORKDIR /build
COPY config.py scorer.py ./
RUN HF_HUB_OFFLINE=0 python -c "import scorer; assert scorer.load_embedding_model() is not None, 'model download failed'" \
 && rm -rf /opt/hf-cache/xet /opt/hf-cache/hub/.locks

# ---------------------------------------------------------------------------------------------
# Runtime: the venv, the model cache and the app, running as a non-root user.
# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# Writable state lives under /app/data and /app/uploads; the code itself is read-only.
# DATABASE_URL here is only a fallback for a bare `docker run`: compose and Cloud Run set PostgreSQL.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/opt/hf-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    PORT=8000 \
    DATABASE_URL=sqlite:////app/data/recruiting_agent.db \
    AGENT_CHECKPOINT_DB=/app/data/agent_checkpoints.db

RUN groupadd --system --gid 10001 hireai \
 && useradd --system --uid 10001 --gid hireai --home-dir /home/hireai --create-home --shell /usr/sbin/nologin hireai

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=hireai:hireai /opt/hf-cache /opt/hf-cache

WORKDIR /app
# Application code, owned by root and read-only to the app user. .dockerignore keeps out .env,
# databases, uploads, tests, eval, docs and sample data.
COPY . .
RUN mkdir -p /app/uploads /app/data \
 && chown hireai:hireai /app/uploads /app/data

USER hireai

# Prove the model loads offline, as the app user, from the baked-in cache.
RUN python -c "import scorer; assert scorer.load_embedding_model() is not None, 'model not in HF_HOME'"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)" || exit 1

# Shell form so ${PORT} expands (Cloud Run sets PORT=8080); exec makes uvicorn PID 1, so it gets
# SIGTERM directly and shuts down gracefully. Migrations run when app/db.py creates the engine.
CMD ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
