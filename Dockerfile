# === STAGE 1: The Builder ===
# We use the official Rust image because wasmer is written in Rust,
# guaranteeing all necessary build tools (like Clang, Rustc) are present.
FROM rust:1.77 AS builder

# 1. Install system dependencies for Python and the Wasmer runtime
RUN apt-get update && apt-get install -y \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 2. Install the Wasmer system runtime
ENV WASMER_DIR=/root/.wasmer
ENV PATH="${WASMER_DIR}/bin:${PATH}"
RUN curl https://get.wasmer.io -sSfL | sh

# 3. Create and activate a Python virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 4. Install the wasmer v4 Python packages
# This is now running in a controlled environment where it is guaranteed to work.
RUN pip install "wasmer[wasi]>=4.0.0" "wasmer-compiler-cranelift>=4.0.0"

# 5. Download the python.wasm module using the just-installed runtime
RUN wasmer install python/python --out /opt/python.wasm


# === STAGE 2: The Final Production Image ===
# Start from a clean, lightweight Python image
FROM python:3.11-slim-bookworm

WORKDIR /app

# 1. Copy the Wasmer system runtime from the builder stage
ENV WASMER_DIR=/root/.wasmer
ENV PATH="${WASMER_DIR}/bin:${PATH}"
COPY --from=builder ${WASMER_DIR} ${WASMER_DIR}

# 2. Copy the Python virtual environment (with all packages) from the builder stage
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# 3. Copy the downloaded python.wasm module from the builder stage
COPY --from=builder /opt/python.wasm ./python.wasm

# 4. Copy your application's source code
COPY . .

# 5. Define the command to run your application
CMD ["python", "my_project/main.py"]