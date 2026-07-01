# ── Stage 1: Python dependencies ─────────────────────────────────────────────
# Use slim image — smaller than full python image
FROM python:3.13-slim AS builder

WORKDIR /app

# Install system dependencies needed to compile some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .

# torch CPU-only is huge — install it separately with the CPU index
# This avoids pulling in CUDA (~3GB) when we only need CPU inference
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.6.0\
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt


RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2'); \
print('Embedding model cached.')"


# ── Stage 2: Final runtime image ─────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Runtime system deps only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin


# Copy HuggingFace model cache from builder
# Model is stored in root's home during build — copy to app directory
COPY --from=builder /root/.cache/huggingface /root/.cache/huggingface

# Copy Django project code
# manage.py lives inside fixit_backend/ subfolder
COPY fixit_backend/ .

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create directories for static and media files
RUN mkdir -p /app/staticfiles /app/media

# Don't run as root in production
RUN useradd --no-create-home --shell /bin/false appuser && \
    mkdir -p /home/appuser/.cache && \
    chown -R appuser:appuser /app /entrypoint.sh \
                             /home/appuser \
                             /root/.cache/huggingface

USER appuser

ENV HF_HOME=/root/.cache/huggingface

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]