from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

MCP_SERVER_MODULE = "agentic_game_engine.mcp_server"
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8787"


def build_mcp_toolset(runtime_url: str = DEFAULT_RUNTIME_URL) -> McpToolset:
    """게임 엔진 런타임(MCP 서버)과 연결된 도구 모음을 생성합니다."""
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
