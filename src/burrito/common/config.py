from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "debug"
    ACCESS_LOG: bool = False

    DEBUG_TOOL_CALLS: bool = False
    DEBUG_TOOL_INPUTS: bool = False
    DEBUG_TOOL_OUTPUTS: bool = False
    DEBUG_COMPLETIONS: bool = False
    DEBUG_PROMPT: bool = False
    DEBUG_OUTGOING_EVENTS: bool = False
    DEBUG_RESPONSE_BUFFER: bool = False
    DEBUG_STATE_CHANGE: bool = False
    DEBUG_HARMONY_ERRORS: bool = False
    DEBUG_BROWSER_ERRORS: bool = False
    DEBUG_STATE_ERRORS: bool = False
    DEBUG_CLIENT_DISCONNECTS: bool = False
    DEBUG_GENERATOR_CLEANUP: bool = False

    CORS_ALLOWED_ORIGINS: str = "*"
    CORS_ALLOWED_METHODS: str = "*"
    CORS_ALLOWED_HEADERS: str = "*"
    CORS_ALLOWED_CREDENTIALS: bool = True

    MAX_REQUEST_BODY_SIZE: int = 1048576 * 1  # MB in bytes
    MAX_CONCURRENT_INFERENCE_REQUESTS: int = 16  # > this  wait in fifo queue

    BACKEND_BASE_URL: str = "changeme"
    BACKEND_INTER_TOKEN_TIMEOUT: int = 120  # allow for large prompt preprocessing
    BACKEND_FORWARD_HEADERS: str = "Authentication,X-Api-Key"

    DEFAULT_MODEL_NAME: str = "openai/gpt-oss-20b"
    DEFAULT_MODEL_CTX_LEN: int = 131072

    DEFAULT_REASONING_EFFORT: Literal["low", "medium", "high"] = "medium"
    DEFAULT_REASONING_SUMMARY: Literal["auto", "concise", "detailed"] = "auto"

    MODEL_IDENTITY: str = "v1"

    MAX_RECOVER_STATE_ATTEMPTS: int = 100
    # NOTE: set temperature to 0.001 and this likely happens more often?
    MAX_REASONING_LOOPS: int = 1000

    ENFORCE_STRICT_TOOL_NAMESPACES: bool = False

    IS_PYTHON_TOOL_ENABLED: bool = True
    IS_BROWSER_TOOL_ENABLED: bool = True

    IS_PYTHON_TOOL_ALWAYS_ENABLED: bool = True
    IS_BROWSER_TOOL_ALWAYS_ENABLED: bool = True

    PYTHON_BACKEND: Literal["docker", "dangerously_use_local_jupyter"] = "docker"

    BROWSER_TIMEOUT_FETCH: int = 3
    BROWSER_TIMEOUT_SEARCH: int = 10
    BROWSER_LOCALE: str = "en-US"
    BROWSER_LANGUAGE: str = "en"
    BROWSER_TIMEZONE: str = "America/New_York"

    BRAVE_API_KEY: str = ""
    BRAVE_API_URL: str = "https://api.search.brave.com/res/v1/web/search"

    SEARXNG_API_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()  # type: ignore[reportCallIssue]
