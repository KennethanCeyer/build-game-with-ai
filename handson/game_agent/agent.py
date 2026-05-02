from __future__ import annotations

import base64
from dataclasses import dataclass

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop
from google.genai import types

from .tools import build_agent_toolset

MAX_SCREENSHOT_DATA_URL_CHARS = 350_000


@dataclass(frozen=True)
class AgentModelProfile:
    agent_name: str
    model: str
    role: str

    def as_dict(self) -> dict[str, str]:
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "role": self.role,
        }


SUPERVISOR_PRO = AgentModelProfile(
    "supervisor_agent",
    "gemini-3.1-pro-preview",
    "[감독] 전체 지휘 및 결과 검증 담당",
)
STRATEGY_AGENT = AgentModelProfile(
    "strategist_agent",
    "gemini-3.1-pro-preview",
    "[설계] 전략 설계 담당",
)
ACTOR_AGENT = AgentModelProfile(
    "actor_agent",
    "gemini-3.1-pro-preview",
    "[행동] 키 입력 실행 담당",
)
OBSERVER_AGENT = AgentModelProfile(
    "observer_agent",
    "gemini-3.1-pro-preview",
    "[관측] 상태 및 시각 데이터 수집 담당",
)


def workshop_model_profiles() -> list[dict[str, str]]:
    return [
        SUPERVISOR_PRO.as_dict(),
        STRATEGY_AGENT.as_dict(),
        ACTOR_AGENT.as_dict(),
        OBSERVER_AGENT.as_dict(),
    ]


STATIC_GAME_RULES = """
[물리 법칙]
1. 이상적인 평지 속력은 걷기 3.8 unit/s, 뛰기 7.5 unit/s입니다.
2. 실제 이동거리는 충돌, actor radius, 벽 근접, 카메라 yaw, step discretization 때문에 더 짧아질 수 있습니다.
3. 대각선 이동은 정규화되므로 대각선이라고 더 빨라지지 않습니다.
4. 미로, 장애물, 상호작용 지점 근처에서는 긴 이동보다 짧은 입력 버퍼를 실행하고 재관측 후 보정하십시오.

[조작 기준]
모든 WASD 이동은 현재 camera_yaw_degrees 기준으로 계산됩니다.
현재 엔진 기준:
- Yaw 0도: W=-Z, S=+Z, A=-X, D=+X
- Yaw 90도: W=-X, S=+X, A=-Z, D=+Z
- Yaw 180도: W=+Z, S=-Z, A=+X, D=-X
- Yaw -90도 또는 270도: W=+X, S=-X, A=+Z, D=-Z

[상호작용]
nearby 필드에 입력값이 뜨면 KeyE를 사용하십시오.
"""


