from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

MCP_SERVER_MODULE = "game_agent.mcp_server"
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
    """MCP 서버 프로세스가 엔진(src)과 에이전트(handson/solution) 모듈을 모두 찾을 수 있도록 환경 변수를 구성합니다."""
    env = dict(os.environ)

    # 1. 엔진 코드가 위치한 src 경로 추가
    root = Path(__file__).resolve().parents[2]
    src_path = str(root / "src")

    # 2. 현재 정답 코드가 위치한 경로 (solution) 추가
    # tools.py가 solution/game_agent/tools.py에 있으므로 parents[1]이 solution입니다.
    lab_path = str(Path(__file__).resolve().parents[1])

    existing_pythonpath = env.get("PYTHONPATH")
    new_paths = [src_path, lab_path]
    if existing_pythonpath:
        new_paths.append(existing_pythonpath)

    env["PYTHONPATH"] = os.pathsep.join(new_paths)
    env["AGENTIC_GAME_MCP_RUNTIME_URL"] = runtime_url
    return env
