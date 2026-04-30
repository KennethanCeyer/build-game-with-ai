from __future__ import annotations

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop

from .tools import build_mcp_toolset

# TODO(starter-2): use the default fast model for the workshop controller.
DEFAULT_MODEL = ...

CONTROLLER_INSTRUCTION = """
You control the player character in a live 3D game QA scene.

... (TODO(starter-2): describe the persona and rules for the agent) ...
""".strip()


def build_loop_agent(model: str = DEFAULT_MODEL) -> LoopAgent:
    """
    최상위 Loop 에이전트를 생성합니다. 
    TODO(starter-3): LoopAgent를 반환하도록 구현하세요. 
    이 에이전트는 하위 에이전트(build_controller_agent)를 실행해야 합니다.
    """
    return LoopAgent(
        name="agentic_game_loop",
        sub_agents=[build_controller_agent(model=model)],
        max_iterations=15,
    )


def build_controller_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """
    게임 월드와 상호작용하고 추론을 수행하는 핵심 에이전트를 생성합니다.
    TODO(starter-4): LlmAgent를 반환하도록 구현하세요.
    에이전트에게 필요한 도구(MCP Toolset, exit_loop)를 등록해야 합니다.
    """
    return LlmAgent(
        model=model,
        name="agentic_game_controller",
        instruction=CONTROLLER_INSTRUCTION,
        tools=[build_mcp_toolset(), exit_loop],
    )
