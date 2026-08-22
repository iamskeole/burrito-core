# burrito

A batteries-included inference harness for gpt-oss.

## What

Burrito is a drop-in replacement for the **OpenAI** and **Anthropic** APIs, backed by a gpt-oss model. It accepts standard requests on `/v1/chat/completions`, `/v1/responses`, and `/v1/messages` (JSON and streamed, including standard wire events where applicable) and delegates next-token prediction to an existing inference backend — **llama.cpp** or **vLLM** — over `/v1/completions`. It does not ship a model.

## Why

gpt-oss was trained with native `python` and `browser` tools and to work in distinct "channels" — interleaving reasoning, tool calls, and backtracking into reasoning before a final answer. Existing inference engines handle this pattern with compromises:

- **llama.cpp** implements both OpenAI endpoints plus an Anthropic-compatible `/v1/messages`, but forces tool calls through grammars and a hardcoded `functions.` prefix. That buys high tool-call success, but the model's native `python` / `browser.*` namespaces cannot be used (they are trained under their own names, not `functions.python` / `functions.browser`), and jinja failures end generation immediately.
- **vLLM** has working tool calling on the OpenAI endpoints, but no `/v1/messages` for Anthropic-compatible clients, no recovery from malformed output, and python/browser support only in a separate demo server that defaults to commercial browser APIs — meaning API fees and third-party data.

Burrito fills the other side of that specialization: it is a model-specific harness that renders conversations the way the model was trained to read them, executes the native `python` and `browser` tools inside the same process (no separate servers), recovers from hallucinated tool calls by telling the model where it went wrong — the model is smart enough to correct itself — and exposes production health checks and Prometheus metrics.

## How

- **Inference pipeline** — requests are tokenized and rendered with the harmony encoding, streamed from the backend, and guarded by repetition-loop detection and automatic state recovery from malformed tool calls.
- **Browser tool** — `browser.open` runs on a bundled Playwright engine (browsers are baked into the image, so nothing is downloaded at build or runtime); `browser.search` runs on a bundled SearXNG instance (the Brave API is an optional alternative).
- **Python tool** — Jupyter kernels run in-process by default, or in isolated, pre-warmed `burrito-kernel` containers managed through the bundled docker-socket-proxy when you want per-session isolation.
- **Deployment** — a single `docker-compose.yml` ships the app with SearXNG, Valkey, Prometheus, and Grafana; remove the services you do not need.

**Rule of thumb:** use llama.cpp when you want maximum single-threaded speed and do not need the native tools; use burrito when you want native python/browser tools, Anthropic-compatible endpoints, and parallel request handling, on either backend.

## Installation

> **Prerequisites**: Docker with Compose v2 (a running docker daemon on the host), and a gpt-oss inference backend (llama.cpp or vLLM) that the docker host can reach. Burrito does not ship a model.

1. clone this repo

```bash
git clone https://github.com/iamskeole/burrito && cd burrito
```

2. configure it. The cleanest way is a `.env` file (docker-compose reads it for `${...}` interpolation) — the repo ships a commented example:

```bash
cp .env.example .env
nano .env
```

> At minimum, set `BACKEND_BASE_URL` to your inference backend (eg. `http://your-backend:9999`, no trailing `/v1`); it must be reachable from the docker host. Everything else has sane defaults — the full list is in [`config.py`](/src/burrito/common/config.py).
>
> Comment out or remove any of the `prometheus`, `grafana`, `valkey`, `searxng` services in [`docker-compose.yml`](/docker-compose.yml) if you already host them yourself; otherwise the compose file bundles everything together.

3. build the images

```bash
docker compose build burrito
docker compose build burrito-kernel   # only needed if you use PYTHON_BACKEND=jupyter-docker-kernels
```

> Note: the `burrito-kernel` service is build-only and profile-gated, so the usual `up --build` never builds it — build it explicitly as above. The main image is based on the official Playwright image: the browser binaries are baked in and the python `playwright` package is pinned to the matching version, so no browser download happens at build or runtime. The tokenizer vocabulary is also pre-downloaded at build time, so a deployed container needs no network access for it.

4. run

```bash
docker compose up -d
docker compose logs -f burrito
```

> The API is on host port **8888** (container 8000). `/live` and `/ready` answer 200 as soon as the app boots; `/health` only returns 200 once it can reach your backend **and** sees at least one model — a 503 with `"Backend unreachable or no models set up yet."` before that is expected, not a crash.

5. point your client at burrito

```bash
# client / caller config (or ANTHROPIC_BASE_URL etc. — see docs/clients.md)
export OPENAI_BASE_URL="http://<burrito-host>:8888"
```

### Isolated python kernels

By default the python tool runs Jupyter kernels **in-process** inside the burrito container. For isolated, per-session kernel containers:

1. build the kernel image (step 3)
2. uncomment `PYTHON_BACKEND=jupyter-docker-kernels` in [`docker-compose.yml`](/docker-compose.yml) (or export it) and `docker compose up -d` again

Burrito then manages `burrito-kernel` containers itself through the bundled docker-socket-proxy: kernels are pre-warmed (default 2), get their own container on the `burrito-internal` network, and are reachable over that network's DNS. Kernels keep normal internet access on that network, matching the app itself: the python tool's description tells the model whether installing packages is possible (the app probes wikipedia at boot and refreshes the answer periodically). If you want the kernels isolated from the internet instead, add `internal: true` back to the `burrito-internal` network in the compose file — the offline description will then apply and agent code can only use the preinstalled numpy/pandas/sympy. If you get `a network with name burrito-internal exists but was not created by compose`, remove the stale network first: `docker network rm burrito-internal`.

### Debugging

[`docker-compose.test.yml`](/docker-compose.test.yml) layers on top of the main compose file for development: it mounts the live code into the container, installs `debugpy` at boot, blocks until a VS Code debug client attaches on port **5678** (see `.vscode/launch.json`), and then starts Uvicorn with `--reload`:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build -d
```

## Licenses

This project depends on a minimal number of open-source libraries. All packages have permissive licenses except for the SearXNG and Grafana Docker images, which are AGPL-3.0; the Docker image also embeds Playwright's browsers (Chromium, Firefox, WebKit) under their respective open-source licenses. Detailed license information is available in [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
