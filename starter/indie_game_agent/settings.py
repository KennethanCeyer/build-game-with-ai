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
    # TODO(starter-1): map GOOGLE_API_KEY from .env to google_api_key.
    # Hint: use the env name as the validation alias.
    google_api_key: str = Field(..., validation_alias="TODO_REPLACE_ME")

    model_config = SettingsConfigDict(
        extra="ignore",
    )


def load_settings() -> Settings:
    # TODO(starter-1): load Settings from the root .env file when it exists.
    # Hint: prefer Settings(_env_file=ENV_FILE) when the file exists.
    if False:
        logger.info("Loading settings from %s", ENV_FILE.name)
        return Settings(_env_file=ENV_FILE)

    logger.info("Loading settings from process environment")
    return Settings()


def apply_environment(settings: Settings) -> None:
    # TODO(starter-1): expose GOOGLE_API_KEY to the current process.
    # Hint: set the exact env var name that Google tooling expects.
    os.environ.setdefault("TODO_ENV_NAME", settings.google_api_key)
    logger.info("Environment values are available to the current process")
