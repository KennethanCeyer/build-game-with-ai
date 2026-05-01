from __future__ import annotations

from urllib import request
from urllib.error import URLError
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp import types

from engine.game.game_observation import agent_visible_state
import logging

# MCP INFO 로그 억제
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("mcp.server").setLevel(logging.WARNING)
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

# 에이전트의 작업 기억을 보관하기 위한 전역 변수
_agent_working_memory: str = "미로 탈출 및 NPC 퀘스트 수행 중. 기록된 세부 기억 없음."


@mcp.tool()
def save_memory(insight: str) -> str:
    """판단, 이동 경로, 발견 사실 등 중요 정보를 작업 기억에 저장.
    load_memory를 통해 정보 확인 가능.
    """
    global _agent_working_memory
    _agent_working_memory = insight
    return "기억 저장 성공."


@mcp.tool()
def load_memory() -> str:
    """저장된 작업 기억 불러오기.
    이전 계획이나 실패 경로 복기 시 사용.
    """
    global _agent_working_memory
    return f"보관된 기억: {_agent_working_memory}"


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
        "message": "진단 정보 획득 실패. 엔진 통신 상태 확인 필요."
    }


@mcp.tool()
def inspect_game_state(include_screenshot: bool = True) -> types.TextContent | list[types.TextContent | types.ImageContent]:
    """현재 게임 월드 상태 정보 조회.
    캐릭터 위치, 주변 장애물, 퀘스트 진행 상황 포함.
    시각 확인 필요 시에만 include_screenshot=True 사용 (TPM 절약).
    """
    runtime_state = _runtime_get("/api/state")
    if runtime_state is not None:
        state_data = runtime_state.get("state", {})
        landmarks = state_data.get("visible_landmarks", [])
        nav_guides = []
        for lm in landmarks:
            name = lm.get("name", "Unknown")
            dist = lm.get("distance_label", "unknown")
            rel_x = lm.get("relative_x", 0)
            rel_z = lm.get("relative_z", 0)
            
            direction = []
            if rel_z < -1: direction.append("North")
            elif rel_z > 1: direction.append("South")
            if rel_x < -1: direction.append("West")
            elif rel_x > 1: direction.append("East")
            nav_guides.append(f"- {name}: {"-".join(direction) or "center"} ({dist})")
        
        guide_text = "\n".join(nav_guides) if nav_guides else "No landmarks visible."

        state_json = json.dumps(
            {"ok": True, "state": agent_visible_state(state_data)},
            ensure_ascii=False
        )
        content: list[types.TextContent | types.ImageContent] = [
            types.TextContent(
                type="text",
                text=f"State JSON: {state_json}\nLandmarks: {guide_text}"
            )
        ]
        
        if include_screenshot:
            screenshot_url = runtime_state.get("screenshot")
            if screenshot_url and "," in screenshot_url:
                try:
                    fmt, b64_data = screenshot_url.split(",", 1)
                    mime = fmt.split(":")[1].split(";")[0]
                    content.append(types.ImageContent(
                        type="image",
                        data=b64_data,
                        mimeType=mime
                    ))
                except Exception:
                    pass
                
        return content

    return types.TextContent(
        type="text",
        text=json.dumps({"ok": False, "msg": "Engine connection failed."}, ensure_ascii=False)
    )


@mcp.tool()
def apply_input_buffer(
    frames: list[dict[str, Any]],
    actor_id: str = "rhea",
    camera_yaw_degrees: float = 0.0,
) -> dict[str, Any]:
    """일련의 입력 프레임(WASD, Shift, Space, E)을 전송하여 캐릭터를 조작합니다.
    [중요] 캐릭터 이동은 카메라 시점을 기준으로 결정됩니다.
    """
    normalized_actor_id = _normalize_actor_id(actor_id)
    if normalized_actor_id != "rhea":
        return {"ok": False, "msg": "Only 'rhea' can be controlled."}

    runtime_result = _runtime_post(
        "/api/input-buffer",
        {
            "actor_id": normalized_actor_id,
            "frames": frames,
            "camera_yaw_degrees": camera_yaw_degrees,
        },
    )
    if runtime_result is not None:
        return {
            "ok": True,
            "state": agent_visible_state(runtime_result.get("state", {}))
        }

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
