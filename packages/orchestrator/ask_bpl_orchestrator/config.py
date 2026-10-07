from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://askbpl:askbpl_dev_password@localhost:5434/askbpl"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    session_ttl_hours: int = 8
    # Tests set DB_USE_NULL_POOL=true so pooled asyncpg connections never outlive
    # the event loop that created them (TestClient and asyncio.run use different loops).
    db_use_null_pool: bool = False

    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    pinecone_api_key: str = ""
    pinecone_index_name: str = "askbpl-pilot"
    pinecone_host: Optional[str] = None

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    pinecone_top_k: int = 6
    # Tuned for text-embedding-3-small + pilot corpus (May 2026)
    grounding_threshold: float = 0.40
    # Margin rule: ground if ≥2 chunks above floor OR one chunk above strong threshold
    grounding_strong_threshold: float = 0.45

    host: str = "0.0.0.0"
    port: int = 8000

    admin_basic_user: str = "vizion_build"
    admin_basic_password: str = ""

    # Public demo: unauthenticated visitors get attributed sessions for this tester.
    public_demo_tester_email: str = "pilot-demo@bklynlibrary.org"

    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,http://localhost:4173,"
        "https://askbpl-web-demo.vercel.app"
    )

    corpus_dir: str = "./sample_corpus"
    # Default "Re-ingest" manifest — pilot PDFs only (see TRD §13 corpus exclusivity).
    # Override with env INGEST_MANIFEST_PATH when running full dev manifests.
    ingest_manifest_path: str = "sample_corpus/corpus_manifest_pilot.yaml"
    documents_public_base_url: str = ""

    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 100

    # Scanned PDF fallback (ingest-time only). Requires optional pip extra `[ocr]`
    # plus system `tesseract-ocr` and `poppler-utils` when enabled.
    ocr_enabled: bool = True
    ocr_dpi: int = 300
    ocr_min_chars_per_page: int = 100

    @field_validator("database_url", mode="before")
    @classmethod
    def convert_psycopg(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def require_secrets(self) -> None:
        """Fail fast at startup when auth or RAG secrets are missing."""
        missing: list[str] = []
        if not self.jwt_secret_key.strip():
            missing.append("JWT_SECRET_KEY")
        if not self.openai_api_key.strip():
            missing.append("OPENAI_API_KEY")
        if not self.anthropic_api_key.strip():
            missing.append("ANTHROPIC_API_KEY")
        if not self.pinecone_api_key.strip():
            missing.append("PINECONE_API_KEY")
        if not self.pinecone_index_name.strip():
            missing.append("PINECONE_INDEX_NAME")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)} "
                "(see .env.example)"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
