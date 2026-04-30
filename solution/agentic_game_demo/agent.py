from __future__ import annotations

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop

from .tools import build_mcp_toolset

DEFAULT_MODEL = "gemini-3-flash-preview"

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
    """최상위 Loop 에이전트를 생성합니다. 컨트롤러가 목표를 달성할 때까지 반복 실행합니다."""
    return LoopAgent(
        name="agentic_game_loop",
        description="ADK LoopAgent for repeated inspect-act-verify game QA steps over MCP tools.",
        sub_agents=[build_controller_agent(model=model)],
        max_iterations=15,
    )


def build_controller_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """게임 월드와 상호작용하고 추론을 수행하는 핵심 에이전트를 생성합니다."""
    return LlmAgent(
        model=model,
        name="agentic_game_controller",
        description="Controls the live 3D game only through player-equivalent input buffers.",
        instruction=CONTROLLER_INSTRUCTION,
        tools=[build_mcp_toolset(), exit_loop],
    )
