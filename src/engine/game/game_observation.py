from __future__ import annotations

from collections.abc import Iterable
from math import atan2, degrees
from typing import Any

_MAZE_BOUNDS_X = (-17.5, -3.5)
_MAZE_BOUNDS_Z = (-9.2, 1.0)


def agent_visible_state(state: dict[str, Any]) -> dict[str, Any]:
    """런타임 전체 상태를 ADK 도구 노출용 간결 상태로 변환.

    정확한 좌표, 퍼즐 정답, 퀘스트 내부 플래그 등 불필요 정보 제외.
    플레이테스트 유효 요약 정보 제공.
    """

    player = _player_actor(state)
    nearby = _nearby_interaction(state, player)

    # 이벤트를 최신순 정렬 후 요약 제공
    raw_events = state.get("events", [])
    sorted_events = sorted(raw_events, key=lambda e: float(e.get("timestamp", 0)), reverse=True)

    visible_events: list[dict[str, Any]] = []
    for event in sorted_events[:10]:  # 상위 10개로 축소
        if not isinstance(event, dict):
            continue
        visible_events.append(_visible_event(event))

    return {
        "scenario_id": state.get("scenario_id"),
        "display_name": state.get("display_name"),
        "current_time": state.get("current_time", 0),
        "tick": state.get("tick"),
        "status": state.get("status"),
        "player": {
            "id": player.get("id"),
            "name": player.get("name"),
            "role": player.get("role"),
            "behavior": player.get("behavior"),
            "gait": player.get("gait"),
            "facing": _compass_from_degrees(float(player.get("facing_degrees", 0.0))),
            "debug_position": _approx_position(player.get("position")),
            "nearby_interaction": nearby,
        },
        "npcs": _npc_summaries(state, player),
        "inventory": list(state.get("inventory", [])),
        "navigation_observation": {
            "visible_landmarks": _relative_landmarks(state, player),
            "local_clearance": _local_clearance(state, player),
            "far_clearance": _far_clearance(state, player),
            "maze_corridors": _maze_open_corridors(state, player),
        },
        "goals": list(state.get("goals", [])),
        "flags": _visible_completion_flags(state.get("flags", {})),
        "events": visible_events,
    }


def _player_actor(state: dict[str, Any]) -> dict[str, Any]:
    actors = state.get("actors", [])
    if not isinstance(actors, list):
        return {}
    return next((actor for actor in actors if actor.get("id") == "rhea"), {})


def _nearby_interaction(state: dict[str, Any], player: dict[str, Any]) -> dict[str, str] | None:
    position = player.get("position")
    zones = state.get("zones", [])
    if not isinstance(position, dict) or not isinstance(zones, list):
        return None
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        center = zone.get("center")
        radius = float(zone.get("radius", 0.0))
        if not isinstance(center, dict) or radius <= 0:
            continue
        dx = player_x - float(center.get("x", 0.0))
        dz = player_z - float(center.get("z", 0.0))
        if (dx * dx + dz * dz) ** 0.5 <= radius:
            return {"name": str(zone.get("name", "Interaction")), "input": "KeyE"}
    return None


def _relative_landmarks(state: dict[str, Any], player: dict[str, Any]) -> list[dict[str, str]]:
    position = player.get("position")
    zones = state.get("zones", [])
    if not isinstance(position, dict) or not isinstance(zones, list):
        return []
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    landmarks: list[dict[str, str]] = []
    for zone in _interactive_zones(zones):
        center = zone.get("center")
        if not isinstance(center, dict):
            continue
        dx = float(center.get("x", 0.0)) - player_x
        dz = float(center.get("z", 0.0)) - player_z
        distance = (dx * dx + dz * dz) ** 0.5
        landmarks.append(
            {
                "name": str(zone.get("name", "Interaction")),
                "direction": _compass_from_vector(dx, dz),
                "distance": _distance_band(distance),
                "debug_position": _format_position(center),
                "input_when_near": "KeyE",
            }
        )
    return sorted(landmarks, key=lambda item: _distance_sort_key(item["distance"]))[:10]


