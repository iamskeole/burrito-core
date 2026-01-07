from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Burrito"
    DEBUG: bool = True
    DATABASE_URL: str = ""
    SECRET_KEY: str = ""
    LOG_LEVEL: str = "INFO"

    INFERENCE_BACKEND_IS_NATIVE: bool = False
    INFERENCE_BACKEND_BASE_URL: str = "http://84.232.239.80:9999"
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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()  # pyright: ignore[reportCallIssue]
