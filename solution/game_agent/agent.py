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
    agent_name="감독관",
    model="gemini-3-flash-preview",
    role="빠른 판단이 필요한 실습 시나리오 기획 및 도구 호출 담당",
)
QA_MODEL = AgentModelProfile(
    agent_name="QA_자동화",
    model="gemini-3.1-pro-preview",
    role="상태 정보와 스크린샷을 기반으로 한 정밀한 다단계 QA 추론 담당",
)
VISION_MODEL = AgentModelProfile(
    agent_name="시각_검증기",
    model="gemini-3.1-flash-lite-preview",
    role="대량의 캡처 데이터를 기반으로 한 빠른 시각적 상태 확인 담당",
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
당신은 실제 3D 게임 QA 환경에서 플레이어 캐릭터를 조작하는 에이전트입니다.

엄격한 규칙:
- 순간이동을 절대 사용하지 마세요. (도구가 제공되지 않음)
- 모델에게 좌표 정보를 직접 묻지 마세요.
- 숨겨진 경로 정보를 호출하거나 시나리오 지름길을 쓰지 마세요.
- 도구의 출력 상태(state)나 이벤트(events) 로그에 성공 메시지가 나타날 때까지 임의로 성공을 선언하지 마세요.
- 환경을 관찰하려면 inspect_game_state를 호출하세요.
- 캐릭터를 움직이거나 상호작용하려면 오직 apply_input_buffer만 사용하세요.
- 카메라 시점을 변경하려면 adjust_camera_view를 호출하세요. (yaw, pitch, zoom 조절 가능)
- 사용 가능한 입력 키는 KeyW, KeyA, KeyS, KeyD, ShiftLeft, Space, KeyE 입니다.
- camera_yaw_degrees=0일 때, KeyW는 북쪽, KeyS는 남쪽, KeyD는 동쪽, KeyA는 서쪽으로 움직입니다.
- 짧은 '관찰 -> 행동 -> 관찰' 루프를 유지하세요.
- 미로를 시작하거나 탈출할 때는 마커 안으로 이동하거나 KeyE를 눌러 상호작용하세요.
- 요청이 완료되었거나 충분한 증거를 확보했다면 exit_loop을 호출하여 작업을 종료하세요.

최종 답변은 간결하게 작성하세요: 전송한 키 입력 목록과 관찰된 결과를 요약해서 답변하세요.
""".strip()


def build_loop_agent(model: str = DEFAULT_MODEL) -> LoopAgent:
    """최상위 Loop 에이전트를 생성합니다."""
    return LoopAgent(
        name="게임_에이전트_루프",
        description="MCP 도구를 활용해 관찰-행동-검증 과정을 반복하는 ADK 루프 에이전트입니다.",
        sub_agents=[build_controller_agent(model=model)],
        max_iterations=15,
    )


def build_controller_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """핵심 컨트롤러 에이전트를 생성합니다."""
    return LlmAgent(
        model=model,
        name="게임_조작_에이전트",
        description="실제 플레이어와 동일한 입력 버퍼 방식으로 3D 게임을 제어합니다.",
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
