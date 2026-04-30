from __future__ import annotations

from indie_game_agent.logging_utils import get_logger
from indie_game_agent.settings import load_settings


logger = get_logger("check_env")


def main() -> None:
    settings = load_settings()
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY was not loaded.")

    logger.info("Environment check passed")
    logger.info("Loaded GOOGLE_API_KEY from .env")


if __name__ == "__main__":
    main()
