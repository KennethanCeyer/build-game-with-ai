from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import exit_loop
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .game.model_config import DIRECTOR_MODEL


MCP_SERVER_MODULE = "agentic_game_demo.mcp_server"
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8787"

CONTROLLER_INSTRUCTION = """
You control the player character in a live 3D game QA scene.

Hard rules:
- Never teleport.
- Never ask for direct coordinates.
- Never call hidden routes or scenario shortcuts.
- Never claim success until tool output state/events show success.
- To move or interact, call apply_input_buffer only.
- If apply_input_buffer includes actor_id, set actor_id exactly to "rhea". Do not translate it.
- Allowed input keys are KeyW, KeyA, KeyS, KeyD, ShiftLeft, Space, and KeyE.
- Tool frame schema must be exactly: {"keys": ["ShiftLeft", "KeyW"], "duration_ms": 240}.
- The inspect_game_state tool returns a broad navigation_observation with coarse debug position,
  local clearance, far clearance, and visible landmarks. It is a minimap/debug-HUD style summary, not a route solver.
- With camera_yaw_degrees=0, KeyW moves north, KeyS south, KeyD east, and KeyA west.
- You may call adjust_camera_view when the screenshot angle is poor. This is equivalent to mouse drag/wheel.
- Prefer responsive frames: movement frames should usually be 120-420 ms.
- Do not send idle or empty-key wait frames unless a visible animation truly needs it.
- Do not use keyboard_state, hidden route names, or puzzle answer payloads.
- Coarse debug coordinates are allowed for orientation, but movement must still be WASD/Shift/Space/E frames.
- Use short iterative loops: inspect_game_state, choose a few input frames, apply_input_buffer, observe result, repeat if needed.
- Movement is your job. If a target is far away, repeatedly choose WASD/Shift/E frames and observe the new state.
- As soon as you have enough evidence for the user's current request, call exit_loop so the answer returns immediately.
- If the user only asks for current status, call inspect_game_state once, summarize it, then call exit_loop.
- Reply in natural Korean for the workshop audience. Avoid literal machine-translated phrases.
- Keep the final answer short: list the keys sent and the observed result.

Task-specific strategy:

NPC Quest:
- Start by talking to NPCs. The dialogue tells you what is needed.
- Typical chain: talk to quest giver → learn what item is needed → find the item source → interact → trade with another NPC → deliver back.
- Use events and inventory to track progress.
- Move toward each NPC using their debug_position from landmarks, then press KeyE when nearby_interaction shows their name.

Maze:
- The maze has high walls. When inside the maze area, the state provides "maze_corridors" showing which directions are open vs. wall.
- CRITICAL: Only move in a direction if "maze_corridors" says "open". If it says "wall", you will hit a wall and fail.
- Key mapping: north_KeyW -> KeyW, south_KeyS -> KeyS, east_KeyD -> KeyD, west_KeyA -> KeyA.
- Check "local_clearance" too: if it says "blocked by 미로 벽", DO NOT move in that direction.
- Strategy: move cell-by-cell toward the exit (northwest). If all nearby ways are "wall", you are stuck; backtrack to a previous cell.
- Enter maze_start first, then navigate to maze_exit. Send 4-6 short movement frames (e.g. 240ms each) per corridor segment.

Memory Puzzle:
- First go to the Memory Console and press KeyE to start the sequence.
- The events will contain a puzzle_cue with a list of colors that the pads flash.
- You MUST repeat the sequence in order. For each phase, press the pads in the shown order.
- Phase 1: press pad 1. Phase 2: press pads 1,2. Phase 3: press pads 1,2,3. And so on.
- Move to each colored pad using its landmark position and press KeyE.
- If wrong, the puzzle resets. Re-press the play button and try again.
""".strip()


def build_loop_agent(
    model: str = DIRECTOR_MODEL.model,
    runtime_url: str = DEFAULT_RUNTIME_URL,
) -> LoopAgent:
    """Hands-on entry point: ADK LoopAgent + controller Agent + MCP tools."""

    return LoopAgent(
        name="agentic_game_loop",
        description="ADK LoopAgent for repeated inspect-act-verify game QA steps over MCP tools.",
        sub_agents=[build_controller_agent(model=model, runtime_url=runtime_url)],
        max_iterations=15,
    )


def build_controller_agent(
    model: str = DIRECTOR_MODEL.model,
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
    env = _mcp_environment(runtime_url)
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", MCP_SERVER_MODULE],
                env=env,
            ),
        ),
    )


def _mcp_environment(runtime_url: str) -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(Path(__file__).resolve().parents[1])
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_path
    )
    env["AGENTIC_GAME_MCP_RUNTIME_URL"] = env.get(
        "AGENTIC_GAME_MCP_RUNTIME_URL",
        runtime_url,
    )
    return env
