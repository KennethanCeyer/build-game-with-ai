from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop
from google.genai import types

from .tools import build_mcp_toolset


@dataclass(frozen=True)
class AgentModelProfile:
    agent_name: str
    model: str
    role: str

    def as_dict(self) -> dict[str, str]:
        return {"agent_name": self.agent_name, "model": self.model, "role": self.role}


# 에이전트 모델 프로필 정의
DIRECTOR_MODEL = AgentModelProfile(
    agent_name="director",
    model="gemini-3-flash-preview",
    role="Fast workshop-facing planner and tool caller.",
)
QA_MODEL = AgentModelProfile(
    agent_name="qa_automation",
    model="gemini-3.1-pro-preview",
    role="Careful multi-step QA reasoning over state, screenshots, and expected outcomes.",
)
VISION_MODEL = AgentModelProfile(
    agent_name="vision_verifier",
    model="gemini-3.1-flash-lite-preview",
    role="Fast screenshot confirmation for capture-heavy hands-on steps.",
)


def workshop_model_profiles() -> list[dict[str, str]]:
    """워크숍 UI에서 표시할 모델 프로필 목록을 반환합니다."""
    return [
        DIRECTOR_MODEL.as_dict(),
        QA_MODEL.as_dict(),
        VISION_MODEL.as_dict(),
    ]


DEFAULT_MODEL = DIRECTOR_MODEL.model

CONTROLLER_INSTRUCTION = """
You control the player character in a live 3D game QA scene.

Hard rules:
- Never teleport.
- Never ask for direct coordinates.
- Never call hidden routes or scenario shortcuts.
- Never claim success until tool output state/events show success.
- To observe, call inspect_game_state.
- To move or interact, call apply_input_buffer only.
- To change the camera view (yaw, pitch, zoom), call adjust_camera_view.
- Allowed input keys are KeyW, KeyA, KeyS, KeyD, ShiftLeft, Space, and KeyE.
- With camera_yaw_degrees=0, KeyW moves north, KeyS south, KeyD east, and KeyA west.
- Use short observe -> act -> observe loops.
- When the request is answered or you have enough evidence, call exit_loop.

Keep the final answer short: list the keys sent and the observed result.
""".strip()


def build_loop_agent(model: str = DEFAULT_MODEL) -> LoopAgent:
    """최상위 Loop 에이전트를 생성합니다."""
    return LoopAgent(
        name="agentic_game_loop",
        description="ADK LoopAgent for repeated inspect-act-verify game QA steps over MCP tools.",
        sub_agents=[build_controller_agent(model=model)],
        max_iterations=15,
    )


def build_controller_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """핵심 컨트롤러 에이전트를 생성합니다."""
    return LlmAgent(
        model=model,
        name="agentic_game_controller",
        description="Controls the live 3D game only through player-equivalent input buffers.",
        instruction=CONTROLLER_INSTRUCTION,
        tools=[build_mcp_toolset(), exit_loop],
    )


def select_model_profile(
    user_message: str,
    screenshot_data_url: str | None,
) -> AgentModelProfile:
    """사용자 메시지와 스크린샷 유무에 따라 최적의 모델 프로필을 선택합니다."""
    lowered = user_message.lower()
    pro_tokens = [
        "전체",
        "계획",
        "복잡",
        "추론",
        "trace",
        "트레이스",
        "분석",
        "리포트",
        "검증",
        "end-to-end",
    ]
    if any(token in lowered for token in pro_tokens):
        return QA_MODEL

    solve_tokens = [
        "풀",
        "탈출",
        "완료",
        "진행",
        "퀘스트",
        "quest",
        "npc",
        "퍼즐",
        "puzzle",
        "미로",
    ]
    if any(token in lowered for token in solve_tokens):
        return DIRECTOR_MODEL

    if screenshot_data_url and any(
        token in lowered for token in ["화면", "캡쳐", "관찰", "보고", "status"]
    ):
        return VISION_MODEL

    return DIRECTOR_MODEL


def build_user_content(user_message: str, screenshot_data_url: str | None) -> types.Content:
    """사용자 메시지와 스크린샷 데이터를 Gemini API 형식으로 변환합니다."""
    parts: list[types.Part] = [types.Part(text=user_message)]
    if screenshot_data_url and "," in screenshot_data_url:
        _, encoded = screenshot_data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded)
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
    return types.Content(role="user", parts=parts)


def validate_agent_answer(user_message: str, answer: str, state: dict[str, Any]) -> str:
    """에이전트의 답변을 추가 검증 없이 그대로 반환합니다.
    성공 여부 판단은 에이전트의 지능과 도구 출력값에 맡깁니다."""
    return answer
