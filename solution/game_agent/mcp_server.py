from __future__ import annotations

from urllib import request
from urllib.error import URLError
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from engine.game.game_observation import agent_visible_state


mcp = FastMCP(
    "Agentic 3D Game Runtime",
    instructions=(
        "Tools for a small 3D indie game QA slice. Agents must inspect the runtime state and "
        "control the player character through the same input buffer a player has: WASD, Shift, "
        "Space, and E. No teleport, direct zone movement, or flag mutation tools are exposed."
    ),
    json_response=True,
)


@mcp.tool()
def inspect_game_state() -> dict[str, Any]:
    runtime_state = _runtime_get("/api/state")
    if runtime_state is not None:
        return {
            "ok": True,
            "state": agent_visible_state(runtime_state.get("state", {})),
            "source": "runtime_http",
        }
    return {
        "ok": False,
        "message": "Live runtime is not reachable. Start the FastAPI game server first.",
        "state": {},
        "source": "runtime_http_unavailable",
        "degraded": True,
    }


@mcp.tool()
def apply_input_buffer(
    frames: list[dict[str, Any]],
    actor_id: str = "rhea",
    camera_yaw_degrees: float = 0.0,
) -> dict[str, Any]:
    normalized_actor_id = _normalize_actor_id(actor_id)
    if normalized_actor_id != "rhea":
        return {
            "ok": False,
            "message": "Only the player character id 'rhea' can be controlled through input buffers.",
            "state": {},
            "degraded": True,
        }
    runtime_result = _runtime_post(
        "/api/input-buffer",
        {
            "actor_id": normalized_actor_id,
            "frames": frames,
            "camera_yaw_degrees": camera_yaw_degrees,
        },
    )
    if runtime_result is not None:
        runtime_result["state"] = agent_visible_state(runtime_result.get("state", {}))
        runtime_result["source"] = "runtime_http"
        return runtime_result

    return {
        "ok": False,
        "message": "Live runtime is not reachable. No local simulator fallback is used.",
        "state": {},
        "source": "runtime_http_unavailable",
        "degraded": True,
    }


@mcp.tool()
def adjust_camera_view(
    yaw_delta_degrees: float = 0.0,
    pitch_delta_degrees: float = 0.0,
    zoom_delta: float = 0.0,
) -> dict[str, Any]:
    """Queue a camera drag/wheel equivalent for the live browser view."""

    runtime_result = _runtime_post(
        "/api/camera-control",
        {
            "yaw_delta_degrees": yaw_delta_degrees,
            "pitch_delta_degrees": pitch_delta_degrees,
            "zoom_delta": zoom_delta,
        },
    )
    if runtime_result is not None:
        runtime_result["source"] = "runtime_http"
        return runtime_result
    return {
        "ok": False,
        "message": "Live runtime is not reachable. Camera view was not changed.",
        "source": "runtime_http_unavailable",
        "degraded": True,
    }


def _runtime_base_url() -> str | None:
    return os.environ.get("AGENTIC_GAME_MCP_RUNTIME_URL")


def _normalize_actor_id(actor_id: str) -> str:
    if actor_id == "rhea":
        return actor_id
    normalized = actor_id.strip().lower()
    aliases = {
        "",
        "player",
        "player1",
        "player_0",
        "player_01",
        "player 1",
        "player character",
        "local_player",
        "avatar",
        "character",
        "pc",
        "user",
        "self",
        "agent",
        "default",
        "캐릭터",
        "캐릭터1",
    }
    return "rhea" if normalized in aliases else actor_id


def _runtime_get(path: str) -> dict[str, Any] | None:
    base_url = _runtime_base_url()
    if not base_url:
        return None
    try:
        with request.urlopen(f"{base_url}{path}", timeout=5) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return parsed if isinstance(parsed, dict) else None
    except (OSError, URLError, json.JSONDecodeError):
        return None


def _runtime_post(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    base_url = _runtime_base_url()
    if not base_url:
        return None
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return parsed if isinstance(parsed, dict) else None
    except (OSError, URLError, json.JSONDecodeError):
        return None


@mcp.resource("design://agent-playtest-lab")
def agent_playtest_lab_design() -> str:
    return (
        "Agent Playtest Lab is a compact 3D slice for teaching agentic game tooling. "
        "The agent proves value by driving locomotion, NPC quest interaction, memory puzzle "
        "interaction, and screenshot-grounded verification."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
