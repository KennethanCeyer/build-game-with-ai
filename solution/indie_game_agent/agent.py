from __future__ import annotations

import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .logging_utils import get_logger
from .settings import apply_environment, load_settings


MCP_SERVER_MODULE = "indie_game_agent.mcp_server"
SETTINGS = load_settings()
logger = get_logger("indie_game_agent.agent")


apply_environment(SETTINGS)


root_agent = LlmAgent(
    model="gemini-3-flash-preview",
    name="indie_game_agent",
    description="An indie game studio copilot backed by local MCP tools and a turn-based room sandbox.",
    instruction="""
You are a pragmatic copilot for indie teams building small top-down roguelike and puzzle rooms.

Use the MCP tools whenever the user asks for:
- vertical slice planning
- enemy roster design
- playtest note triage
- feature backlog drafting
- launch checklist drafting
- inspecting the running room
- loading another room preset
- suggesting a safe route
- previewing a route on the board
- applying a suggested move sequence
- exporting a board snapshot
- visually analyzing the current board from a snapshot
- resetting or annotating the running room

Prefer concise, structured answers.
State assumptions explicitly if scope, numbers, or release timing are missing.
Do not invent structured outputs when an MCP tool can answer directly.
Summarize tool output into short sections instead of pasting raw JSON unless the user asks for JSON.
Inspect the room before suggesting moves whenever the current board state matters.
If the user asks for visual confirmation, use the snapshot analysis tool and cross-check it against MCP room state when useful.
""".strip(),
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=["-m", MCP_SERVER_MODULE],
                ),
            ),
        )
    ],
)

logger.info("Agent module loaded with MCP server module %s", MCP_SERVER_MODULE)
