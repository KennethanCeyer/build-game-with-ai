from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from indie_game_agent.logging_utils import get_logger
from indie_game_agent.runtime_bridge import UDP_CHEATSHEET, request_runtime
from indie_game_agent.studio_domain import (
    build_launch_checklist_payload,
    design_enemy_roster_payload,
    draft_feature_backlog_payload,
    indie_scope_heuristics,
    plan_vertical_slice_payload,
    suggest_safe_route_payload,
    topdown_roguelike_pillars,
    triage_playtest_notes_payload,
)
from indie_game_agent.vision import analyze_snapshot


logger = get_logger("indie_game_agent.mcp_server")

mcp = FastMCP(
    "Indie Game Agent MCP",
    instructions="Tools for top-down roguelike planning, playtest triage, room inspection, safe-route hints, and runtime board control.",
    json_response=True,
)


@mcp.tool()
def plan_vertical_slice(
    game_name: str,
    fantasy: str,
    core_loop: str,
    scope_weeks: int = 8,
    team_size: int = 2,
) -> dict:
    return plan_vertical_slice_payload(game_name, fantasy, core_loop, scope_weeks, team_size)


@mcp.tool()
def design_enemy_roster(
    theme: str,
    combat_focus: Literal["melee", "ranged", "mix"] = "mix",
    roster_size: int = 3,
) -> dict:
    return design_enemy_roster_payload(theme, combat_focus, roster_size)


@mcp.tool()
def triage_playtest_notes(
    notes: list[str],
    release_days: int = 30,
) -> dict:
    return triage_playtest_notes_payload(notes, release_days)


@mcp.tool()
def draft_feature_backlog(
    feature_name: str,
    design_goal: str,
    sprint_days: int = 10,
) -> dict:
    return draft_feature_backlog_payload(feature_name, design_goal, sprint_days)


@mcp.tool()
def build_launch_checklist(
    platforms: list[str],
    demo_available: bool = True,
    localization_count: int = 1,
) -> dict:
    return build_launch_checklist_payload(platforms, demo_available, localization_count)


@mcp.tool()
def inspect_running_game() -> dict:
    return request_runtime("get_state")


@mcp.tool()
def load_room_preset(
    room_id: Literal["vault_intro", "crossfire_gallery", "switchback_archive"] = "vault_intro",
) -> dict:
    return request_runtime("load_room", {"room_id": room_id})


@mcp.tool()
def suggest_safe_route(step_limit: int = 4) -> dict:
    runtime_state = request_runtime("get_state")["state"]
    return suggest_safe_route_payload(runtime_state, step_limit)


@mcp.tool()
def preview_plan_in_game(step_limit: int = 4) -> dict:
    plan = suggest_safe_route(step_limit)
    if not plan["recommended_moves"]:
        return {"plan": plan, "runtime": request_runtime("get_state")}

    runtime = request_runtime(
        "preview_plan",
        {
            "moves": plan["recommended_moves"],
            "label": f"Suggested {len(plan['recommended_moves'])}-step route",
        },
    )
    return {"plan": plan, "runtime": runtime}


@mcp.tool()
def solve_turn_in_game(step_limit: int = 4) -> dict:
    plan = suggest_safe_route(step_limit)
    if not plan["recommended_moves"]:
        return {"plan": plan, "runtime": request_runtime("get_state")}

    runtime = request_runtime("apply_moves", {"moves": plan["recommended_moves"]})
    return {"plan": plan, "runtime": runtime}


@mcp.tool()
def apply_moves_in_game(moves: list[str]) -> dict:
    return request_runtime("apply_moves", {"moves": moves})


@mcp.tool()
def export_board_snapshot(filename: str = "board_snapshot.png") -> dict:
    return request_runtime("save_snapshot", {"filename": filename})


@mcp.tool()
def capture_and_analyze_board(
    filename: str = "board_snapshot.png",
    prompt: str | None = None,
) -> dict:
    snapshot = request_runtime("save_snapshot", {"filename": filename})
    visual_analysis = analyze_snapshot(snapshot["path"], prompt=prompt)
    return {
        "snapshot": snapshot,
        "visual_analysis": visual_analysis,
    }


@mcp.tool()
def reset_game_room() -> dict:
    return request_runtime("reset_room")


@mcp.tool()
def show_note_in_game(message: str) -> dict:
    return request_runtime("show_note", {"message": message})


@mcp.resource("design://topdown-roguelike-pillars")
def design_topdown_roguelike_pillars() -> str:
    return topdown_roguelike_pillars()


@mcp.resource("production://indie-scope-heuristics")
def production_indie_scope_heuristics() -> str:
    return indie_scope_heuristics()


@mcp.resource("runtime://udp-command-cheatsheet")
def runtime_udp_command_cheatsheet() -> str:
    return UDP_CHEATSHEET


if __name__ == "__main__":
    logger.info("Starting MCP server")
    mcp.run(transport="stdio")
