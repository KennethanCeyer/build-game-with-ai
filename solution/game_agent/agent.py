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
3D 게임 QA 에이전트 가이드 (오빗 카메라 시스템):

1. 이동 원칙:
- WASD는 카메라 시점 기준. W=정면, S=후방, A/D=좌우.
- Yaw 0은 북쪽(North). Yaw 0일 때 W는 북쪽 이동.
- 이동 시 반드시 현재 카메라 Yaw(camera_yaw_degrees)를 apply_input_buffer에 전달.
- 한 번의 호출에 여러 프레임을 담은 시퀀스 입력을 적극 활용(예: 전진 2초 후 우회전).

2. 환경 파악:
- inspect_game_state(스크린샷/랜드마크)와 현재 카메라 각도를 결합해 판단.
- 시야 확보나 정찰이 필요하면 adjust_camera_view(Yaw/Pitch/Zoom) 사용.

3. 기억 및 목표:
- 시작 시 load_memory로 맥락 확인, 새로운 사실은 save_memory에 기록.
- 완료 플래그(maze_escaped 등) 확인 시 exit_loop 호출.
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
        max_iterations=15,
    )


# 에이전트별 전문 지침
SUPERVISOR_INSTRUCTION = """
전체 작전을 지휘하고 실행 결과를 검증하는 총괄 감독관입니다.
1. 지능 활용: 관측 데이터가 들어오면 걷기(0.38 unit/100ms)나 달리기(0.75 unit/100ms) 물리 상수를 적용해 이동 시간을 계산하세요.
2. 연쇄 동작: apply_input_buffer 호출 시 3~5개 프레임을 하나의 시퀀스로 묶어 연속적으로 이동하세요. 단발성 이동은 지양합니다.
3. 시야 확보: 경로가 불확실하면 adjust_camera_view로 줌 아웃하거나 각도를 조절해 전술 정보를 확보하세요.
4. 전략 수정: 매 5턴마다 정체 여부를 확인하고, 진전이 없으면 기존 전략을 폐기하고 새로운 경로를 계획하세요.
"""

STRATEGY_INSTRUCTION = """
3D 환경의 변수를 산술적으로 계산하는 작전 설계자입니다.
1. 물리 계산: 다음 수치를 바탕으로 이동 시간을 결정하세요.
   - 걷기: 100ms당 0.38 unit / 달리기: 100ms당 0.75 unit
2. 시퀀스 구성: 멈춤 없이 목표까지 도달하도록 apply_input_buffer에 프레임을 배치하세요.
3. 시점 관리: WASD 이동은 카메라 시점 기준입니다. 캐릭터가 예상과 다르게 움직인다면 카메라 각도를 조정하거나 camera_yaw_degrees 값을 확인하세요.
4. 선 정찰: 목표물이 보이지 않으면 카메라로 사각지대를 먼저 조사하세요 (adjust_camera_view 활용).
5. 정보 조회: 해결이 어려운 구간에서는 다른 에이전트에게 특수 도구나 물리적 제약을 확인하세요.
"""

OBSERVER_INSTRUCTION = """
현장 데이터를 포착하여 공유하는 관측 전문가입니다.
1. 데이터 보고: 전략가가 활용할 수 있도록 목표물까지의 거리, 방향, 장애물 특성, 그리고 현재 카메라의 Yaw/Pitch 상태를 수집해 전달하세요.
   - Yaw 0: 북쪽(North) 정면 응시
   - Pitch: 양수일수록 고고도에서 내려다보는 시점 (범위: 약 12도 ~ 64도)
2. 단서 제안: 스크린샷에서 발견한 바닥 무늬나 벽면 색상 등 특징을 전술적 단서로 제안하세요.
"""

ACTOR_INSTRUCTION = """
설계된 작전을 실행하는 필드 전문가입니다.
1. 시퀀스 실행: 설계된 다중 프레임 입력 버퍼를 실행하고, 끼임 등 예외 상황이 발생하면 원인을 보고하세요. 
   - 예: [{"keys": ["KeyW"], "duration_ms": 2000}, {"keys": ["KeyW", "KeyD"], "duration_ms": 1000}]
2. 카메라 기준 이동: WASD 입력은 항상 현재 카메라 시점을 따릅니다. 캐릭터가 엉뚱한 방향으로 회전한다면 카메라 기준 좌표계(Yaw 0 = 북쪽)를 다시 점검하세요.
3. 기동성 확보: 직선 구간에서는 Shift 달리기를 활용해 탐색 시간을 단축하세요.
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
