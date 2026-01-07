import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BURRITO_SANDBOX_HOST: int = int(os.environ.get("BURRITO_SANDBOX_HOST", 8001))
    BURRITO_SANDBOX_KERNEL_TIMEOUT: int = 60
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./burrito.db")


settings = Settings()
