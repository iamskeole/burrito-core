from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = PROJECT_ROOT / ".env"


def list_from_cfg(val: str, fallback: str) -> list[str]:
    return [
        v
        for v in val.replace("; ", ";").replace(", ", ",").replace(";", ",").split(",")
        if v
    ] or [fallback]


class Settings(BaseSettings):
    HOST: str = Field(
        default="0.0.0.0", description="IP address to bind the HTTP server."
    )
    PORT: int = Field(default=8000, description="Port number for the HTTP server.")

    LOG_LEVEL: str = Field(
        default="debug", description="Logging level for the application."
    )
    ACCESS_LOG: bool = Field(
        default=False, description="Emit access logs for HTTP requests."
    )

    DEBUG_TOOL_CALLS: bool = Field(
        default=False, description="Log raw tool calls sent to external tools."
    )
    DEBUG_TOOL_INPUTS: bool = Field(
        default=False, description="Log raw inputs sent to external tools."
    )
    DEBUG_TOOL_OUTPUTS: bool = Field(
        default=False, description="Log raw outputs received from external tools."
    )
    DEBUG_COMPLETIONS: bool = Field(
        default=False, description="Log the final LLM completions."
    )
    DEBUG_PROMPT: bool = Field(
        default=False, description="Log the conversation prompt."
    )
    DEBUG_OUTGOING_EVENTS: bool = Field(
        default=False, description="Log events sent to a client via SSE."
    )
    DEBUG_RESPONSE_BUFFER: bool = Field(
        default=False, description="Persist the in-memory response buffer."
    )
    DEBUG_STATE_CHANGE: bool = Field(
        default=False, description="Log state transition events."
    )
    DEBUG_HARMONY_ERRORS: bool = Field(
        default=False, description="Log unhandled Harmony (LLM) errors."
    )
    DEBUG_BROWSER_ERRORS: bool = Field(
        default=False, description="Log browser tool errors."
    )
    DEBUG_STATE_ERRORS: bool = Field(
        default=False, description="Log state management errors."
    )
    DEBUG_CLIENT_DISCONNECTS: bool = Field(
        default=False, description="Log client disconnect events."
    )
    DEBUG_GENERATOR_CLEANUP: bool = Field(
        default=False, description="Log cleanup actions performed by the generator."
    )

    CORS_ALLOWED_ORIGINS: str = Field(
        default="*",
        description="Comma or semicolon separated list of origins allowed by CORS.",
    )
    CORS_ALLOWED_METHODS: str = Field(
        default="*",
        description="Comma or semicolon separated list of HTTP methods allowed by CORS.",
    )
    CORS_ALLOWED_HEADERS: str = Field(
        default="*",
        description="Comma or semicolon separated list of HTTP headers allowed by CORS.",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Allow browsers to send credentials on cross origin requests.",
    )

    MAX_REQUEST_BODY_SIZE: int = Field(
        default=1048576 * 1,
        description="Maximum HTTP request body size in bytes.",
    )
    MAX_CONCURRENT_INFERENCE_REQUESTS: int = Field(
        default=16,
        description="Maximum simultaneous inference requests; excess FIFO queued.",
    )

    BACKEND_BASE_URL: str = Field(
        default="http://127.0.0.1:6379",
        description="Base URL of the underlying LLM backend. Do NOT include the /v1 suffix, only host and port.",
    )
    BACKEND_INTER_TOKEN_TIMEOUT: int = Field(
        default=120,
        description="Timeout (seconds) for long tokenization or preprocessing.",
    )
    BACKEND_FORWARD_HEADERS: str = Field(
        default="Authentication,X-Api-Key",
        description="Comma or semicolon separated headers forwarded to the backend.",
    )

    DEFAULT_MODEL_NAME: str = Field(
        default="openai/gpt-oss-20b",
        description="Default model identifier used for inference.",
    )
    DEFAULT_MODEL_CTX_LEN: int = Field(
        default=131072,
        description="Default maximum context length for the model.",
    )

    DEFAULT_REASONING_EFFORT: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Default reasoning effort.",
    )
    DEFAULT_REASONING_SUMMARY: Literal["auto", "concise", "detailed"] = Field(
        default="auto",
        description="Default summarisation mode for reasoning outcomes. Not yet implemented.",
    )

    MODEL_IDENTITY: str = Field(
        default="v1",
        description="Model identity / personality that gets built into the system prompt.",
    )

    MAX_RECOVER_STATE_ATTEMPTS: int = Field(
        default=100,
        description="Maximum attempts to recover a corrupted inference state.",
    )
    MAX_REASONING_LOOPS: int = Field(
        default=1000,
        description="Maximum number of reasoning loops before triggering a state recovery.",
    )

    ENFORCE_STRICT_TOOL_NAMESPACES: bool = Field(
        default=False,
        description="Require tool names to be fully qualified namespaces.",
    )
    CLEANUP_LOW_PRECISION_PROMPT_TIMESTRINGS: bool = Field(
        default=True,
        description="Remove granular timestamps (eg: 12:42:23) from prompts. These mess up prompt caching with no added benefit.",
    )

    IS_PYTHON_TOOL_ENABLED: bool = Field(
        default=True, description="Enable the native Python tool."
    )
    IS_BROWSER_TOOL_ENABLED: bool = Field(
        default=True, description="Enable the native browser tool."
    )

    IS_PYTHON_TOOL_ALWAYS_ENABLED: bool = Field(
        default=True,
        description="Always enable Python tool without caller tool list gymnastics.",
    )
    IS_BROWSER_TOOL_ALWAYS_ENABLED: bool = Field(
        default=True,
        description="Always enable browser tool without caller tool list gymnastics.",
    )

    PYTHON_BACKEND: Literal["docker", "dangerously_use_local_jupyter"] = Field(
        default="docker",
        description="Backend used to execute Python code.",
    )

    BROWSER_TIMEOUT_FETCH: int = Field(
        default=3,
        description="Timeout (seconds) for browser fetch operations.",
    )
    BROWSER_TIMEOUT_SEARCH: int = Field(
        default=10,
        description="Timeout (seconds) for browser search operations.",
    )
    BROWSER_LOCALE: str = Field(
        default="en-GB",
        description="Locale setting used by browser operations. Also prompts the model to use this as a default.",
    )
    BROWSER_LANGUAGE: str = Field(
        default="en",
        description="Preferred language for browser operations. Also prompts the model to use this as a default.",
    )
    BROWSER_TIMEZONE: str = Field(
        default="Europe/London",
        description="Timezone for browser timestamps.",
    )
    BROWSER_SESSION_CACHE_SIZE: int = Field(
        default=1024,
        description="Maximum number of browser session objects cached in the browser engine singleton.",
    )

    BRAVE_API_KEY: str = Field(
        default="", description="API key for the Brave search engine."
    )
    BRAVE_API_URL: str = Field(
        default="https://api.search.brave.com/res/v1/web/search",
        description="Endpoint URL for the Brave search API.",
    )

    SEARXNG_API_URL: str = Field(
        default="", description="Endpoint URL for the SearXNG search API."
    )

    METRICS_AUTH_TOKEN: str = Field(
        default="BURRITO_AUTH_DEV",
        description="Bearer token required for accessing the /metrics endpoint; empty disables filtering.",
    )
    METRICS_IP_WHITELIST: str = Field(
        default="",
        description="Comma or semicolon separated IP whitelist for metrics access; empty disables filtering.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()  # type: ignore[reportCallIssue]
