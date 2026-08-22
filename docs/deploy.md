# Deployment

Burrito is a Python package (FastAPI + Uvicorn) that ships as a Docker image based on the official Playwright base image (Ubuntu noble).  Deployment is fully automated through Docker Compose.

## 1. Clone the repository
```bash
$ git clone https://github.com/iamskeole/burrito
$ cd burrito
```

## 2. Configure the environment
Create a ```.env``` file (or set environment variables in your shell) with the values you want.  The repository already contains a commented example:

```dotenv
# .env.example (abridged)
BACKEND_BASE_URL=http://apollo.local:9999
# BRAVE_API_KEY=
# PYTHON_BACKEND=jupyter-docker-kernels
# METRICS_AUTH_TOKEN=
```

Copy it to ```.env```:

```bash
$ cp .env.example .env
```

Adjust any values that differ for your infrastructure.  The full list of variables is in [config.md](config.md).

## 3. Build the container image
```bash
$ docker compose build burrito
$ docker compose build burrito-kernel   # only if you use PYTHON_BACKEND=jupyter-docker-kernels
```

The Dockerfile installs the package and its dependencies into a virtualenv, pre‑downloads the tokenizer vocab, and bakes in the Playwright browsers (already present in the base image).  The Uvicorn HTTP server listens on port **8000** inside the container.

## 4. Run the service
```bash
$ docker compose up -d
```

Burrito will be reachable on host port **8888** (the compose mapping is ``8888:8000``).  The compose file also bundles optional `prometheus`, `grafana`, `valkey` and `searxng` services, plus the docker‑socket‑proxy used to manage python‑kernel containers.

## 5. Verify the API
```bash
$ curl -i http://localhost:8888/live
HTTP/1.1 200 OK
{ "status": "alive" }

$ curl -i http://localhost:8888/health
HTTP/1.1 200 OK
{ "status": "ok" }
```

`/live` and `/ready` answer as soon as the app boots.  `/health` additionally probes your backend (`BACKEND_BASE_URL/v1/models`) and returns **503** — `"Backend unreachable or no models set up yet."` — until the backend is reachable and serves at least one model, so a 503 right after deployment is expected, not a failure.

OpenAI‑style agents can now point to ``http://localhost:8888`` (see [clients.md](clients.md)) and requests will be forwarded to the configured backend.

## 6. Optional: Running the backend
Burrito does not ship with a gpt‑oss model.  To test locally you can bring up a model server such as vLLM or llama.cpp.  For example, with vLLM:

```bash
$ docker run --gpus all -p 9999:9999 ghcr.io/vllm-project/vllm:latest --model openai/gpt-oss-20b
```

With the backend listening on ``127.0.0.1:9999`` (or set a different port in ``BACKEND_BASE_URL``) Burrito will forward inference requests to it.

---

For advanced deployment scenarios (Kubernetes, …) consult the FastAPI and Uvicorn documentation.
