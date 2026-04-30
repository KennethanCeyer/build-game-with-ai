from __future__ import annotations

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools import McpToolset, exit_loop

# 런타임 게임 엔진은 MCP(Model Context Protocol) 서버를 통해 에이전트와 통신합니다.
# 에이전트는 이 도구를 사용하여 게임 캐릭터를 조작하고 상태를 관찰합니다.
MCP_RUNTIME_URL = "http://127.0.0.1:8787/api/mcp"

CONTROLLER_INSTRUCTION = """당신은 3인칭 액션 게임을 테스트하는 전문 에이전트입니다.
화면 스크린샷과 게임 상태(JSON)를 분석하여 주어지는 목표를 달성하세요.

[조작 지침]
- 캐릭터 이동은 apply_input_buffer 도구의 WASD 키 입력만을 사용하며, 순간이동(move_actor)은 절대 사용하지 마세요.
- 장애물에 막히면 다른 방향으로 우회하거나 점프(Space)를 활용하세요.
- 상호작용이 필요한 경우(대화, 아이템 획득 등) 해당 위치로 이동 후 E 키를 입력하세요.
- 목표가 완료되면(예: maze_escaped=True) 즉시 exit_loop 도구를 호출하여 종료하세요.

[전술 지침]
- 미로: 막힌 길을 기억하며 출구(maze_exit) 방향으로 단계별로 이동하세요.
- 퍼즐: 콘솔이 보여주는 빛 패턴의 색상 순서를 기억하고 해당 패드를 순서대로 밟으세요.
- 퀘스트: NPC의 대화 내용을 분석하여 필요한 아이템을 찾고 전달하세요."""


def build_controller_agent(model: str) -> LlmAgent:
    """게임 월드와 상호작용하고 추론을 수행하는 핵심 에이전트를 생성합니다."""
    return LlmAgent(
        name="agentic_game_controller",
        model=model,
        instruction=CONTROLLER_INSTRUCTION,
        tools=[build_mcp_toolset(), exit_loop],
    )


def build_mcp_toolset() -> McpToolset:
    """게임 엔진 런타임과 연결된 MCP 도구 모음을 생성합니다."""
    return McpToolset(MCP_RUNTIME_URL)


def build_loop_agent(model: str = "gemini-3-flash-preview") -> LoopAgent:
    """
    최상위 Loop 에이전트를 조립합니다.
    이 에이전트는 하위 에이전트(Controller)가 목표를 달성할 때까지 반복해서 실행합니다.
    """
    return LoopAgent(
        name="agentic_game_loop",
        sub_agents=[build_controller_agent(model)],
        max_loops=15,  # 복잡한 작업을 수행하기 위해 반복 횟수를 충분히 설정합니다.
    )
