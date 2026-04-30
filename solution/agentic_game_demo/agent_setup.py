from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters


MCP_SERVER_MODULE = "agentic_game_demo.mcp_server"
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8787"
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
- Allowed input keys are KeyW, KeyA, KeyS, KeyD, ShiftLeft, Space, and KeyE.
- With camera_yaw_degrees=0, KeyW moves north, KeyS south, KeyD east, and KeyA west.
- Use short observe -> act -> observe loops.
- When the request is answered or you have enough evidence, call exit_loop.

Keep the final answer short: list the keys sent and the observed result.
""".strip()


def build_loop_agent(
    model: str = DEFAULT_MODEL,
    runtime_url: str = DEFAULT_RUNTIME_URL,
) -> LoopAgent:
    return LoopAgent(
        name="agentic_game_loop",
        description="ADK LoopAgent for repeated inspect-act-verify game QA steps over MCP tools.",
        sub_agents=[build_controller_agent(model=model, runtime_url=runtime_url)],
        max_iterations=15,
    )


def build_controller_agent(
    model: str = DEFAULT_MODEL,
    runtime_url: str = DEFAULT_RUNTIME_URL,
) -> LlmAgent:
    return LlmAgent(
        model=model,
        name="agentic_game_controller",
        description="Controls the live 3D game only through player-equivalent input buffers.",
        instruction=CONTROLLER_INSTRUCTION,
        tools=[build_mcp_toolset(runtime_url), exit_loop],
    )


def build_mcp_toolset(runtime_url: str = DEFAULT_RUNTIME_URL) -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", MCP_SERVER_MODULE],
                env=_mcp_environment(runtime_url),
            ),
        ),
    )


def _mcp_environment(runtime_url: str) -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(Path(__file__).resolve().parents[2] / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_path
    )
    env["AGENTIC_GAME_MCP_RUNTIME_URL"] = runtime_url
    return env
