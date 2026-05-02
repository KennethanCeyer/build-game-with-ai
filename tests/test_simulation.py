from __future__ import annotations

from engine.game.contracts import ScenarioStatus, Vec3
from engine.game.simulation import (
    MAZE_CELL_SIZE,
    SIMON_PADS,
    WORLD_X_LIMIT,
    create_default_simulator,
)


def get_actor(state_dict: dict, actor_id: str) -> dict:
    for actor in state_dict["actors"]:
        if actor["id"] == actor_id:
            return actor
    raise KeyError(actor_id)


def test_context_action_without_target_is_reported_in_korean() -> None:
    simulator = create_default_simulator()
    # 멀리 이동 (duration을 크게 주어 WORLD_X_LIMIT 근처로 보냄)
    simulator.drive_actor("rhea", ["KeyW", "KeyD"], 45.0, 10000.0)

    result = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

    assert result.ok is True
    # events는 as_dict에서 역순 정렬되므로 index 0이 최신
    assert "가까운 대상이 없습니다" in result.state["events"][0]["message"]


def test_unknown_zone_fails_without_exception() -> None:
    simulator = create_default_simulator()

    result = simulator.move_actor("rhea", "missing_zone")

    assert result.ok is False
    assert result.degraded is True
    assert result.state["status"] == ScenarioStatus.FAILED.value


def test_drive_actor_clamps_position_to_visible_world_bounds() -> None:
    simulator = create_default_simulator()

    # 동쪽 경계(+X)로 이동하기 위해 시작 위치를 동쪽으로 옮김
    simulator.state.actors["rhea"].position = Vec3(10.0, 0.0, 0.0)

    # Yaw 0에서 D는 동쪽(+X) 이동.
    # 충분히 멀리 이동하도록 호출 (7.5 speed * 5 sec = 37.5 unit 이동 가능)
    for _ in range(5):
        result = simulator.drive_actor("rhea", ["KeyD"], 0.0, 1000.0)

    assert result.ok is True
    actor = get_actor(result.state, "rhea")
    # 동쪽 경계(WORLD_X_LIMIT=17.2) 확인
    assert abs(actor["position"]["x"] - WORLD_X_LIMIT) < 0.1


def test_drive_actor_reports_collision_without_entering_obstacle() -> None:
    simulator = create_default_simulator()
    # 벤치 쪽으로 이동 시도
    result = simulator.drive_actor("rhea", ["KeyS", "KeyA"], 0.0, 5000.0)
    assert result.ok is True


def test_drive_actor_can_sync_idle_state_after_key_release() -> None:
    simulator = create_default_simulator()

    moving = simulator.drive_actor("rhea", ["KeyW"], 90.0, 100.0)
    assert get_actor(moving.state, "rhea")["behavior"] == "walking"

    stopped = simulator.drive_actor("rhea", [], 90.0, 100.0)
    assert get_actor(stopped.state, "rhea")["behavior"] == "idle"


def test_generated_maze_is_player_scale_and_collision_backed() -> None:
    simulator = create_default_simulator()
    state = simulator.inspect()
    maze_walls = [
        obstacle for obstacle in state["obstacles"] if obstacle["id"].startswith("maze_wall_")
    ]

    assert len(maze_walls) >= 20
    assert len(maze_walls) >= 40
    assert MAZE_CELL_SIZE >= 1.8
    assert get_actor(state, "rhea")["position"]["x"] > -2.0


def test_maze_exit_requires_entering_start_marker_first() -> None:
    simulator = create_default_simulator()
    exit_zone = simulator.state.zones["maze_exit"]
    simulator.state.actors["rhea"].position = exit_zone.center

    early_exit = simulator.apply_input_buffer(
        "rhea", [{"keys": ["KeyD"], "duration_ms": 80}], camera_yaw_degrees=0.0
    )

    assert early_exit.state["flags"]["maze_escaped"] is False
    assert "시작 지점부터" in early_exit.state["events"][0]["message"]


def test_memory_puzzle_requires_play_then_correct_sequence() -> None:
    simulator = create_default_simulator()
    simulator.state.actors["rhea"].position = simulator.state.zones["puzzle_play"].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

    assert simulator.state.flags["puzzle_ready"] is True
    sequence = simulator.puzzle_sequence  # 길이 5

    # 각 phase마다 처음부터 해당 phase까지의 모든 패드를 순서대로 눌러야 함
    for phase in range(1, len(sequence) + 1):
        target_sub_sequence = sequence[:phase]
        for pad_id in target_sub_sequence:
            simulator.state.actors["rhea"].position = simulator.state.zones[pad_id].center
            simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

        if phase < len(sequence):
            assert simulator.state.flags[f"puzzle_phase_{phase}"] is True
            assert simulator.puzzle_phase == phase + 1

    assert simulator.state.flags["puzzle_solved"] is True


def test_memory_puzzle_wrong_pad_resets_progress() -> None:
    simulator = create_default_simulator()
    simulator.state.actors["rhea"].position = simulator.state.zones["puzzle_play"].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

    sequence = simulator.puzzle_sequence
    correct_pad = sequence[0]
    wrong_pad = SIMON_PADS[0] if SIMON_PADS[0] != correct_pad else SIMON_PADS[1]

    simulator.state.actors["rhea"].position = simulator.state.zones[wrong_pad].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])

    assert simulator.state.flags["puzzle_ready"] is False
    assert simulator.puzzle_phase == 0


def test_npc_quest_uses_only_context_interactions_for_progress() -> None:
    simulator = create_default_simulator()

    simulator.state.actors["rhea"].position = simulator.state.zones["npc1"].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert simulator.state.flags["quest_started"] is True

    simulator.state.actors["rhea"].position = simulator.state.zones["apple_tree"].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert "사과" in simulator.state.inventory

    simulator.state.actors["rhea"].position = simulator.state.zones["npc2"].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert "오렌지" in simulator.state.inventory
    assert "사과" not in simulator.state.inventory

    simulator.state.actors["rhea"].position = simulator.state.zones["npc1"].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    assert simulator.state.flags["quest_complete"] is True
