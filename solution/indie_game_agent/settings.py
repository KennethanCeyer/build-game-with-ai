from __future__ import annotations

from pathlib import Path
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .logging_utils import get_logger


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
logger = get_logger("indie_game_agent.settings")


class Settings(BaseSettings):
    google_api_key: str = Field(..., validation_alias="GOOGLE_API_KEY")

    model_config = SettingsConfigDict(
        extra="ignore",
    )


def load_settings() -> Settings:
    if ENV_FILE.exists():
        logger.info("Loading settings from %s", ENV_FILE.name)
        return Settings(_env_file=ENV_FILE)

    logger.info("Loading settings from process environment")
    return Settings()


def apply_environment(settings: Settings) -> None:
    os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    logger.info("Environment values are available to the current process")
