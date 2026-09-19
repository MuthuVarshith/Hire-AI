FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Hugging Face Spaces runs containers as UID 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# CPU-only torch first; otherwise sentence-transformers pulls the multi-GB CUDA build.
COPY --chown=user requirements.txt .
RUN pip install --user torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --user -r requirements.txt gunicorn

# Bake the embedding model into the image so startup doesn't download it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY --chown=user . .
RUN mkdir -p data/uploads

# HF_HUB_OFFLINE: the model is already in the image; skip update checks at startup.
ENV DATABASE_URL=sqlite:////home/user/app/data/recruiting_agent.db \
    UPLOAD_FOLDER=/home/user/app/data/uploads \
    PRELOAD_MODEL=1 \
    HF_HUB_OFFLINE=1 \
    PORT=7860

EXPOSE 7860

# One worker: SQLite has a single writer and each worker would load its own model copy.
CMD ["sh", "-c", "exec gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 180"]
