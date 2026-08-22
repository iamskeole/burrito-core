# ==================== Stage 1: Builder ====================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
# REMOVED: UV_SYSTEM_PYTHON=1 (This was causing the conflict)

# 1. Create and "activate" the virtual environment
#    (uv sync targets the same location via UV_PROJECT_ENVIRONMENT)
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# 2. Install dependencies into the venv (from the lockfile, project itself later)
COPY pyproject.toml uv.lock .python-version README.md* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    uv sync --frozen --no-install-project

# 3. Pre-download tokenizer vocabs so the runtime container never needs
#    egress for them: openai-harmony (harmoney/gpt-oss encoding) uses
#    TIKTOKEN_RS_CACHE_DIR, the tiktoken package (gpt-oss's page-content
#    token capping) uses TIKTOKEN_CACHE_DIR
ENV TIKTOKEN_RS_CACHE_DIR=/tmp/tiktoken_cache \
    TIKTOKEN_CACHE_DIR=/tmp/tiktoken_cache
RUN --mount=type=cache,target=/root/.cache/uv \
    mkdir -p $TIKTOKEN_RS_CACHE_DIR && \
    python -c "from openai_harmony import load_harmony_encoding, HarmonyEncodingName; load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)" && \
    python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

# 4. Install project source (editable, into the same venv)
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# ==================== Stage 2: Runtime ====================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

WORKDIR /app
RUN (userdel -r ubuntu || true) && \
    (userdel -r pwuser || true) && \
    (groupdel ubuntu || true) && \
    (groupdel pwuser || true) && \
    groupadd -g 1000 burrito && \
    useradd -m -u 1000 -g burrito -s /bin/bash burrito_user

# Copy the venv, vocab, and app
COPY --from=builder --chown=burrito_user:burrito /opt/venv /opt/venv
COPY --from=builder --chown=burrito_user:burrito /tmp/tiktoken_cache /tmp/tiktoken_cache
COPY --from=builder --chown=burrito_user:burrito /app /app

# ADD THIS: Pre-create the shared directory and fix permissions so Jupyter can write to it
RUN mkdir -p /tmp/jupyter-runtime && chown -R burrito_user:burrito /tmp/jupyter-runtime

# Ensure runtime uses the venv
# (PLAYWRIGHT_BROWSERS_PATH is inherited from the base image: /ms-playwright)
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    TIKTOKEN_RS_CACHE_DIR=/tmp/tiktoken_cache \
    TIKTOKEN_CACHE_DIR=/tmp/tiktoken_cache \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

USER burrito_user

CMD ["uvicorn", "burrito.main:app", "--no-access-log", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]