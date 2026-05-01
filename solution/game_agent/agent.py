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
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "role": self.role
        }


# 에이전트 모델 프로필 정의 (4인 협력 체계)
# 전략가는 항상 Pro, 감독자는 태스크 유형에 따라 Pro/Flash 가변 적용
SUPERVISOR_PRO = AgentModelProfile(
    agent_name="supervisor_pro",
    model="gemini-3.1-pro-preview",
    role="[복잡한 추론 중심] 고차원적 논리 판단과 전체 프로세스 지휘 및 결과 검증 담당",
)
SUPERVISOR_FLASH = AgentModelProfile(
    agent_name="supervisor_flash",
    model="gemini-3-flash-preview",
    role="[실시간 대응 중심] 물리적 정체 감지 및 빠른 실행 결과 대조 담당",
)
STRATEGY_AGENT = AgentModelProfile(
    agent_name="strategist_agent",
    model="gemini-3.1-pro-preview",
    role="관측 데이터를 기반으로 한 명확한 목표 수립 및 정밀 물리 계산 담당",
)
OBSERVER_AGENT = AgentModelProfile(
    agent_name="observer_agent",
    model="gemini-3-flash-preview",
    role="게임 상태 및 시각 정보(스크린샷)의 정밀 포착 및 데이터화 담당",
)
ACTOR_AGENT = AgentModelProfile(
    agent_name="actor_agent",
    model="gemini-3-flash-preview",
    role="수립된 전략에 따른 최적의 키 입력 시퀀스 실행 담당",
)


def workshop_model_profiles() -> list[dict[str, str]]:
    """워크숍 UI에서 표시할 모델 프로필 목록을 반환합니다."""
    return [
        SUPERVISOR_PRO.as_dict(),
        SUPERVISOR_FLASH.as_dict(),
        STRATEGY_AGENT.as_dict(),
        OBSERVER_AGENT.as_dict(),
        ACTOR_AGENT.as_dict(),
    ]


DEFAULT_MODEL = SUPERVISOR_PRO.model

CONTROLLER_INSTRUCTION = """
3D 게임 QA 제어 가이드:

1. 행동 및 관측 규칙:
- 한 번의 도구 호출에 포함되는 프레임은 최대 5개로 제한함.
- 이동 후 반드시 주변 상태를 다시 파악하여 전략을 수정함.
- **시간 분석:** `current_time`과 이벤트 `timestamp`를 대조하여 자신의 행동 이후에 발생한 변화만 결과로 인정함.

2. 이동 및 물리 (Yaw 0 = 북쪽):
- 물리 상수: 걷기 0.24, 뛰기 0.48 (100ms당 이동 거리).
- 이동 후 실제 좌표 변화가 예상치의 80% 미만이면 정체로 판단함.

3. 정체 회복 및 이벤트 관리:
- 정체 감지 시: 후진(S) 0.3초 -> 옆걸음(A 또는 D) 0.3초와 점프 병행 -> 재진입 시도.
- **최신성 우선:** 이벤트 로그는 최신순으로 정렬되어 제공됨. 상단의 이벤트를 우선 분석할 것.
- 퍼즐이나 대화 내용은 기록 도구를 사용하여 메모리에 보관함.
- 목표 달성 시 즉시 루프를 종료함.
""".strip()


def build_loop_agent(model: str = DEFAULT_MODEL) -> LoopAgent:
    """최상위 Loop 에이전트를 생성합니다.
    관측자-전략가-행동가-감독자로 이어지는 전문 협업 시퀀스를 구성합니다.
    """
    # 현재 태스크 유형에 맞는 감독자 프로필 선택
    supervisor_profile = SUPERVISOR_PRO
    if any(kw in model.lower() for kw in ["maze", "puzzle", "flash"]):
        supervisor_profile = SUPERVISOR_FLASH

    return LoopAgent(
        name="multi_agent_collaboration_loop",
        description="전문 지침을 가진 에이전트들이 순차적으로 협력하여 미션을 수행합니다.",
        sub_agents=[
            build_controller_agent(OBSERVER_AGENT),  # 1. 정보 수집
            build_controller_agent(STRATEGY_AGENT),  # 2. 작전 설계
            build_controller_agent(ACTOR_AGENT),     # 3. 현장 실행
            build_controller_agent(supervisor_profile),  # 4. 결과 검증 및 피드백
        ],
        max_iterations=8,
    )


# 에이전트별 전문 지침
SUPERVISOR_INSTRUCTION = """
작전 총괄 및 결과 검증:
1. 계획 검토: 전략가의 시간 계획과 물리 상수 대조 및 확인.
2. 정체 판단: 2턴 이상 위치 변화가 없으면 시점 변경 후 새로운 경로 지시.
3. 상황 추론: 대화 기록과 인벤토리 상태를 조합해 다음 목적지 결정.
4. 토큰 관리: 불필요한 반복 관측 지양 및 필수 상황에서만 스크린샷 요청.
"""

