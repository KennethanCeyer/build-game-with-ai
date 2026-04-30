from __future__ import annotations

from agentic_game_engine.game.contracts import Gait, ScenarioStatus
from agentic_game_engine.game.simulation import (
    MAZE_CELL_SIZE,
    SIMON_PADS,
    WORLD_X_LIMIT,
    WORLD_Z_LIMIT,
    create_default_simulator,
)


def test_context_action_without_target_is_reported_in_korean() -> None:
    simulator = create_default_simulator()
    simulator.drive_actor("rhea", 11.8, -1.8, 0.0, Gait.WALK)

    result = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

    assert result.ok is True
    assert "가까운 대상이 없습니다" in result.state["events"][-1]["message"]


def test_unknown_zone_fails_without_exception() -> None:
    simulator = create_default_simulator()

    result = simulator.move_actor("rhea", "missing_zone")

    assert result.ok is False
    assert result.degraded is True
    assert result.state["status"] == ScenarioStatus.FAILED.value


def test_drive_actor_clamps_position_to_visible_world_bounds() -> None:
    simulator = create_default_simulator()

    result = simulator.drive_actor("rhea", 99.0, -99.0, 45.0, Gait.RUN)

    assert result.ok is True
    actor = result.state["actors"][0]
    assert actor["position"] == {"x": WORLD_X_LIMIT, "y": 0.0, "z": -WORLD_Z_LIMIT}
    assert actor["behavior"] == "running"


def test_drive_actor_reports_collision_without_entering_obstacle() -> None:
    simulator = create_default_simulator()

    result = simulator.drive_actor("rhea", -1.1, 6.75, 0.0, Gait.WALK)

    assert result.ok is True
    assert result.degraded is True
    assert "충돌로 막혔습니다" in result.message


def test_drive_actor_can_sync_idle_state_after_key_release() -> None:
    simulator = create_default_simulator()

    moving = simulator.drive_actor("rhea", 2.7, 0.1, 90.0, Gait.RUN, moving=True)
    stopped = simulator.drive_actor("rhea", 2.7, 0.1, 90.0, Gait.WALK, moving=False)

    assert moving.state["actors"][0]["behavior"] == "running"
    assert stopped.state["actors"][0]["behavior"] == "idle"
    assert stopped.state["actors"][0]["gait"] == "walk"


def test_generated_maze_is_player_scale_and_collision_backed() -> None:
    simulator = create_default_simulator()
    state = simulator.inspect()
    maze_walls = [
        obstacle for obstacle in state["obstacles"] if obstacle["id"].startswith("maze_wall_")
    ]

    assert len(maze_walls) >= 20
    assert len(maze_walls) >= 40
    assert MAZE_CELL_SIZE >= 1.8
    assert state["actors"][0]["position"]["x"] > -2.0
    assert next(zone for zone in state["zones"] if zone["id"] == "maze_start")["center"]["x"] < -3.0
    assert next(zone for zone in state["zones"] if zone["id"] == "maze_exit")["center"]["x"] < -15.0
    assert state["actors"][0]["last_zone_id"] is None


def test_maze_exit_requires_entering_start_marker_first() -> None:
    simulator = create_default_simulator()
    zones = {zone["id"]: zone for zone in simulator.inspect()["zones"]}
    exit_zone = zones["maze_exit"]

    simulator.drive_actor(
        "rhea",
        exit_zone["center"]["x"],
        exit_zone["center"]["z"],
        90.0,
        Gait.WALK,
    )
    early_exit = simulator.apply_input_buffer(
        "rhea", [{"keys": ["KeyD"], "duration_ms": 80}], camera_yaw_degrees=0.0
    )

    assert early_exit.state["flags"]["maze_escaped"] is False
    assert "시작 지점부터" in early_exit.state["events"][-1]["message"]

    start_zone = zones["maze_start"]
    simulator.drive_actor(
        "rhea",
        start_zone["center"]["x"],
        start_zone["center"]["z"],
        90.0,
        Gait.WALK,
    )
    simulator.apply_input_buffer(
        "rhea", [{"keys": ["KeyD"], "duration_ms": 80}], camera_yaw_degrees=0.0
    )
    simulator.drive_actor(
        "rhea",
        exit_zone["center"]["x"],
        exit_zone["center"]["z"],
        90.0,
        Gait.WALK,
    )
    completed = simulator.apply_input_buffer(
        "rhea", [{"keys": ["KeyD"], "duration_ms": 80}], camera_yaw_degrees=0.0
    )

    assert completed.state["flags"]["maze_escaped"] is True


