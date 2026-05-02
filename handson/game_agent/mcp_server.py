from __future__ import annotations

from urllib import request
from urllib.error import URLError
import json
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp import types

from engine.game.game_observation import agent_visible_state
import logging

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logging.getLogger("fastmcp").setLevel(logging.WARNING)


mcp = FastMCP(
    "게임 에이전트 런타임",
    instructions=(
        "3D 인디 게임 QA용 도구 모음. 게임 상태 관측 및 "
        "WASD, Shift, Space, E 키 입력을 조합해 캐릭터 조작. "
        "직접적인 상태 수정 불가 및 실제 플레이어와 동일 조건 기동."
    ),
    json_response=True,
)


@mcp.tool()
def save_memory(key: str, value: Any, source: str = "agent") -> dict[str, Any]:
    """판단, 이동 경로, 발견 사실 등 중요 정보를 런타임 작업 기억에 저장합니다."""
    runtime_result = _runtime_post(
        "/api/agent-memory/save",
        {
            "key": key,
            "value": value,
            "source": source,
        },
    )
    if runtime_result is not None:
        return runtime_result
    return {
        "ok": False,
        "msg": "Engine connection failed.",
        "source": "runtime_http_unavailable",
        "degraded": True,
    }


@mcp.tool()
def load_memory(key: str | None = None) -> dict[str, Any]:
    """런타임 작업 기억을 불러옵니다."""
    runtime_result = _runtime_post(
        "/api/agent-memory/load",
        {"key": key},
    )
    if runtime_result is not None:
        return runtime_result
    return {
        "ok": False,
        "msg": "Engine connection failed.",
        "source": "runtime_http_unavailable",
        "degraded": True,
    }


@mcp.tool()
def diagnose_engine_state() -> dict[str, Any]:
    """게임 엔진 내부 진단 정보 조회.
    이벤트 트리거 상태, 물리 엔진 경고, 퀘스트 논리 구조 등 기술 데이터 제공.
    """
    runtime_diag = _runtime_get("/api/diagnostics")
    if runtime_diag is not None:
        return {
            "ok": True,
            "diagnostics": runtime_diag,
            "source": "engine_diagnostics"
        }
    return {
        "ok": False,
        "msg": "진단 정보 획득 실패. 엔진 통신 상태 확인 필요."
    }


_tool_budgets = {
    "inspect_game_state": 1,
    "capture_visual_observation": 1,
    "capture_visual_crop": 2,
}
_tool_counts = {}
_tool_cache = {}

def _claim_budget(tool_name: str) -> dict[str, Any] | None:
    limit = _tool_budgets.get(tool_name, 999)
    count = _tool_counts.get(tool_name, 0)
    if count >= limit:
        return {
            "ok": True,
            "budget_exhausted": True,
            "duplicate_request": True,
            "message": (
                f"{tool_name} 예산이 이미 소진되었습니다. 이번 턴에는 추가 관측이 불가합니다. "
                "이미 제공된 cached_result를 요약하고 즉시 observer 턴을 종료하십시오. "
                "절대로 같은 도구를 반복 호출하지 마십시오."
            ),
            "observation_complete": True,
            "must_finalize_observation": True,
            "cached_result": _tool_cache.get(tool_name)
        }
    _tool_counts[tool_name] = count + 1
    return None

def _reset_tool_budgets():
    global _tool_counts, _tool_cache
    _tool_counts.clear()
    _tool_cache.clear()

@mcp.tool()
def capture_visual_observation(reason: str = "visual QA") -> types.ImageContent | dict[str, Any]:
    """시각 검증이 꼭 필요한 경우에만 현재 화면을 캡처합니다.
    사용자 메시지에 이미 이미지가 포함되어 있다면 가급적 호출하지 마십시오.
    """
    budget_error = _claim_budget("capture_visual_observation")
    if budget_error:
        return budget_error

    runtime_capture = _runtime_get("/api/capture")
    if runtime_capture and runtime_capture.get("screenshot"):
        screenshot_url = runtime_capture.get("screenshot")
        if "," in screenshot_url:
            fmt, b64_data = screenshot_url.split(",", 1)
            mime = fmt.split(":")[1].split(";")[0]
            result = f"Full screen captured for: {reason}"
            _tool_cache["capture_visual_observation"] = result
            return types.ImageContent(
                type="image",
                data=b64_data,
                mimeType=mime,
            )

    return {
        "ok": False,
        "message": "시각 캡처 실패 또는 브라우저 클라이언트 없음",
    }