def _local_clearance(state: dict[str, Any], player: dict[str, Any]) -> dict[str, str]:
    """벽을 건너뛰지 않도록 단계별로 확인하며 각 방향으로 약 1.8유닛 이내의 장애물을 조사합니다."""
    position = player.get("position")
    obstacles = state.get("obstacles", [])
    if not isinstance(position, dict) or not isinstance(obstacles, list):
        return {}
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    flags = state.get("flags", {})
    if not isinstance(flags, dict):
        flags = {}

    # 조사 방향: 라벨 -> (dx, dz)
    directions = {
        "north_KeyW": (0.0, -1),
        "south_KeyS": (0.0, 1),
        "east_KeyD": (1, 0),
        "west_KeyA": (-1, 0),
    }

    # 조사를 진행할 거리 단계
    steps = [0.6, 1.2, 1.8]

    clearance: dict[str, str] = {}
    for label, (dx, dz) in directions.items():
        blocker = None
        for dist in steps:
            probe = {"x": player_x + dx * dist, "z": player_z + dz * dist}
            blocker = _blocking_obstacle_name(probe, obstacles, flags)
            if blocker:
                break
        clearance[label] = f"{blocker}에 의해 막힘" if blocker else "통행 가능"
    return clearance


def _far_clearance(state: dict[str, Any], player: dict[str, Any]) -> dict[str, str]:
    """단계별 조사를 통해 전방 약 3.5유닛까지의 장애물을 확인합니다."""
    position = player.get("position")
    obstacles = state.get("obstacles", [])
    if not isinstance(position, dict) or not isinstance(obstacles, list):
        return {}
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    flags = state.get("flags", {})
    if not isinstance(flags, dict):
        flags = {}

    directions = {
        "north_2_KeyW": (0.0, -1),
        "south_2_KeyS": (0.0, 1),
        "east_2_KeyD": (1, 0),
        "west_2_KeyA": (-1, 0),
    }

    # 근거리 너머의 원거리 조사 단계
    steps = [2.4, 3.5]

    clearance: dict[str, str] = {}
    for label, (dx, dz) in directions.items():
        blocker = None
        for dist in steps:
            probe = {"x": player_x + dx * dist, "z": player_z + dz * dist}
            blocker = _blocking_obstacle_name(probe, obstacles, flags)
            if blocker:
                break
        clearance[label] = f"{blocker}에 의해 막힘" if blocker else "통행 가능"
    return clearance


def _maze_open_corridors(state: dict[str, Any], player: dict[str, Any]) -> dict[str, str] | None:
    """플레이어가 미로 구역 안에 있을 때, 현재 위치에서 보이는 뚫린 통로 방향을 반환합니다.

    3인칭 카메라로 3D 미로를 볼 때 플레이어가 인지하는 정보와 유사하게, 벽으로 막혔는지
    또는 통로가 열려 있는지를 보고합니다. 이는 경로 탐색 엔진이 아니며, 바로 앞의
    통로 개방 여부만을 알려줍니다.
    """
    position = player.get("position")
    if not isinstance(position, dict):
        return None
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    if not (
        _MAZE_BOUNDS_X[0] <= player_x <= _MAZE_BOUNDS_X[1]
        and _MAZE_BOUNDS_Z[0] <= player_z <= _MAZE_BOUNDS_Z[1]
    ):
        return None

    obstacles = state.get("obstacles", [])
    if not isinstance(obstacles, list):
        return None
    flags = state.get("flags", {})
    if not isinstance(flags, dict):
        flags = {}

    # 통로의 통행 가능 여부를 확인하기 위해 여러 지점을 조사합니다.
    # 중간 단계에서 벽에 걸리지 않으면 해당 통로는 "open"으로 간주합니다.
    step = 0.45  # 서브 셀 해상도
    max_dist = 1.85  # 미로 한 셀 거리
    directions = {
        "north_KeyW": (0.0, -step),
        "south_KeyS": (0.0, step),
        "east_KeyD": (step, 0.0),
        "west_KeyA": (-step, 0.0),
    }
    corridors: dict[str, str] = {}
    for label, (sx, sz) in directions.items():
        open_corridor = True
        px, pz = player_x, player_z
        walked = 0.0
        while walked < max_dist:
            px += sx
            pz += sz
            walked += step
            probe = {"x": px, "z": pz}
            if _blocking_obstacle_name(probe, obstacles, flags) is not None:
                open_corridor = False
                break
        corridors[label] = "통로 열림" if open_corridor else "벽에 막힘"
    return corridors


def _interactive_zones(zones: Iterable[Any]) -> list[dict[str, Any]]:
    interactive: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        zone_id = str(zone.get("id", ""))
        radius = float(zone.get("radius", 0.0))
        if radius <= 0 or zone_id == "spawn":
            continue
        if (
            zone.get("required_behavior")
            or zone_id.startswith("puzzle_")
            or zone_id in {"npc1", "npc2", "apple_tree", "maze_start", "maze_exit"}
        ):
            interactive.append(zone)
    return interactive


