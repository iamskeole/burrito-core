# ==================== Stage 1: Builder ====================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble AS builder

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -e . --root-user-action ignore

# -----------------------------------------------------------
# Pre‑download the Harmony tiktoken vocab
# -----------------------------------------------------------
# Tell openai‑harmony where to store its cache
ENV TIKTOKEN_RS_CACHE_DIR=/tmp/tiktoken_cache

# Create the cache directory, write a tiny Python script, run it,
# and then delete the temporary script.
RUN mkdir -p $TIKTOKEN_RS_CACHE_DIR && \
    echo "from openai_harmony import load_harmony_encoding, HarmonyEncodingName\nload_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)" > /tmp/precache.py && \
    python /tmp/precache.py && \
    rm /tmp/precache.py

# ==================== Stage 2: Runtime ====================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

# Copy the pre‑cached vocab into the runtime image
COPY --from=builder /tmp/tiktoken_cache /tmp/tiktoken_cache
RUN chmod -R a+rw /tmp/tiktoken_cache
ENV TIKTOKEN_RS_CACHE_DIR=/tmp/tiktoken_cache
# Copy installed packages and source code
COPY --from=builder /usr/local/lib/python3.12/dist-packages /usr/local/lib/python3.12/dist-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create and use a non‑root user
RUN groupadd -r burrito && useradd -r -m -g burrito -s /bin/bash burrito_user
RUN chmod -R a+rwX /usr/local/lib/python3.12/dist-packages /app/src
RUN apt-get update && apt-get install -y docker.io

USER burrito_user
RUN groupadd -g 999 docker || true
RUN usermod -aG docker burrito_user

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# uvicorn workers can now share the same cache directory
CMD uvicorn burrito.main:app --host 0.0.0.0 --port 8000 --workers 1
