from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://norma:norma_local_demo@localhost:55433/norma"
    ollama_url: str = "http://localhost:11435"
    model: str = "qwen3:4b"
    embedding_model: str = "nomic-embed-text"
    llm_provider: str = "ollama"
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""
    api_model: str = ""
    data_dir: Path = Path("data")
    max_question_length: int = 1500
    max_parallel: int = 2
    request_timeout: int = 120
    weekly_updates: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "http://localhost:3100"


settings = Settings()
