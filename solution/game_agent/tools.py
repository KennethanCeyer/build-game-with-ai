from __future__ import annotations

import os
import sys
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams, StdioServerParameters

MCP_SERVER_MODULE = "game_agent.mcp_server"
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8787"


def _mcp_environment(runtime_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENTIC_GAME_MCP_RUNTIME_URL"] = runtime_url

    src_path = os.path.abspath(os.path.join(os.getcwd(), "src"))
    solution_path = os.path.abspath(os.path.join(os.getcwd(), "solution"))
    env["PYTHONPATH"] = os.path.pathsep.join(
        filter(None, [env.get("PYTHONPATH", ""), src_path, solution_path])
    )

    return env


def build_mcp_toolset(
    tool_filter: list[str] | None = None,
    runtime_url: str = DEFAULT_RUNTIME_URL,
) -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", MCP_SERVER_MODULE],
                env=_mcp_environment(runtime_url),
            ),
        ),
        tool_filter=tool_filter,
    )


def build_agent_toolset(tool_names: list[str]) -> McpToolset:
    return build_mcp_toolset(tool_names)
