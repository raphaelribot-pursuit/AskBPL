from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://askbpl:askbpl_dev_password@localhost:5432/askbpl"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    session_ttl_hours: int = 8

    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    pinecone_api_key: str = ""
    pinecone_index_name: str = "askbpl-pilot"
    pinecone_host: Optional[str] = None

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    pinecone_top_k: int = 6
    grounding_threshold: float = 0.72

    host: str = "0.0.0.0"
    port: int = 8000

    admin_basic_user: str = "vizion_build"
    admin_basic_password: str = ""

    cors_origins: str = "http://localhost:5173"

    corpus_dir: str = "./sample_corpus"
    documents_public_base_url: str = ""

    chunk_size_tokens: int = 800
    chunk_overlap_tokens: int = 100

    @field_validator("database_url", mode="before")
    @classmethod
    def convert_psycopg(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