def _blocking_obstacle_name(
    position: dict[str, float],
    obstacles: list[Any],
    flags: dict[str, Any],
) -> str | None:
    actor_radius = 0.32
    for obstacle in obstacles:
        if not isinstance(obstacle, dict):
            continue
        disabled_by_flag = obstacle.get("disabled_by_flag")
        if disabled_by_flag and flags.get(str(disabled_by_flag), False):
            continue
        center = obstacle.get("center")
        if not isinstance(center, dict):
            continue
        if (
            abs(float(position["x"]) - float(center.get("x", 0.0)))
            <= float(obstacle.get("half_extent_x", 0.0)) + actor_radius
            and abs(float(position["z"]) - float(center.get("z", 0.0)))
            <= float(obstacle.get("half_extent_z", 0.0)) + actor_radius
        ):
            return str(obstacle.get("name", "obstacle"))
    return None


def _compass_from_vector(dx: float, dz: float) -> str:
    if abs(dx) < 0.01 and abs(dz) < 0.01:
        return "here"
    # World convention: north is negative z, east is positive x.
    angle = (degrees(atan2(dx, -dz)) + 360.0) % 360.0
    return _compass_from_degrees(angle)


def _compass_from_degrees(angle: float) -> str:
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return directions[int(((angle % 360.0) + 22.5) // 45) % len(directions)]


def _distance_band(distance: float) -> str:
    if distance <= 1.25:
        return "near"
    if distance <= 4.0:
        return "short"
    if distance <= 8.0:
        return "medium"
    return "far"


def _approx_position(position: Any) -> dict[str, float] | None:
    if not isinstance(position, dict):
        return None
    return {
        "x": round(float(position.get("x", 0.0)), 1),
        "z": round(float(position.get("z", 0.0)), 1),
    }


def _format_position(position: Any) -> str:
    approx = _approx_position(position)
    if approx is None:
        return "unknown"
    return f"x={approx['x']}, z={approx['z']}"


def _distance_sort_key(distance: str) -> int:
    return {"near": 0, "short": 1, "medium": 2, "far": 3}.get(distance, 4)


def _visible_completion_flags(flags: dict[str, Any]) -> dict[str, bool]:
    allowed = ["maze_escaped", "puzzle_solved", "quest_complete"]
    return {flag: bool(flags.get(flag, False)) for flag in allowed}


def _visible_event(event: dict[str, Any]) -> dict[str, Any]:
    """단일 이벤트를 플레이어가 인지할 수 있는 형태의 가시 정보로 변환합니다.

    퍼즐 재생 순서나 대화 내용은 화면이나 소리를 통해 플레이어가 직접 경험하는 정보이므로
    그대로 유지합니다. 내부 플래그나 퀘스트 아이템의 숨겨진 데이터 등 엔진 내부 정보는 제외됩니다.
    """
    base = {
        "tick": event.get("tick"),
        "timestamp": event.get("timestamp"),
        "message": event.get("message"),
        "severity": event.get("severity"),
    }
    data = event.get("data")
    if not isinstance(data, dict):
        return base

    event_type = data.get("type")
    if event_type == "puzzle_cue":
        # 플레이어가 화면에서 반짝이는 색상 패드를 관찰합니다.
        base["puzzle_cue"] = data.get("sequence", [])
    elif event_type == "dialogue":
        # 플레이어가 화면의 대화창 레이아웃을 통해 대사를 읽습니다.
        base["dialogue"] = {
            "speaker": data.get("speaker"),
            "line": data.get("line"),
        }
    elif event_type == "quest_item":
        # 플레이어가 아이템이 나타나거나 사라지는 것을 보지만, 내부 플래그는 보지 못합니다.
        base["item_event"] = data.get("type")
    return base


def _npc_summaries(state: dict[str, Any], player: dict[str, Any]) -> list[dict[str, Any]]:
    """플레이어를 기준으로 한 NPC의 대략적인 위치와 방향 요약을 반환합니다."""
    actors = state.get("actors", [])
    if not isinstance(actors, list):
        return []
    position = player.get("position")
    if not isinstance(position, dict):
        return []
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    summaries: list[dict[str, Any]] = []
    for actor in actors:
        if not isinstance(actor, dict):
            continue
        if actor.get("role") == "player character":
            continue
        actor_pos = actor.get("position")
        if not isinstance(actor_pos, dict):
            continue
        dx = float(actor_pos.get("x", 0.0)) - player_x
        dz = float(actor_pos.get("z", 0.0)) - player_z
        distance = (dx * dx + dz * dz) ** 0.5
        summaries.append(
            {
                "name": actor.get("name"),
                "role": actor.get("role"),
                "direction": _compass_from_vector(dx, dz),
                "distance": _distance_band(distance),
                "debug_position": _format_position(actor_pos),
            }
        )
    return summaries
