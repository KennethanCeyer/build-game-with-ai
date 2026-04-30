from __future__ import annotations

import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from indie_game_agent.logging_utils import get_logger


SERVER_MODULE = "indie_game_agent.mcp_server"
EXPECTED_TOOLS = {
    "plan_vertical_slice",
    "design_enemy_roster",
    "triage_playtest_notes",
    "draft_feature_backlog",
    "build_launch_checklist",
    "inspect_running_game",
    "load_room_preset",
    "suggest_safe_route",
    "preview_plan_in_game",
    "solve_turn_in_game",
    "apply_moves_in_game",
    "export_board_snapshot",
    "capture_and_analyze_board",
    "reset_game_room",
    "show_note_in_game",
}
EXPECTED_RESOURCES = {
    "design://topdown-roguelike-pillars",
    "production://indie-scope-heuristics",
    "runtime://udp-command-cheatsheet",
}
logger = get_logger("check_mcp")


async def _main() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", SERVER_MODULE],
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            tool_names = {tool.name for tool in tools.tools}
            resource_names = {str(resource.uri) for resource in resources.resources}
            missing_tools = EXPECTED_TOOLS - tool_names
            missing_resources = EXPECTED_RESOURCES - resource_names

            if missing_tools or missing_resources:
                raise RuntimeError(
                    f"Missing MCP entries: tools={sorted(missing_tools)}, resources={sorted(missing_resources)}"
                )

            logger.info("MCP check passed")
            logger.info("Tools: %s", ", ".join(sorted(tool_names)))
            logger.info("Resources: %s", ", ".join(sorted(resource_names)))


if __name__ == "__main__":
    anyio.run(_main)
