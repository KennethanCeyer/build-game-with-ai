from __future__ import annotations

from urllib import request
from urllib.error import URLError
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from engine.game.game_observation import agent_visible_state


mcp = FastMCP(
    "게임 에이전트 런타임",
    instructions=(
        "3D 인디 게임 QA를 위한 도구 모음입니다. 에이전트는 게임 상태를 관찰하고 "
        "WASD, Shift, Space, E 키 입력을 조합하여 캐릭터를 조작해야 합니다. "
        "순간이동이나 직접적인 상태 수정 도구는 제공되지 않으며 실제 플레이어와 동일한 제약 조건을 가집니다."
    ),
    json_response=True,
)


@mcp.tool()
def inspect_game_state() -> dict[str, Any]:
    """현재 게임 월드의 상태 정보를 조회합니다. 캐릭터 위치, 주변 장애물, 퀘스트 진행 상황 및 이벤트 로그를 포함합니다."""
    runtime_state = _runtime_get("/api/state")
    if runtime_state is not None:
        return {
            "ok": True,
            "state": agent_visible_state(runtime_state.get("state", {})),
            "source": "runtime_http",
        }
    return {
        "ok": False,
        "message": "게임 런타임에 접속할 수 없습니다. 먼저 게임 서버를 실행하세요.",
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
    """일련의 키보드 입력 프레임을 게임 엔진에 전달하여 캐릭터를 조작합니다.
    frames 예시: [{"keys": ["KeyW"], "duration_ms": 200}] (W키를 0.2초간 입력)
    이동 시에는 현재 카메라의 yaw 각도를 함께 전달해야 정확한 방향으로 움직입니다.
    """
    normalized_actor_id = _normalize_actor_id(actor_id)
    if normalized_actor_id != "rhea":
        return {
            "ok": False,
            "message": "플레이어 캐릭터 'rhea'만 조작할 수 있습니다.",
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
        "message": "게임 런타임에 접속할 수 없습니다. 입력을 전달하지 못했습니다.",
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
    """카메라의 각도(yaw, pitch)와 줌(zoom)을 조정합니다. 주변 환경을 더 넓게 보거나 특정 방향을 조망할 때 사용합니다."""

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
        "message": "게임 런타임에 접속할 수 없습니다. 카메라 뷰를 변경하지 못했습니다.",
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
    """실습용 3D 게임 QA 환경에 대한 설계 의도와 설명입니다."""
    return (
        "Agent Playtest Lab은 에이전트 기반 게임 테스트 도구를 학습하기 위한 3D 환경입니다. "
        "에이전트는 이동, NPC 퀘스트 상호작용, 메모리 퍼즐 해결, 그리고 스크린샷 기반의 검증 작업을 "
        "수행하며 자신의 가치를 증명합니다."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
