"""Application settings loaded from NIYAM_* environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecretFileError(RuntimeError):
    """A configured secret file exists but holds no usable value."""


class Settings(BaseSettings):
    """Runtime configuration. Defaults match the Kubernetes deployment."""

    model_config = SettingsConfigDict(env_prefix="NIYAM_", extra="ignore")

    app_version: str = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    qdrant_url: str = "http://qdrant.niyam.svc:6333"
    qdrant_api_key: SecretStr | None = None  # Local development only.
    qdrant_api_key_file: Path = Path("/vault/secrets/qdrant")
    qdrant_collection: str = "circulars_v1"

    ollama_url: str = "http://ollama.niyam.svc:11434"
    llm_model: str = "qwen2.5:1.5b-instruct"
    llm_timeout_s: int = Field(default=60, gt=0)
    llm_max_tokens: int = Field(default=256, gt=0)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_cache: Path = Path("/models")
    prompt_version: str = "v1"
    refusal_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    corpus_manifest: Path = Path("/data/corpus/manifest.yaml")

    def resolved_qdrant_api_key(self) -> str | None:
        """Return the Qdrant key, preferring the injected file over the dev variable.

        The file is read on every call so a value rewritten by the Vault agent is picked up.
        """
        try:
            value = self.qdrant_api_key_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return self.qdrant_api_key.get_secret_value() if self.qdrant_api_key else None
        if not value:
            raise SecretFileError(f"Secret file is empty: {self.qdrant_api_key_file}")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
