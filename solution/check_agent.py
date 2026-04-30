from __future__ import annotations

from indie_game_agent.logging_utils import get_logger
from indie_game_agent.agent import root_agent


logger = get_logger("check_agent")


def main() -> None:
    logger.info("Agent check passed")
    logger.info("Agent name: %s", root_agent.name)
    logger.info("Model: %s", root_agent.model)


if __name__ == "__main__":
    main()
