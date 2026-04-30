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


# TODO(실습-2): 실습 상황에 맞는 모델 프로필을 정의하세요.
DIRECTOR_MODEL = AgentModelProfile(
    agent_name="director",
    model="gemini-3-flash-preview",
    role="Fast workshop-facing planner and tool caller.",
)
QA_MODEL = AgentModelProfile(
    agent_name="qa_automation",
    model="gemini-3.1-pro-preview",
    role="Careful multi-step QA reasoning.",
)
VISION_MODEL = AgentModelProfile(
    agent_name="vision_verifier",
    model="gemini-3.1-flash-lite-preview",
    role="Fast screenshot confirmation.",
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
... (TODO: 에이전트의 페르소나와 행동 지침을 작성하세요) ...
""".strip()


def build_loop_agent(model: str = DEFAULT_MODEL) -> LoopAgent:
    """최상위 Loop 에이전트를 생성합니다."""
    # TODO(실습-3): LoopAgent를 반환하도록 구현하세요.
    return LoopAgent(
        name="agentic_game_loop",
        sub_agents=[build_controller_agent(model=model)],
        max_iterations=15,
    )


def build_controller_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """핵심 컨트롤러 에이전트를 생성합니다."""
    # TODO(실습-4): LlmAgent를 반환하고 필요한 도구를 등록하세요.
    return LlmAgent(
        model=model,
        name="agentic_game_controller",
        instruction=CONTROLLER_INSTRUCTION,
        tools=[build_mcp_toolset(), exit_loop],
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
    # Hint: screenshot_data_url에서 데이터를 추출하고 base64.b64decode를 사용하세요.
    return types.Content(role="user", parts=parts)


def validate_agent_answer(user_message: str, answer: str, state: dict[str, Any]) -> str:
    """
    에이전트의 답변을 검증 없이 반환합니다.
    TODO(실습-8): 에이전트가 도구 출력값(tool_response)을 통해 스스로 성공 여부를
    판단할 수 있도록 지침(Instruction)을 보강해 보세요.
    """
    return answer
