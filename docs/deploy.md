# Deployment

Burrito is distributed as a single‑file Python package that ships with an Alpine Linux container.  Deployment is fully automated through Docker Compose.

## 1. Clone the repository
```bash
$ git clone https://github.com/iamskeole/burrito
$ cd burrito
```

## 2. Configure the environment
Create a ```.env``` file (or set environment variables in your shell) with the values you want.  The repository already contains a minimal example:

```dotenv
# .env.example
BACKEND_BASE_URL=http://localhost:6379
SEARXNG_API_URL=http://localhost:9090
BRAVE_API_KEY=
```

Copy it to ```.env```:

```bash
$ cp .env.example .env
```

Adjust any values that differ for your infrastructure.

## 3. Build the container image
```bash
$ docker compose build
```

The Dockerfile pulls a minimal Python image, installs the package and makes the Uvicorn HTTP server listen on port **80** inside the container.

## 4. Run the service
```bash
$ docker compose up -d
```

Burrito will be reachable on the host port specified under ``ports`` in the compose file.  The default mapping is ``8000:80``.

## 5. Verify the API
```bash
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{ "status": "ok" }
```

OpenAI‑style agents can now point to ``http://localhost:8000`` and forward requests to underlying backends.

## 6. Optional: Running the backend
Burrito does not ship with an LLM backend.  To test locally you can bring up a lightweight model server such as VLLM or llama.cpp.  For example, with VLLM:

```bash
$ docker run --gpus all -p 6379:8000 ghcr.io/vllm-project/vllm:latest --model mistralai/Mistral-7B-v0.1
```

With the backend listening on ``127.0.0.1:6379`` Burrito will automatically forward inference requests to it.

---

For advanced deployment scenarios (Kubernetes, …) consult the FastAPI and Uvicorn documentation.