STRATEGY_INSTRUCTION = """
경로 설계 및 시간 계산:
1. 프레임 설계: 한 번의 작전 설계 시 이동 경로를 최대 5개 프레임 이내로 구성.
2. 물리 계산: 목표 거리를 물리 상수(0.24 또는 0.48)로 나누어 정확한 입력 시간 산출.
3. 효율적 관측: 정보가 충분할 경우 `include_screenshot=False`로 상태 확인 및 토큰 절약.
4. 시점 선행: 이동 전 카메라 회전으로 정면 시야 확보.
"""

OBSERVER_INSTRUCTION = """
데이터 및 이벤트 관측:
1. 상태 보고: 현재 좌표(x, z)와 목표물까지의 거리, 카메라 각도 보고.
2. 효율적 도구 사용: 시각적 변화가 클 때만 `include_screenshot=True` 사용, 단순 위치 확인은 False로 호출.
3. 로그 기록: 퍼즐 시퀀스와 대화 내용을 `PUZZLE_LOG` 형식으로 메모리에 저장.
"""

ACTOR_INSTRUCTION = """
입력 실행 및 실시간 보정:
1. 실행 제한: 제안된 경로 중 상위 5개 프레임만 실행 후 결과 확인.
2. 회복 기동: 충돌 발생 시 즉시 중단 및 정체 회복 절차(후진 후 옆걸음) 실행.
3. 물리 피드백: 조작 전후의 좌표(x, z) 변화 수치 보고 및 전략 수정 기여.
"""


def build_controller_agent(profile: AgentModelProfile) -> LlmAgent:
    """역할에 특화된 에이전트를 생성합니다."""
    # 에이전트 이름에 포함된 키워드로 지침 매핑
    instruction = "게임 QA 에이전트"
    if "supervisor" in profile.agent_name:
        instruction = SUPERVISOR_INSTRUCTION
    elif "strategist" in profile.agent_name:
        instruction = STRATEGY_INSTRUCTION
    elif "observer" in profile.agent_name:
        instruction = OBSERVER_INSTRUCTION
    elif "actor" in profile.agent_name:
        instruction = ACTOR_INSTRUCTION

    return LlmAgent(
        model=profile.model,
        name=profile.agent_name,
        description=profile.role,
        instruction=instruction.strip(),
        tools=[build_mcp_toolset(), exit_loop],
    )


# 모델 선택을 위한 라우팅 규칙 정의 (태스크 성격에 따른 정밀 배정)
MODEL_ROUTING_TABLE = [
    {
        "profile": SUPERVISOR_PRO,
        "keywords": ["퀘스트", "대화", "npc", "아이템", "스토리"],
    },
    {
        "profile": SUPERVISOR_FLASH,
        "keywords": ["미로", "퍼즐", "탈출", "조작", "보기", "상태"],
    },
    {
        "profile": STRATEGY_AGENT,
        "keywords": ["전략", "계획", "진단", "로직", "목표", "방법", "해결"],
    },
    {
        "profile": OBSERVER_AGENT,
        "keywords": ["관측", "보기", "화면", "무엇", "상황", "주변", "정보"],
        "requires_screenshot": True,
    },
    {
        "profile": ACTOR_AGENT,
        "keywords": ["행동", "이동", "조작", "실행", "걷기", "뛰기", "입력", "wasd"],
    },
]


def select_model_profile(
    user_message: str,
    screenshot_data_url: str | None,
) -> AgentModelProfile:
    """사용자 메시지와 스크린샷 유무에 따라 최적의 모델 프로필을 선택합니다."""
    lowered_msg = user_message.lower()

    for rule in MODEL_ROUTING_TABLE:
        # 키워드가 포함되어 있고, (스크린샷 필수 조건이 없거나 스크린샷이 있는 경우) 해당 모델 선택
        if any(token in lowered_msg for token in rule["keywords"]):
            if not rule.get("requires_screenshot") or screenshot_data_url:
                return rule["profile"]

    return SUPERVISOR_PRO


def build_user_content(user_message: str, screenshot_data_url: str | None) -> types.Content:
    """사용자 메시지와 스크린샷 데이터를 Gemini API 형식으로 변환합니다."""
    parts: list[types.Part] = [types.Part(text=user_message)]
    if screenshot_data_url and "," in screenshot_data_url:
        _, encoded = screenshot_data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded)
        parts.append(
            types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        )
    return types.Content(role="user", parts=parts)


def validate_agent_answer(user_message: str, answer: str, state: dict[str, Any]) -> str:
    """에이전트의 답변을 그대로 반환합니다.
    성공 여부 판단은 에이전트의 지능과 도구 출력값에 맡깁니다."""
    return answer


# ADK run 명령어를 위해 기본 에이전트 인스턴스를 노출합니다.
root_agent = build_loop_agent()
