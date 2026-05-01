from __future__ import annotations

import json
import socket
from typing import Any

from .logging_utils import get_logger


UDP_HOST = "127.0.0.1"
UDP_PORT = 8765
BUFFER_SIZE = 65535
logger = get_logger("indie_game_agent.runtime_bridge")


class RuntimeBridgeError(RuntimeError):
    pass


def request_runtime(
    command: str,
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 0.8,
) -> dict[str, Any]:
    message = {"command": command}
    if payload:
        message.update(payload)

    raw_message = json.dumps(message).encode("utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_sec)
        sock.sendto(raw_message, (UDP_HOST, UDP_PORT))

        try:
            raw_response, _ = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout as exc:
            raise RuntimeBridgeError(
                f"No response from the local game runtime on udp://{UDP_HOST}:{UDP_PORT}. "
                "Start run_game.py first."
            ) from exc

    response = json.loads(raw_response.decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeBridgeError("Invalid JSON response from runtime (not a dictionary).")
    if not response.get("ok", False):
        raise RuntimeBridgeError(response.get("error", "Unknown runtime error"))

    return response


def runtime_available() -> bool:
    try:
        request_runtime("ping", timeout_sec=0.3)
    except RuntimeBridgeError:
        return False
    return True


UDP_CHEATSHEET = """
Runtime UDP commands:
- ping
- get_state
- reset_room
- load_room
- preview_plan
- apply_moves
- show_note
- save_snapshot
""".strip()
