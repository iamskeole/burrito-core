from pathlib import Path
from typing import Literal, Optional

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
        default="127.0.0.1", description="IP address to bind the HTTP server."
    )
    PORT: int = Field(default=8888, description="Port number for the HTTP server.")

    LOG_LEVEL: str = Field(
        default="debug", description="Logging level for the application."
    )

    # debug prints
    DEBUG_REASONING_EFFORT: bool = Field(
        default=True, description="Log reasoning effort."
    )
    DEBUG_TOOL_CALLS: bool = Field(default=True, description="Log tool names.")
    DEBUG_TOOL_INPUTS: bool = Field(default=False, description="Log tool inputs.")
    DEBUG_TOOL_OUTPUTS: bool = Field(default=False, description="Log tool outputs.")
    DEBUG_COMPLETIONS: bool = Field(
        default=False,
        description="Log completion events received from inference backend.",
    )
    DEBUG_PROMPT: bool = Field(
        default=False,
        description="Log the conversation prompt before Harmony tokenization.",
    )
    DEBUG_OUTGOING_EVENTS: bool = Field(
        default=False, description="Log SSE events sent to clients."
    )
    DEBUG_RESPONSE_BUFFER: bool = Field(
        default=False,
        description="Persist the in-memory response buffer. Includes state recovery messages.",
    )
    DEBUG_STATE_CHANGE: bool = Field(
        default=False, description="Log state transition events."
    )
    DEBUG_HARMONY_ERRORS: bool = Field(
        default=True, description="Log unhandled Harmony errors."
    )
    DEBUG_BROWSER_ERRORS: bool = Field(
        default=True, description="Log browser tool errors."
    )
    DEBUG_STATE_ERRORS: bool = Field(
        default=True, description="Log state management errors."
    )
    DEBUG_CLIENT_DISCONNECTS: bool = Field(
        default=True, description="Log client disconnect events."
    )
    DEBUG_GENERATOR_CLEANUP: bool = Field(
        default=True, description="Log cleanup actions performed by the generator."
    )
    DEBUG_SESSION_CACHE: bool = Field(
        default=True, description="Log cache operations inside SessionCache."
    )
    DEBUG_SESSION_SENTINEL_HEARTBEAT: bool = Field(
        default=False,
        description="Log tick / tock heartbeats for SessionHandler tool cleanup sentinel.",
    )
    DEBUG_KERNEL_OPERATIONS: bool = Field(
        default=True,
        description="Log operations performed by the KernelHandler to manage Jupyter kernels in docker.",
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
        description="Maximum simultaneous inference requests per uvicorn worker process; excess FIFO queued.",
    )

    BACKEND_BASE_URL: str = Field(
        default="http://127.0.0.1:9999",
        description="Base URL of the underlying LLM backend. Do NOT include the /v1 suffix, only host and port.",
    )
    BACKEND_INTER_TOKEN_TIMEOUT: int = Field(
        default=120,
        description="Timeout (seconds) to allow for long prompt preprocessing.",
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
        default="default",
        description="Model personality prompt that gets built into the system prompt.",
    )

    MAX_REASONING_TOKENS: int = Field(
        default=128000,
        description="Default maximum reasoning tokens budget before brain surgery to output NOW. Setting this to 0 is experimental, it forces model to skip output on analysis channel straight to final (ie no reasoning).",
    )
    MAX_REASONING_LOOPS: int = Field(
        default=100,
        description="Maximum number of reasoning loops before triggering a state recovery.",
    )
    MAX_PREAMBLE_LOOPS: int = Field(
        default=100,
        description="Maximum number of preamble loops before triggering a state recovery.",
    )
    REPETITION_WINDOW_SIZE: int = Field(
        default=64,
        description=(
            "The maximum number of recent, normalized sentences to keep in the history buffer. "
            "A larger window allows the detector to catch longer, highly complex reasoning loops "
            "(limit cycles) without impacting performance."
        ),
    )
    REPETITION_MIN_FOOTPRINT: int = Field(
        default=32,
        description=(
            "The minimum total footprint of repeating sentences required to trigger an abort. "
            "Uses an adaptive threshold: a 1-sentence loop must repeat 8 times, while a "
            "4-sentence loop only needs to repeat twice (4x2=8). This prevents false positives "
            "on valid, short repetitive structures (e.g., conversational filler or list enumeration)."
        ),
    )
    REPETITION_MIN_WORDS: int = Field(
        default=16,
        description=(
            "Minimum number of (decoded) text words for repeated word fallback."
        ),
    )
    REPETITION_ENTROPY_THRESHOLD: float = Field(
        default=0.15,
        description=(
            "The 'God-Mode' fallback safety net. Checks the compression ratio of the last 1000 characters "
            "using Zlib. Normal English compresses to ~45%. If the text compresses to a fraction smaller "
            "than this threshold (e.g. 0.15 or 15%), it guarantees the model is stuck in a highly "
            "repetitive loop (run-on commas, gibberish, or semantic paraphrasing) and forces an abort."
        ),
    )
    REPETITION_ENTROPY_NUM_CHARS: int = Field(
        default=4096,
        description=(
            "Minimum number of (decoded) text characters to trigger entropy checks."
        ),
    )
    BREAK_NON_REASONING_REPETITIONS: bool = Field(
        default=True,
        description="Whether to detect and attempt to break repetition loops outside of the analysis channel. Forces the model back into analysis channel to consider its mistakes. May break some clients that do not expect streamed outputs to be reasoning -> output -> reasoning -> output.",
    )
    NON_REASONING_REPETITION_RECOVERY_CHANNEL: Literal[
        "analysis", "commentary", "final"
    ] = Field(
        default="final",
        description="What channel to prefill on model state recovery. Defaults to analysis to allow model to reason about the error it encountered.",
    )

    MAX_RECOVER_STATE_ATTEMPTS: int = Field(
        default=32,
        description="Maximum attempts to recover a corrupted inference state.",
    )

    ENFORCE_STRICT_TOOL_NAMESPACES: bool = Field(
        default=False,
        description="Require tool names to be fully qualified namespaces ('functions.*', 'browser.*' and 'python').",
    )
    CLEANUP_LOW_PRECISION_PROMPT_TIMESTRINGS: bool = Field(
        default=True,
        description="Remove granular timestamps (eg: 12:42:23) from prompts. These mess up prompt caching with no added benefit.",
    )
    SYSTEM_MESSAGE_DATE_CONFIG: str | Literal["off", "auto", "auto-utc"] = Field(
        default="2026-04-08",
        description="Whether and how to include and format current date in system message.",
    )

    # TODO: reset to Nones when done benchmarking
    SAMPLING_DEFAULT_TOP_K: Optional[int] = Field(
        default=64, description="Default top_k to use when not set by client"
    )
    SAMPLING_DEFAULT_TOP_P: Optional[float] = Field(
        default=1.0, description="Default top_p to use when not set by client"
    )
    SAMPLING_DEFAULT_MIN_P: Optional[float] = Field(
        default=0.0, description="Default min_p to use when not set by client"
    )
    SAMPLING_DEFAULT_TEMPERATURE: Optional[float] = Field(
        default=1.0, description="Default temperature to use when not set by client"
    )
    SAMPLING_DEFAULT_SEED: Optional[int] = Field(
        default=None, description="Default seed to use when not set by client"
    )

    IS_PYTHON_TOOL_AVAILABLE: bool = Field(
        default=True, description="Enable the native Python tool."
    )
    IS_PYTHON_TOOL_ALWAYS_ENABLED: bool = Field(
        default=False,
        description="Always enable Python tool without caller tool list gymnastics.",
    )

    IS_BROWSER_TOOL_AVAILABLE: bool = Field(
        default=True, description="Enable the native browser tool."
    )
    IS_BROWSER_TOOL_ALWAYS_ENABLED: bool = Field(
        default=False,
        description="Always enable browser tool without caller tool list gymnastics.",
    )

    BROWSER_BACKEND: Literal["playwright", "httpx"] = Field(
        default="httpx",
        description="Choose between playwright or httpx for browser fetch.",
    )
    # NOTE: defaulting to jupyter since it will be inside docker anyway in prod
    # also, model seems to really like chaining commands, but wastes a lot of turns
    # figuring out it also needs to print (in docker), so jupyter seems more.. native?
    # warning.. docker also seems to hang, doesn't properly kill on timeout?
    # use jupyter, hardened to be thread safe (and it's within docker)
    PYTHON_BACKEND: Literal["jupyter-in-process", "jupyter-docker-kernels"] = Field(
        default="jupyter-in-process",
        description="Backend used to execute Python code.",
    )
    PYTHON_KERNEL_MIN_POOL_SIZE: int = Field(
        default=2,
        description="Minumum number of jupyter kernels to keep in the warm pool.",
    )

    SESSION_HANDLER_SENTINEL_HEARTBEAT_SECONDS: int = Field(
        default=30,
        description="Timeout for python tool execution, in seconds.",
    )

    PYTHON_EXECUTION_TIMEOUT_SECONDS: int = Field(
        default=120,
        description="Timeout for python tool execution, in seconds.",
    )

    BROWSER_SESSION_IDLE_TIMEOUT: int = Field(
        default=24 * 60 * 60,  # 24 hours
        description="Timeout (in seconds) to keep idle browser sessions alive.",
    )
    PYTHON_SESSION_IDLE_TIMEOUT: int = Field(
        default=1 * 1 * 60,  # 20 minutes
        description="Timeout (in seconds) to keep idle python sessions alive. MUST be > than execution timeout otherwise SessionHandler sentinel can prematurely kill long working python tool threads.",
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
        description="Locale setting used by browser operations. Also prompts the model to use this as a default when relevant.",
    )
    BROWSER_LANGUAGE: str = Field(
        default="en",
        description="Preferred language for browser operations. Also prompts the model to use this as a default when relevant.",
    )
    BROWSER_TIMEZONE: str = Field(
        default="Europe/London",
        description="Timezone for browser engine context.",
    )
    BROWSER_SESSION_CACHE_SIZE: int = Field(
        default=32,
        description="Maximum number of browser session objects cached in the browser engine singleton LRU cache.",
    )
    PYTHON_SESSION_CACHE_SIZE: int = Field(
        default=32,
        description="Maximum number of python session objects cached in the python engine singleton LRU cache.",
    )

    BRAVE_API_KEY: str = Field(
        default="",
        description="API key for the Brave search engine. Use a blank string to fall back to SearXNG for browser search.",
    )
    BRAVE_API_URL: str = Field(
        default="https://api.search.brave.com/res/v1/web/search",
        description="Endpoint URL for the Brave search API.",
    )

    SEARXNG_API_URL: str = Field(
        default="",
        description="Endpoint URL for the SearXNG search API. If both this and BRAVE_API_KEY are blank, browser.search is disabled.",
    )

    METRICS_AUTH_TOKEN: str = Field(
        default="",
        description="Bearer token required for accessing the /metrics endpoint; empty disables filtering.",
    )
    METRICS_IP_WHITELIST: str = Field(
        default="",
        description="Comma or semicolon separated IP whitelist for /metrics endpoint; empty disables filtering.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()  # type: ignore[reportCallIssue]
