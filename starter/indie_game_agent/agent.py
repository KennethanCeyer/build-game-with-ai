from __future__ import annotations

import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .logging_utils import get_logger
from .settings import apply_environment, load_settings


logger = get_logger("indie_game_agent.agent")
# TODO(starter-2): point to the local MCP server module.
# Hint: use a Python module path, not a file path.
MCP_SERVER_MODULE = "TODO_MODULE_NAME"
SETTINGS = load_settings()


# TODO(starter-2): apply the loaded GOOGLE_API_KEY before the agent starts.
# Hint: call the helper that copies values into the current process environment.
# apply_environment(SETTINGS)


root_agent = LlmAgent(
    # TODO(starter-2): use the validated model name from the solution README.
    model="TODO_MODEL",
    # TODO(starter-2): use the app name that ADK should expose in `adk run`, `adk web`, and `list-apps`.
    name="TODO_AGENT_NAME",
    description="TODO_DESCRIPTION",
    instruction="""
TODO(starter-2): describe when the agent should use MCP tools for planning,
enemy roster design, playtest triage, backlog or launch planning,
room inspection, safe-route suggestions, board previews, move application,
snapshot export, visual board analysis, and how it should summarize results.
""".strip(),
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    # TODO(starter-2): run the local MCP server as a Python module.
                    # Hint: keep "-m" and replace only the module name.
                    args=["-m", MCP_SERVER_MODULE],
                ),
            ),
        )
    ],
)

logger.info("Agent module loaded")
