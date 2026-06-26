"""Central configuration. Every value has a safe default so the app runs
fully offline (deterministic MockLLM) when no API key is present."""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent.parent  # -> capstone/
DATA_DIR = PACKAGE_ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
DATASETS_DIR = PACKAGE_ROOT / "datasets" / "Agentic Healthcare Assistant for Medical Task Automation"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PACKAGE_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-opus-4-8", alias="HCASST_MODEL")
    offline: bool = Field(default=False, alias="HCASST_OFFLINE")
    max_tokens: int = Field(default=1024, alias="HCASST_MAX_TOKENS")
    temperature: float = Field(default=0.0, alias="HCASST_TEMPERATURE")
    db_path: str = Field(default=str(DATA_DIR / "hcasst.db"), alias="HCASST_DB_PATH")
    use_st_embeddings: bool = Field(default=True, alias="HCASST_USE_ST_EMBEDDINGS")
    st_model: str = Field(default="all-MiniLM-L6-v2", alias="HCASST_ST_MODEL")
    max_agent_loops: int = Field(default=3, alias="HCASST_MAX_LOOPS")
    load_instructor_data: bool = Field(default=True, alias="HCASST_LOAD_INSTRUCTOR_DATA")

    @property
    def llm_available(self) -> bool:
        """True when real Claude calls are possible."""
        return bool(self.anthropic_api_key) and not self.offline

    def ensure_dirs(self) -> None:
        for d in (DATA_DIR, SEED_DIR):
            d.mkdir(parents=True, exist_ok=True)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s



    