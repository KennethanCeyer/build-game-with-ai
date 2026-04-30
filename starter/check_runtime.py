from __future__ import annotations

from indie_game_agent.logging_utils import get_logger
from indie_game_agent.runtime_bridge import request_runtime


logger = get_logger("check_runtime")


def main() -> None:
    ping = request_runtime("ping")
    state = request_runtime("get_state")
    logger.info("Runtime check passed")
    logger.info("Ping reply: %s", ping.get("reply"))
    logger.info("Room: %s", state["state"]["room_name"])
    logger.info("Relics remaining: %s", state["state"]["relics_remaining"])
    logger.info("Exit locked: %s", state["state"]["exit"]["locked"])
    logger.info("Safe moves: %s", ", ".join(state["state"]["available_moves"]))


if __name__ == "__main__":
    main()
