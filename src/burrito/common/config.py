from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Burrito"
    DEBUG: bool = True
    DATABASE_URL: str = ""
    SECRET_KEY: str = ""
    LOG_LEVEL: str = "INFO"

    INFERENCE_BACKEND_IS_NATIVE: bool = False
    INFERENCE_BACKEND_BASE_URL: str = "http://192.168.0.202:9999"
    INFERENCE_BACKEND_COMPLETIONS_PATH: str = "/v1/completions"

    BACKEND_INTER_TOKEN_TIMEOUT: int = 120  # allow for large prompt preprocessing

    DEFAULT_MODEL_NAME: str = "openai/gpt-oss-20b"
    DEFAULT_MODEL_CTX_LEN: int = 131072

    DEFAULT_REASONING_EFFORT: Literal["low", "medium", "high"] = "high"
    DEFAULT_REASONING_SUMMARY: Literal["auto", "concise", "detailed"] = "auto"

    DEFAULT_COMPLETION_BEST_OF: int = 1
    DEFAULT_COMPLETION_N: int = 1

    MAX_RECOVER_STATE_ATTEMPTS: int = 100

    IS_PYTHON_TOOL_ENABLED: bool = True
    IS_BROWSER_TOOL_ENABLED: bool = True

    SANDBOX_KERNEL_TIMEOUT: int = 120
    SANDBOX_SESSIONS_DIR: str = "sessions"

    PYTHON_BACKEND: Literal["docker"] = "docker"

    USER_AGENT_BROWSE: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15"
    USER_AGENT_SEARCH: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15"

    BRAVE_API_KEY: str = ""
    BRAVE_API_URL: str = "https://api.search.brave.com/res/v1/web/search"

    SEARXNG_API_URL: str = "http://192.168.0.201:9090"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()  # pyright: ignore[reportCallIssue]