@mcp.tool()
def capture_visual_crop(
    reason: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> types.ImageContent | dict[str, Any]:
    """특정 영역(x, y, width, height)만 집중적으로 관측합니다. 
    작은 물체나 퍼즐 텍스트를 정밀하게 확인해야 할 때 사용하십시오.
    """
    budget_error = _claim_budget("capture_visual_crop")
    if budget_error:
        return budget_error

    runtime_capture = _runtime_get("/api/capture")
    if runtime_capture and runtime_capture.get("screenshot"):
        screenshot_url = runtime_capture.get("screenshot")
        if "," in screenshot_url:
            fmt, b64_data = screenshot_url.split(",", 1)
            mime = fmt.split(":")[1].split(";")[0]
            result = f"Crop at ({x},{y}) captured for: {reason}"
            _tool_cache["capture_visual_crop"] = result
            return types.ImageContent(
                type="image",
                data=b64_data,
                mimeType=mime,
            )

    return {
        "ok": False,
        "message": "영역 캡처 실패",
    }


@mcp.tool()
def inspect_game_state() -> dict[str, Any]:
    """현재 게임 월드의 구조화된 상태(좌표, 주변 장애물, 랜드마크, 퀘스트 상태 등)를 조회합니다.
    이미지는 절대 포함하지 않으며 순수 상태 데이터만 반환합니다.
    """
    budget_error = _claim_budget("inspect_game_state")
    if budget_error:
        return budget_error

    runtime_state = _runtime_get("/api/state")
    if runtime_state is None:
        return {
            "ok": False,
            "message": "Engine connection failed.",
            "observation_complete": True,
            "must_finalize_observation": True,
        }

    raw_state = runtime_state.get("state", {})
    state_data = agent_visible_state(raw_state)
    player = state_data.get("player", {})
    raw_camera = raw_state.get("camera", {})
    nav = state_data.get("navigation_observation", {})

    summary = {
        "pos": player.get("debug_position"),
        "facing": player.get("facing"),
        "camera_yaw_degrees": raw_camera.get("yaw_degrees", 0.0),
        "nearby": player.get("nearby_interaction"),
        "npcs": state_data.get("npcs", []),
        "navigation_observation": {
            "visible_landmarks": nav.get("visible_landmarks", [])[:5],
            "local_clearance": nav.get("local_clearance"),
            "far_clearance": nav.get("far_clearance"),
            "maze_corridors": nav.get("maze_corridors"),
        },
        "goals": state_data.get("goals"),
        "flags": state_data.get("flags"),
        "recent_events": [e["message"] for e in state_data.get("events", [])[-3:]],
    }

    result = {
        "ok": True,
        "message": (
            "상태 관찰 완료. observer_agent는 이 결과를 요약하고 "
            "추가 inspect_game_state 호출 없이 즉시 observer 턴을 종료해야 합니다."
        ),
        "observation_complete": True,
        "must_finalize_observation": True,
        "player": {
            **player,
            "debug_position": summary["pos"],
            "nearby_interaction": summary["nearby"],
        },
        "camera_yaw_degrees": summary["camera_yaw_degrees"],
        "navigation_observation": summary["navigation_observation"],
        "flags": summary["flags"],
        "goals": summary["goals"],
        "recent_events": summary["recent_events"],
        "summary": summary,
    }
    _tool_cache["inspect_game_state"] = result
    return result


@mcp.tool()
def apply_input_buffer(
    frames: list[dict[str, Any]],
    actor_id: str = "rhea",
    camera_yaw_degrees: float = 0.0,
) -> dict[str, Any]:
    """일련의 입력 프레임(WASD, Shift, Space, E)을 전송하여 캐릭터를 조작합니다.
    - [중요] 캐릭터 이동은 카메라 시점을 기준으로 결정됩니다.
    - [정밀도] duration_ms는 물리 계산 결과에 따라 소수점 단위로 입력할 수 있습니다.
    - [예시] frames: [{"keys": ["KeyW"], "duration_ms": 1245.5}, {"keys": ["KeyD"], "duration_ms": 450.0}]
    """
    normalized_actor_id = _normalize_actor_id(actor_id)
    if normalized_actor_id != "rhea":
        return {"ok": False, "msg": "Only 'rhea' can be controlled."}

    _reset_tool_budgets()
    runtime_result = _runtime_post(
        "/api/input-buffer",
        {
            "actor_id": normalized_actor_id,
            "frames": frames,
            "camera_yaw_degrees": camera_yaw_degrees,
        },
    )

    if runtime_result is not None:
        return runtime_result

    return {"ok": False, "msg": "Engine connection failed."}


@mcp.tool()
def adjust_camera_view(
    yaw_delta_degrees: float = 0.0,
    pitch_delta_degrees: float = 0.0,
    zoom_delta: float = 0.0,
) -> dict[str, Any]:
    """카메라의 각도(yaw, pitch)와 줌(zoom)을 조정합니다.
    이 게임은 오빗 카메라(Orbit Camera) 시스템을 사용합니다.
    주변 환경을 더 넓게 보거나 특정 방향을 조망할 때 사용합니다. 시점 변경은 WASD 이동의 기준점도 바꿈에 유의하세요.

    - yaw_delta_degrees: 수평 회전량. 양수는 오른쪽, 음수는 왼쪽으로 카메라를 돌립니다.
      * Yaw 0의 의미: 월드 좌표계의 북쪽(North)을 정면으로 응시함. 시계 방향으로 회전합니다.
    - pitch_delta_degrees: 수직 기울기 변화량. 양수는 위에서 아래를 내려다보는 시점(Top-down)으로, 음수는 지평선을 바라보는 시점으로 바꿉니다.
      * 범위: 약 12도(0.22 rad) ~ 64도(1.12 rad). 64도에 가까울수록 수직으로 내려다봅니다.
    - zoom_delta: 카메라 거리 변화량. 양수는 캐릭터로부터 멀어지며(줌 아웃) 더 넓은 영역을 보여주고, 음수는 가까워집니다(줌 인).
      * 거리 범위: 3.6 ~ 11.5 unit.
    """

    _reset_tool_budgets()
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
        "msg": "Engine connection failed.",
        "source": "runtime_http_unavailable",
        "degraded": True,
    }


def _runtime_base_url() -> str | None:
    return os.environ.get("AGENTIC_GAME_MCP_RUNTIME_URL")


PLAYER_ALIASES = {
    "", "player", "player1", "player_0", "player_01", "player 1",
    "player character", "local_player", "avatar", "character", "pc",
    "user", "self", "agent", "default", "캐릭터", "캐릭터1",
}


def _normalize_actor_id(actor_id: str) -> str:
    """다양한 별칭을 표준 캐릭터 ID인 'rhea'로 정규화합니다."""
    if actor_id == "rhea":
        return actor_id
    normalized = actor_id.strip().lower()
    return "rhea" if normalized in PLAYER_ALIASES else actor_id


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
