import asyncio
import selectors
import sys
import os
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    asyncio.set_event_loop(asyncio.SelectorEventLoop(selectors.SelectSelector()))

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://app:app@localhost:5433/support"
    redis_url: str = "redis://localhost:6379"

    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = "ollama"
    llm_model: str = "llama3.1"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    retrieval_k: int = 5
    confidence_threshold: float = 0.35

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    jwt_secret: str = "change-this-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 8   # 8 hours
    frontend_url: str = "http://localhost:5173"

    admin_username: str = "admin"
    admin_password: str = "admin123"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",
        extra="ignore",
    )

settings = Settings()