def test_memory_puzzle_requires_play_then_correct_sequence() -> None:
    simulator = create_default_simulator()

    simulator.drive_actor("rhea", 7.25, 1.95, 0.0, Gait.WALK)
    start = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert start.state["flags"]["puzzle_ready"] is True

    zones = {zone["id"]: zone for zone in simulator.inspect()["zones"]}
    for phase_length in range(1, len(simulator.puzzle_sequence) + 1):
        for pad_id in simulator.puzzle_sequence[:phase_length]:
            zone = zones[pad_id]
            simulator.drive_actor(
                "rhea",
                zone["center"]["x"],
                zone["center"]["z"],
                0.0,
                Gait.WALK,
            )
            simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

    for phase in range(1, len(SIMON_PADS) + 1):
        assert simulator.inspect()["flags"][f"puzzle_phase_{phase}"] is True
    assert simulator.inspect()["flags"]["puzzle_solved"] is True


def test_memory_puzzle_wrong_pad_resets_progress() -> None:
    simulator = create_default_simulator()
    zones = {zone["id"]: zone for zone in simulator.inspect()["zones"]}

    simulator.drive_actor("rhea", 7.25, 1.95, 0.0, Gait.WALK)
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    wrong_pad = next(pad for pad in SIMON_PADS if pad != simulator.puzzle_sequence[0])
    zone = zones[wrong_pad]
    simulator.drive_actor("rhea", zone["center"]["x"], zone["center"]["z"], 0.0, Gait.WALK)

    result = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

    assert result.state["flags"]["puzzle_ready"] is False
    assert result.state["flags"]["puzzle_solved"] is False
    assert "기억 퍼즐이 초기화" in result.state["events"][-1]["message"]


def test_npc_quest_uses_only_context_interactions_for_progress() -> None:
    simulator = create_default_simulator()

    simulator.drive_actor("rhea", 3.55, -2.25, 90.0, Gait.WALK)
    start = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert start.state["flags"]["quest_started"] is True
    assert "미라:" in start.state["events"][-1]["message"]

    simulator.drive_actor("rhea", -0.8, -1.0, 90.0, Gait.WALK)
    ask_trade = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert ask_trade.state["flags"]["orange_received"] is False
    assert "사과와 바꾸고 싶어" in ask_trade.state["events"][-1]["message"]

    simulator.drive_actor("rhea", 13.35, 6.45, 90.0, Gait.WALK)
    apple = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert apple.state["flags"]["apple_collected"] is True
    assert apple.state["flags"]["apple_harvested"] is True
    assert "사과" in apple.state["inventory"]
    assert apple.state["events"][-1]["data"]["item"] == "apple"

    simulator.drive_actor("rhea", -0.8, -1.0, 90.0, Gait.WALK)
    orange = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert orange.state["flags"]["apple_collected"] is False
    assert orange.state["flags"]["orange_received"] is True
    assert "사과" not in orange.state["inventory"]
    assert "오렌지" in orange.state["inventory"]

    simulator.drive_actor("rhea", 3.55, -2.25, 90.0, Gait.WALK)
    complete = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert complete.state["flags"]["quest_complete"] is True
    assert complete.state["flags"]["orange_received"] is False
    assert "오렌지" not in complete.state["inventory"]
    assert "오렌지를 가져왔구나" in complete.state["events"][-1]["message"]


def test_npc_quest_does_not_trade_orange_before_dialogue_and_apple() -> None:
    simulator = create_default_simulator()

    simulator.drive_actor("rhea", -0.8, -1.0, 90.0, Gait.WALK)
    no_task = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert no_task.state["flags"]["orange_received"] is False
    assert "미라에게 먼저 말을 걸어봐" in no_task.state["events"][-1]["message"]

    simulator.drive_actor("rhea", 3.55, -2.25, 90.0, Gait.WALK)
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    simulator.drive_actor("rhea", -0.8, -1.0, 90.0, Gait.WALK)
    no_apple = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert no_apple.state["flags"]["orange_received"] is False
    assert "신선한 사과와 바꾸고 싶어" in no_apple.state["events"][-1]["message"]
