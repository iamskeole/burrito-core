# Configuration

Burrito exposes all its behaviour through environment variables.  A complete list of supported variables is defined in :py:class:`burrito.common.config.Settings`.  Each variable has a sensible default that is used when the variable is not supplied.

## Core behaviour
- **``BACKEND_BASE_URL``** – Base URL of the LLM backend (required in practice).  It must omit the ``/v1`` prefix; the default points to ``http://127.0.0.1:9999``.
- **``SEARXNG_API_URL``** – Endpoint for the self‑hosted SearXNG search service (``browser.search`` fallback).  The compose file points this at the bundled SearXNG container (``http://searxng:8080``).  When blank **and** ``BRAVE_API_KEY`` is empty, the ``browser.search`` tool is disabled.
- **``BRAVE_API_KEY``** – Public API key for Brave Search.  When supplied it takes priority over SearXNG for the search tool.
- **``MAX_REQUEST_BODY_SIZE``** – Maximum POST payload size in bytes (default 1 MiB).  Requests larger than this are rejected with a 413.
- **``MAX_CONCURRENT_INFERENCE_REQUESTS``** – Number of concurrent inferences that a single Uvicorn worker will handle.
- **``MAX_RECOVER_STATE_ATTEMPTS``** – How many retries Burrito will perform when a state recovery message fails.

## Tool configuration
- **``IS_BROWSER_TOOL_AVAILABLE``** – Make the native browser tool available to the model.  Defaults to ``true`` (``IS_BROWSER_TOOL_ALWAYS_ENABLED`` forces it on without caller opt‑in).
- **``IS_PYTHON_TOOL_AVAILABLE``** – Make the native Python tool available to the model.  Defaults to ``true`` (``IS_PYTHON_TOOL_ALWAYS_ENABLED`` as above).
- **``BROWSER_BACKEND``** – Page fetch engine: ``playwright`` (default, headless Chromium) or ``httpx`` (plain GET).
- **``PYTHON_BACKEND``** – Python execution mode: ``jupyter-in-process`` (default, kernels inside the burrito container) or ``jupyter-docker-kernels`` (isolated ``burrito-kernel`` containers managed via the docker socket proxy; ``DOCKER_HOST`` is set in the compose file).  With docker kernels, ``PYTHON_KERNEL_MIN_POOL_SIZE`` (default 2) keeps that many pre‑warmed. Docker kernels run on the compose ``burrito-internal`` network, which has normal internet egress by default (set ``internal: true`` on that network in the compose file to remove it).
- **``BROWSER_TIMEOUT_FETCH``** – Timeout for page fetches (seconds).
- **``BROWSER_TIMEOUT_SEARCH``** – Timeout for web‑search calls (seconds).

> Note: ``HOST`` and ``PORT`` exist in the Settings class but are not used by the container deployment — the image's command line pins Uvicorn to ``0.0.0.0:8000`` and the compose file maps host port 8888 to it.

## Logging & metrics
- **``LOG_LEVEL``** – Logging level (``debug``, ``info``, ``warning`` …).
- **``METRICS_AUTH_TOKEN``** – When set, the `/metrics` endpoint requires a matching Bearer token.  Leaving it empty disables authentication.
- **``METRICS_IP_WHITELIST``** – Comma‑separated IPs allowed to access `/metrics`.

## CORS policy
CORS settings are driven by ``CORS_ALLOWED_ORIGINS``, ``CORS_ALLOWED_METHODS`` and ``CORS_ALLOWED_HEADERS``.  Each defaults to ``*``.

## Example – .env file
```dotenv
BACKEND_BASE_URL=http://apollo.local:9999
# SEARXNG_API_URL=http://searxng:8080   (default when using the compose stack)
# BRAVE_API_KEY=
MAX_REQUEST_BODY_SIZE=1048576
```

The repository also provides a `docker-compose.yml` that demonstrates the basic environment variable substitution.

---

For a full listing of settings and their defaults see the source of :py:class:`~burrito.common.config.Settings`.
