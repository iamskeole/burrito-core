# ==================== Stage 1: Builder ====================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
# REMOVED: UV_SYSTEM_PYTHON=1 (This was causing the conflict)

# 1. Create and "activate" the virtual environment
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 2. Install dependencies into the venv
COPY pyproject.toml README.md* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r pyproject.toml

# 3. Pre-download Tiktoken Vocab
# We use 'uv pip' to ensure it hits the venv and then run the script
ENV TIKTOKEN_RS_CACHE_DIR=/tmp/tiktoken_cache
RUN --mount=type=cache,target=/root/.cache/uv \
    mkdir -p $TIKTOKEN_RS_CACHE_DIR && \
    uv pip install openai-harmony && \
    python -c "from openai_harmony import load_harmony_encoding, HarmonyEncodingName; load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)"

# 4. Install project source
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -e .

# ==================== Stage 2: Runtime ====================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
RUN groupadd -r burrito && useradd -r -m -g burrito -s /bin/bash burrito_user

# Copy the venv, vocab, and app
COPY --from=builder --chown=burrito_user:burrito /opt/venv /opt/venv
COPY --from=builder --chown=burrito_user:burrito /tmp/tiktoken_cache /tmp/tiktoken_cache
COPY --from=builder --chown=burrito_user:burrito /app /app

# ADD THIS: Pre-create the shared directory and fix permissions so Jupyter can write to it
RUN mkdir -p /tmp/jupyter-runtime && chown -R burrito_user:burrito /tmp/jupyter-runtime

# Ensure runtime uses the venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    TIKTOKEN_RS_CACHE_DIR=/tmp/tiktoken_cache \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

USER burrito_user

CMD ["uvicorn", "burrito.main:app", "--no-access-log", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]