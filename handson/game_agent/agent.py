from __future__ import annotations

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


# TODO(실습-2): 실습 상황에 맞는 모델 프로필을 정의하세요.
DIRECTOR_MODEL = AgentModelProfile(
    agent_name="감독관",
    model="TODO_모델명_입력",  # 예: gemini-3-flash-preview
    role="빠른 판단이 필요한 실습 시나리오 기획 및 도구 호출 담당",
)
QA_MODEL = AgentModelProfile(
    agent_name="QA_자동화",
    model="TODO_모델명_입력",  # 예: gemini-3.1-pro-preview
    role="상태 정보와 스크린샷을 기반으로 한 정밀한 다단계 QA 추론 담당",
)
VISION_MODEL = AgentModelProfile(
    agent_name="시각_검증기",
    model="TODO_모델명_입력",  # 예: gemini-3.1-flash-lite-preview
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
- 환경을 관찰하려면 inspect_game_state를 호출하세요.
- 캐릭터를 움직이거나 상호작용하려면 오직 apply_input_buffer만 사용하세요.
- 사용 가능한 입력 키는 KeyW, KeyA, KeyS, KeyD, ShiftLeft, Space, KeyE 입니다.
- 짧은 '관찰 -> 행동 -> 관찰' 루프를 유지하세요.
- 요청이 완료되었거나 충분한 증거를 확보했다면 exit_loop을 호출하여 작업을 종료하세요.

(여기에 추가적인 행동 지침을 작성하여 에이전트의 지능을 높여보세요)
""".strip()


def build_loop_agent(model: str = DEFAULT_MODEL) -> LoopAgent:
    """최상위 Loop 에이전트를 생성합니다."""
    # TODO(실습-3): LoopAgent를 반환하도록 구현하세요.
    # 힌트: sub_agents=[build_controller_agent(model=model)], max_iterations=15
    return LoopAgent(
        name="게임_에이전트_루프",
        sub_agents=[],
        max_iterations=0,
    )


def build_controller_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """핵심 컨트롤러 에이전트를 생성합니다."""
    # TODO(실습-4): LlmAgent를 반환하고 필요한 도구를 등록하세요.
    # 힌트: instruction=CONTROLLER_INSTRUCTION, tools=[build_mcp_toolset(), exit_loop]
    return LlmAgent(
        model=model,
        name="게임_조작_에이전트",
        instruction="",
        tools=[],
    )


def select_model_profile(
    user_message: str,
    screenshot_data_url: str | None,
) -> AgentModelProfile:
    """
    TODO(실습-6): 사용자 메시지의 키워드나 스크린샷 유무에 따라 어떤 모델을 쓸지 결정하는 로직을 작성하세요.
    예: "분석"이 포함되면 QA_MODEL, "미로"가 포함되면 DIRECTOR_MODEL 등
    """
    return DIRECTOR_MODEL


def build_user_content(user_message: str, screenshot_data_url: str | None) -> types.Content:
    """
    TODO(실습-7): 사용자 메시지와 스크린샷(base64)을 Gemini Content 형식으로 변환하세요.
    """
    parts: list[types.Part] = [types.Part(text=user_message)]
    # 힌트: screenshot_data_url에서 데이터를 추출하고 base64.b64decode를 사용하세요.
    return types.Content(role="user", parts=parts)


def validate_agent_answer(user_message: str, answer: str, state: dict[str, Any]) -> str:
    """
    에이전트의 답변을 검증 없이 반환합니다.
    TODO(실습-8): 에이전트가 도구 출력값(tool_response)을 통해 스스로 성공 여부를
    판단할 수 있도록 지침(Instruction)을 보강해 보세요.
    """
    return answer
