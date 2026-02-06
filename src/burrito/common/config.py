from typing import Literal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = True
    LOG_LEVEL: str = "debug"

    DEBUG_TOOL_IO: bool = True
    DEBUG_COMPLETIONS: bool = False
    DEBUG_PROMPT: bool = True
    DEBUG_OUTGOING_EVENTS: bool = False
    DEBUG_RESPONSE_BUFFER: bool = False

    CORS_ALLOWED_ORIGINS: list[str] = ["*"]
    CORS_ALLOWED_METHODS: list[str] = ["*"]
    CORS_ALLOWED_HEADERS: list[str] = ["*"]
    CORS_ALLOWED_CREDENTIALS: bool = True

    MAX_REQUEST_BODY_SIZE: int = 1048576  # 1MB in bytes
    MAX_CONCURRENT_INFERENCE_REQUESTS: int = 4  # > this  wait in fifo queue
    FORWARD_HEADERS: list[str] = ["Authorization", "X-Api-Key"]

    BURRITO_HOST: str = "0.0.0.0"
    BURRITO_PORT: int = 8000

    INFERENCE_BACKEND_IS_NATIVE: bool = False
    INFERENCE_BACKEND_BASE_URL: str = "changeme"
    INFERENCE_BACKEND_COMPLETIONS_PATH: str = "/v1/completions"

    BACKEND_INTER_TOKEN_TIMEOUT: int = 120  # allow for large prompt preprocessing

    DEFAULT_MODEL_NAME: str = "openai/gpt-oss-20b"
    DEFAULT_MODEL_CTX_LEN: int = 131072

    DEFAULT_REASONING_EFFORT: Literal["low", "medium", "high"] = "medium"
    DEFAULT_REASONING_SUMMARY: Literal["auto", "concise", "detailed"] = "auto"

    MAX_RECOVER_STATE_ATTEMPTS: int = 100

    IS_PYTHON_TOOL_ENABLED: bool = True
    IS_BROWSER_TOOL_ENABLED: bool = True

    IS_PYTHON_TOOL_ALWAYS_ENABLED: bool = True
    IS_BROWSER_TOOL_ALWAYS_ENABLED: bool = True

    PYTHON_BACKEND: Literal["docker", "dangerously_use_local_jupyter"] = (
        "dangerously_use_local_jupyter"
    )

    USER_AGENT_BROWSE: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15"
    USER_AGENT_SEARCH: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15"

    BRAVE_API_KEY: str = ""
    BRAVE_API_URL: str = "https://api.search.brave.com/res/v1/web/search"

    SEARXNG_API_URL: str = "changeme"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()  # type: ignore[reportCallIssue]