def build_loop_agent(model: str = "gemini-3.1-pro-preview") -> LoopAgent:
    # [문제 1] 관측자(observer)가 상황을 파악하기 위해 필요한 도구들을 연결하세요.
    # TODO: inspect_game_state, capture_visual_observation, capture_visual_crop 도구를 리스트에 추가하세요.
    observer = LlmAgent(
        name=OBSERVER_AGENT.agent_name,
        model=OBSERVER_AGENT.model,
        instruction=(
            f"당신은 [관측자]입니다. {OBSERVER_AGENT.role}\n"
            "모든 응답을 반드시 '[관측자]'로 시작하십시오.\n"
            "규칙:\n"
            "1. inspect_game_state를 정확히 한 번만 호출하여 구조화된 상태를 보강하십시오.\n"
            "2. 사용자 입력에 [visual_context]가 포함되어 있으면 이미 현재 화면을 본 것으로 간주하십시오.\n"
            "3. capture_visual_observation은 같은 턴에서 반복하지 마십시오.\n"
            "4. 정말 정밀한 확인이 필요한 경우에만 capture_visual_crop을 최대 한 번 호출하십시오.\n"
            "5. 관측 후 즉시 요약을 작성하고 종료하십시오."
        ),
        static_instruction=STATIC_GAME_RULES,
        tools=[
            build_agent_toolset(
                [
                    "inspect_game_state",
                    # "...", # TODO: 시각 관측 도구들을 추가하세요.
                    # "...",
                ]
            )
        ],
    )

    strategist = LlmAgent(
        name=STRATEGY_AGENT.agent_name,
        model=STRATEGY_AGENT.model,
        instruction=(
            f"당신은 [전략가]입니다. {STRATEGY_AGENT.role}\n"
            "모든 응답을 반드시 '[전략가]'로 시작하십시오.\n"
            "지침:\n"
            "- 도구를 호출하지 마십시오. 오직 텍스트 응답만 작성하십시오.\n"
            "- 관측자 결과를 바탕으로 행동가가 즉시 실행할 수 있는 JSON 계획을 최종 응답으로 작성하십시오.\n"
            "- 반드시 apply_input_buffer 형식의 frames를 사용하십시오.\n"
            "- keydown/keyup 이벤트 형식은 절대 사용하지 마십시오.\n"
            "- 미로, 장애물, 상호작용 지점 근처에서는 250ms에서 350ms 단위의 짧은 입력을 우선하십시오.\n"
            "- 형식 예시:\n"
            "{\n"
            '  "task": "maze_navigation",\n'
            '  "camera_yaw_degrees": 0,\n'
            '  "frames": [{"keys": ["KeyW"], "duration_ms": 300}],\n'
            '  "expected_result": "player moved closer to the corridor"\n'
            "}"
        ),
        static_instruction=STATIC_GAME_RULES,
        tools=[],
    )

    actor = LlmAgent(
        name=ACTOR_AGENT.agent_name,
        model=ACTOR_AGENT.model,
        instruction=(
            f"당신은 [행동가]입니다. {ACTOR_AGENT.role}\n"
            "모든 응답을 반드시 '[행동가]'로 시작하십시오.\n"
            "지침:\n"
            "- 전략가의 직전 응답에 포함된 frames와 camera_yaw_degrees를 읽으십시오.\n"
            "- apply_input_buffer를 정확히 한 번 호출하여 계획을 실행하십시오.\n"
            "- 실행 후 save_memory(key='qa.last_action', value=...)를 최대 한 번 호출하여 결과를 기록하고 종료하십시오.\n"
            "- 추가 계획 수립이나 재관측은 하지 마십시오."
        ),
        static_instruction=STATIC_GAME_RULES,
        tools=[build_agent_toolset(["apply_input_buffer", "save_memory"])],
    )

    # [문제 2] 관측, 전략 수립, 실행을 순차적으로 수행하는 파이프라인을 구축하세요.
    # TODO: SequentialAgent를 사용해 observer, strategist, actor를 순서대로 연결하세요.
    worker_pipeline = ...
    # worker_pipeline = SequentialAgent(
    #     name="worker_pipeline",
    #     description="QA 실행 파이프라인",
    #     sub_agents=[...],
    # )

    # [문제 3] 감독자(supervisor)가 파이프라인을 제어할 수 있도록 하위 에이전트로 등록하세요.
    # TODO: supervisor의 sub_agents 리스트에 위에서 만든 worker_pipeline을 추가하세요.
    supervisor = LlmAgent(
        name=SUPERVISOR_PRO.agent_name,
        model=model,
        instruction=(
            f"당신은 [감독자]입니다. {SUPERVISOR_PRO.role}\n"
            "모든 응답을 반드시 '[감독자]'로 시작하십시오.\n"
            "사용자 요청을 분석하여 worker_pipeline을 호출하십시오.\n"
            "worker_pipeline 실행 후 flags/status를 검증하십시오.\n"
            "목표가 달성되었으면 exit_loop를 호출하십시오.\n"
            "진행이 막혔거나 내부 상태 확인이 필요할 때만 diagnose_engine_state를 사용하십시오.\n"
            "이전 실패 경로 또는 실행 결과가 필요할 때만 load_memory를 사용하십시오."
        ),
        static_instruction=STATIC_GAME_RULES,
        tools=[exit_loop, build_agent_toolset(["load_memory", "diagnose_engine_state"])],
        sub_agents=[...],  # TODO: worker_pipeline을 등록하세요.
    )

    # [문제 4] 전체 시스템을 자율적으로 구동할 LoopAgent를 정의하세요.
    # [문제 5] 에이전트가 목표를 달성할 때까지 충분히 시도할 수 있도록 최대 반복 횟수를 설정하세요.
    # TODO: LoopAgent에 supervisor를 등록하고 max_iterations를 적절한 숫자(예: 50)로 설정하세요.
    return ...
    # return LoopAgent(
    #     name="agent_collaboration_system",
    #     sub_agents=[...],
    #     max_iterations=...,
    # )


def build_user_content(
    user_message: str,
    screenshot_data_url: str | None,
) -> types.Content:
    parts: list[types.Part] = [types.Part(text=user_message)]

    if screenshot_data_url:
        if len(screenshot_data_url) > MAX_SCREENSHOT_DATA_URL_CHARS:
            parts.append(
                types.Part(
                    text=(
                        "\n[visual_context]\n"
                        "화면 캡처가 너무 커서 모델 입력에서 제외되었습니다. "
                        "필요한 경우 제한된 시각 관측 도구(capture_visual_observation)를 사용하십시오."
                    )
                )
            )
            return types.Content(role="user", parts=parts)

        parts.append(
            types.Part(
                text=(
                    "\n[visual_context]\n"
                    "현재 화면 캡처가 이 메시지에 첨부되어 있습니다. "
                    "관측자는 같은 턴에서 추가 전체 화면 캡처(capture_visual_observation)를 반복하지 마십시오. "
                    "구조화된 데이터 보강(inspect_game_state) 또는 정밀 확인(capture_visual_crop)을 우선 사용하십시오."
                )
            )
        )

        if "," in screenshot_data_url:
            fmt, b64_data = screenshot_data_url.split(",", 1)
            mime = fmt.split(":")[1].split(";")[0]
            parts.append(
                types.Part.from_bytes(
                    data=base64.b64decode(b64_data),
                    mime_type=mime,
                )
            )

    return types.Content(role="user", parts=parts)


root_agent = build_loop_agent()
