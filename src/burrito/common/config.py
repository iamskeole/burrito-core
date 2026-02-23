from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DEBUG: bool = False
    LOG_LEVEL: str = "debug"

    DEBUG_TOOL_INPUTS: bool = True
    DEBUG_TOOL_OUTPUTS: bool = False
    DEBUG_COMPLETIONS: bool = False
    DEBUG_PROMPT: bool = False
    DEBUG_OUTGOING_EVENTS: bool = False
    DEBUG_RESPONSE_BUFFER: bool = False

    CORS_ALLOWED_ORIGINS: list[str] = ["*"]
    CORS_ALLOWED_METHODS: list[str] = ["*"]
    CORS_ALLOWED_HEADERS: list[str] = ["*"]
    CORS_ALLOWED_CREDENTIALS: bool = True

    MAX_REQUEST_BODY_SIZE: int = 1048576  # 1MB in bytes
    # TODO: check python on concurrent requests, running aime broke it?
    MAX_CONCURRENT_INFERENCE_REQUESTS: int = 16  # > this  wait in fifo queue
    FORWARD_HEADERS: list[str] = ["Authorization", "X-Api-Key"]

    INFERENCE_BACKEND_IS_NATIVE: bool = False
    INFERENCE_BACKEND_BASE_URL: str = "changeme"

    BACKEND_INTER_TOKEN_TIMEOUT: int = 120  # allow for large prompt preprocessing

    DEFAULT_MODEL_NAME: Literal[
        "openai/gpt-oss-20b",
        "openai/gpt-oss-20b-chat",
        "openai/gpt-oss-20b-responses",
    ] = "openai/gpt-oss-20b"
    DEFAULT_MODEL_CTX_LEN: int = 131072

    DEFAULT_REASONING_EFFORT: Literal["low", "medium", "high"] = "medium"
    DEFAULT_REASONING_SUMMARY: Literal["auto", "concise", "detailed"] = "auto"

    MODEL_IDENTITY: Literal["default", "experimental"] = "experimental"

    MAX_RECOVER_STATE_ATTEMPTS: int = 100
    # NOTE: set temperature to 0.001 and this likely happens more often?
    MAX_REASONING_LOOPS: int = 50

    IS_PYTHON_TOOL_ENABLED: bool = True
    IS_BROWSER_TOOL_ENABLED: bool = True

    IS_PYTHON_TOOL_ALWAYS_ENABLED: bool = True
    IS_BROWSER_TOOL_ALWAYS_ENABLED: bool = True

    BROWSER_TIMEOUT_FETCH: int = 3
    BROWSER_TIMEOUT_SEARCH: int = 10

    PYTHON_BACKEND: Literal["docker", "dangerously_use_local_jupyter"] = "docker"

    USER_AGENT_SEARCH: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15"

    BRAVE_API_KEY: str = ""
    BRAVE_API_URL: str = "https://api.search.brave.com/res/v1/web/search"

    SEARXNG_API_URL: str = "changeme"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()  # type: ignore[reportCallIssue]
