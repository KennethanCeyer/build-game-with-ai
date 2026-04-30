from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from agentic_game_engine.game.model_config import DIRECTOR_MODEL


# MCP 서버 모듈 및 기본 모델 설정
# 시스템 가동에 필요한 핵심 변수를 정의합니다.
MCP_SERVER_MODULE = "agentic_game_engine.mcp_server"
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8787"
DEFAULT_MODEL = DIRECTOR_MODEL.model

CONTROLLER_INSTRUCTION = """
실시간 3D 게임 환경에서 캐릭터를 조작하기 위한 동작 지침입니다.

주요 규칙:
- 캐릭터 이동은 WASD 키 입력만을 사용하며 좌표값을 직접 수정하지 않습니다.
- 도구 실행 결과에서 성공 상태가 확인된 경우에만 임무 완수로 판단합니다.
- 캐릭터 rhea를 조작하기 위해 apply_input_buffer 도구를 사용합니다.
- 허용된 입력 키는 KeyW, KeyA, KeyS, KeyD, ShiftLeft, Space, KeyE입니다.
- 게임 상태를 파악하기 위해 inspect_game_state 도구를 우선적으로 호출합니다.
- 화면 시점 조정이 필요한 경우 adjust_camera_view 도구를 사용합니다.
- 목표 지점이 먼 경우 이동 도구를 반복 호출하며 상태 변화를 관찰합니다.
- 작업 완료 조건이 충족되면 즉시 exit_loop를 호출하여 수행을 종료합니다.
- 모든 답변은 한국어로 기술합니다.
""".strip()


def build_loop_agent(
    model: str = DEFAULT_MODEL,
    runtime_url: str = DEFAULT_RUNTIME_URL,
) -> LoopAgent:
    """
    에이전트가 목표를 달성할 때까지 관찰과 판단을 지속하도록 제어 루프를 구성합니다.
    """
    return LoopAgent(
        name="agentic_game_loop",
        description="게임 미션 완수를 위해 하위 에이전트를 반복 실행하는 제어 객체입니다.",
        
        # 실습 1: 하위 에이전트 등록
        # LoopAgent는 등록된 하위 에이전트에게 실제 작업을 위임합니다.
        # 동작 지침이 포함된 build_controller_agent 함수 호출 결과를 리스트에 추가합니다.
        sub_agents=[
            # TODO: build_controller_agent(model=model, runtime_url=runtime_url)를 추가하세요.
        ],
        
        # 실습 2: 반복 횟수 제한 설정
        # 에이전트가 목표를 달성하지 못하고 무한히 실행되는 것을 방지합니다.
        # 작업의 복잡도를 고려하여 반복 횟수를 15회로 수정합니다.
        max_iterations=1,  # TODO: 값을 15로 수정하여 충분한 실행 기회를 부여하세요.
    )


def build_controller_agent(
    model: str = DEFAULT_MODEL,
    runtime_url: str = DEFAULT_RUNTIME_URL,
) -> LlmAgent:
    """
    언어 모델을 기반으로 상황을 분석하고 실행할 도구를 결정하는 에이전트를 생성합니다.
    """
    return LlmAgent(
        model=model,
        name="agentic_game_controller",
        description="게임 엔진과 통신하여 동작을 결정하는 실행 에이전트입니다.",
        instruction=CONTROLLER_INSTRUCTION,
        
        # 실습 3: 도구 목록 연결
        # 에이전트가 환경에 개입하기 위해 사용할 도구들을 등록합니다.
        # 게임 조작 기능을 제공하는 build_mcp_toolset과 종료 기능을 담당하는 exit_loop를 추가합니다.
        tools=[
            # TODO: build_mcp_toolset(runtime_url)과 exit_loop를 리스트에 추가하세요.
        ],
    )


def build_mcp_toolset(runtime_url: str = DEFAULT_RUNTIME_URL) -> McpToolset:
    """
    에이전트와 게임 엔진 사이의 통신 규약을 설정하고 도구 서버를 가동합니다.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                
                # 실습 4: 실행 인자 설정
                # 파이썬 명령어로 도구 서버 파일을 모듈 단위로 실행하도록 설정합니다.
                # 리스트에 모듈 실행 옵션인 -m과 모듈 경로 변수를 차례대로 입력합니다.
                args=[
                    # TODO: ["-m", MCP_SERVER_MODULE] 형태로 인자를 구성하세요.
                ],
                env=_mcp_environment(runtime_url),
            ),
        ),
    )


def _mcp_environment(runtime_url: str) -> dict[str, str]:
    """도구 서버 실행 시 필요한 경로와 접속 정보를 환경 변수로 설정합니다."""
    env = dict(os.environ)
    src_path = str(Path(__file__).resolve().parents[2] / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_path
    )
    env["AGENTIC_GAME_MCP_RUNTIME_URL"] = runtime_url
    return env
