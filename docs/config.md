# Configuration

Burrito exposes all its behaviour through environment variables.  A complete list of supported variables is defined in :py:class:`burrito.common.config.Settings`.  Each variable has a sensible default that is used when the variable is not supplied.

## Core behaviour
- **``BACKEND_BASE_URL``** – Base URL of the LLM backend (required).  It must omit the ``/v1`` prefix; the default points to ``http://127.0.0.1:6379``.
- **``SEARXNG_API_URL``** – Endpoint for the self‑hosted SearXNG search service.  When blank **and** ``BRAVE_API_KEY`` is empty, the ``browser.search`` tool is disabled.
- **``BRAVE_API_KEY``** – Public API key for Brave Search.  When supplied it overrides SearXNG for the search tool.
- **``MAX_REQUEST_BODY_SIZE``** – Maximum POST payload size in bytes (default 1 MiB).  Requests larger than this are rejected with a 413.
- **``MAX_CONCURRENT_INFERENCE_REQUESTS``** – Number of concurrent inferences that a single Uvicorn worker will handle.
- **``MAX_RECOVER_STATE_ATTEMPTS``** – How many retries Burrito will perform when a state recovery message fails.

## Tool configuration
- **``IS_BROWSER_TOOL_ENABLED``** – Enable the native browser tool.  Defaults to ``true``.
- **``IS_PYTHON_TOOL_ENABLED``** – Enable the native Python tool.  Defaults to ``true``.
- **``PREFERRED_BROWSER``** – If set, the browser will prefer that browser engine.
- **``BROWSER_TIMEOUT_FETCH``** – Timeout for page fetches (seconds).
- **``BROWSER_TIMEOUT_SEARCH``** – Timeout for web‑search calls (seconds).

## Logging & metrics
- **``LOG_LEVEL``** – Logging level (``debug``, ``info``, ``warning`` …).
- **``METRICS_AUTH_TOKEN``** – When set, the `/metrics` endpoint requires a matching Bearer token.  Leaving it empty disables authentication.
- **``METRICS_IP_WHITELIST``** – Comma‑separated IPs allowed to access `/metrics`.

## CORS policy
CORS settings are driven by ``CORS_ALLOWED_ORIGINS``, ``CORS_ALLOWED_METHODS`` and ``CORS_ALLOWED_HEADERS``.  Each defaults to ``*``.

## Example – .env file
```dotenv
BACKEND_BASE_URL=http://localhost:6379
SEARXNG_API_URL=http://localhost:9090
BRAVE_API_KEY=
MAX_REQUEST_BODY_SIZE=1048576
```

The repository also provides a `docker-compose.yml` that demonstrates the basic environment variable substitution.

---

For a full listing of settings and their defaults see the source of :py:class:`~burrito.common.config.Settings`.
