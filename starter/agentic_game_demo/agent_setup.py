from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters


# TODO(starter-1): point to the completed MCP server module.
MCP_SERVER_MODULE = ...
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8787"

# TODO(starter-2): use the default fast model for the workshop controller.
DEFAULT_MODEL = ...

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
    # TODO(starter-3): return a LoopAgent named "agentic_game_loop".
    # It should contain one controller sub-agent and run for up to 4 iterations.
    ...


def build_controller_agent(
    model: str = DEFAULT_MODEL,
    runtime_url: str = DEFAULT_RUNTIME_URL,
) -> LlmAgent:
    # TODO(starter-4): return an LlmAgent named "agentic_game_controller".
    # Attach the MCP toolset and exit_loop.
    ...


def build_mcp_toolset(runtime_url: str = DEFAULT_RUNTIME_URL) -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                # TODO(starter-5): run the MCP server as a Python module.
                args=["-m", ...],
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
