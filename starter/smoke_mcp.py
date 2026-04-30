from __future__ import annotations

import json
import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from indie_game_agent.logging_utils import get_logger
from indie_game_agent.runtime_bridge import runtime_available


SERVER_MODULE = "indie_game_agent.mcp_server"
logger = get_logger("smoke_mcp")


async def _main() -> None:
    if not runtime_available():
        raise RuntimeError("The local runtime is not responding on udp://127.0.0.1:8765. Start run_game.py first.")

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", SERVER_MODULE],
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            resources = await session.list_resources()
            slice_result = await session.call_tool(
                "plan_vertical_slice",
                {
                    "game_name": "Nightshift Echo",
                    "fantasy": "forbidden archive under a dead city",
                    "core_loop": "enter one room, read watcher lanes, take the safest line, claim the relic, escape",
                    "scope_weeks": 8,
                    "team_size": 2,
                },
            )
            roster_result = await session.call_tool(
                "design_enemy_roster",
                {
                    "theme": "catacomb order",
                    "combat_focus": "mix",
                    "roster_size": 4,
                },
            )
            triage_result = await session.call_tool(
                "triage_playtest_notes",
                {
                    "notes": [
                        "Players said the second room spike feels unfair and the support enemy is hard to read.",
                        "The pause menu sometimes freezes after a retry.",
                        "The HUD objective text is too small during combat.",
                    ],
                    "release_days": 21,
                },
            )
            backlog_result = await session.call_tool(
                "draft_feature_backlog",
                {
                    "feature_name": "relic swap",
                    "design_goal": "Let the player trade position for safer routing in a static room.",
                    "sprint_days": 10,
                },
            )
            launch_result = await session.call_tool(
                "build_launch_checklist",
                {
                    "platforms": ["PC", "Steam Deck"],
                    "demo_available": True,
                    "localization_count": 3,
                },
            )
            room_result = await session.call_tool(
                "load_room_preset",
                {
                    "room_id": "crossfire_gallery",
                },
            )
            route_result = await session.call_tool("suggest_safe_route", {"step_limit": 4})
            preview_result = await session.call_tool("preview_plan_in_game", {"step_limit": 4})
            solve_result = await session.call_tool("solve_turn_in_game", {"step_limit": 4})
            snapshot_result = await session.call_tool("export_board_snapshot", {"filename": "smoke_room.png"})
            runtime_state = await session.call_tool("inspect_running_game", {})

            logger.info("Tools: %s", ", ".join(tool.name for tool in tools.tools))
            logger.info("Resources: %s", ", ".join(str(resource.uri) for resource in resources.resources))
            logger.info("Vertical slice sample:\n%s", json.dumps(slice_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Enemy roster sample:\n%s", json.dumps(roster_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Playtest triage sample:\n%s", json.dumps(triage_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Backlog sample:\n%s", json.dumps(backlog_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Launch checklist sample:\n%s", json.dumps(launch_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Room load sample:\n%s", json.dumps(room_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Route suggestion sample:\n%s", json.dumps(route_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Plan preview sample:\n%s", json.dumps(preview_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Applied turn sample:\n%s", json.dumps(solve_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Snapshot sample:\n%s", json.dumps(snapshot_result.model_dump(mode="json"), indent=2, ensure_ascii=True))
            logger.info("Runtime state sample:\n%s", json.dumps(runtime_state.model_dump(mode="json"), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    anyio.run(_main)
