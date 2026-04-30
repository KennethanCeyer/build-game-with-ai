from __future__ import annotations

from collections.abc import Iterable
from math import atan2, degrees
from typing import Any

_MAZE_BOUNDS_X = (-17.5, -3.5)
_MAZE_BOUNDS_Z = (-9.2, 1.0)


def agent_visible_state(state: dict[str, Any]) -> dict[str, Any]:
    """Project full runtime state into the compact state an ADK tool may expose.

    The browser needs exact coordinates, obstacles, and visual event payloads to
    render. The agent does not. This view intentionally strips exact coordinates,
    all obstacles, zone centers/radii, puzzle answer payloads, and quest item
    flags while retaining broad UI-style information useful for playtesting.
    """

    player = _player_actor(state)
    nearby = _nearby_interaction(state, player)
    visible_events: list[dict[str, Any]] = []
    for event in state.get("events", []):
        if not isinstance(event, dict):
            continue
        visible_events.append(_visible_event(event))
    return {
        "scenario_id": state.get("scenario_id"),
        "display_name": state.get("display_name"),
        "tick": state.get("tick"),
        "status": state.get("status"),
        "observation_policy": (
            "Primary evidence is the attached screenshot. This state contains no exact "
            "obstacle geometry, hidden routes, puzzle sequences, or quest item flags. It may "
            "include coarse debug coordinates and local clearance like a minimap/debug HUD."
        ),
        "controls": ["KeyW", "KeyA", "KeyS", "KeyD", "ShiftLeft", "Space", "KeyE"],
        "tool_contract": {
            "controllable_actor_id": "rhea",
            "movement_tool": "apply_input_buffer",
            "camera_tool": "adjust_camera_view",
            "notes": [
                "Use actor_id='rhea' if the tool asks for actor_id.",
                "Prefer 2-6 short frames per tool call so movement is visible.",
            ],
        },
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
            "frame": (
                "Compass-style, player-visible navigation summary. It gives direction bands "
                "to visible interaction labels, not exact coordinates, paths, walls, or puzzle answers."
            ),
            "movement_hint": (
                "With camera_yaw_degrees=0, KeyW moves north, KeyS south, KeyD east, KeyA west. "
                "Use short input buffers, then inspect again."
            ),
            "visible_landmarks": _relative_landmarks(state, player),
            "local_clearance": _local_clearance(state, player),
            "far_clearance": _far_clearance(state, player),
            "maze_corridors": _maze_open_corridors(state, player),
        },
        "objective_context": [
            "NPC 퀘스트는 대화 박스와 인벤토리로 추론한다.",
            "미로 탈출은 미로 시작 라벨을 먼저 통과한 뒤 출구 라벨로 나가야 인정된다.",
            "이 정보는 플레이어 UI에 보이는 일반 상태이며 좌표/정답/숨은 경로는 포함하지 않는다.",
        ],
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
    """Probe up to ~1.8 units in each cardinal direction using steps to avoid skipping walls."""
    position = player.get("position")
    obstacles = state.get("obstacles", [])
    if not isinstance(position, dict) or not isinstance(obstacles, list):
        return {}
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    flags = state.get("flags", {})
    if not isinstance(flags, dict):
        flags = {}
    
    # Probing directions: label -> (dx, dz)
    directions = {
        "north_KeyW": (0.0, -1),
        "south_KeyS": (0.0, 1),
        "east_KeyD": (1, 0),
        "west_KeyA": (-1, 0),
    }
    
    # Distances to check for local clearance
    steps = [0.6, 1.2, 1.8]
    
    clearance: dict[str, str] = {}
    for label, (dx, dz) in directions.items():
        blocker = None
        for dist in steps:
            probe = {"x": player_x + dx * dist, "z": player_z + dz * dist}
            blocker = _blocking_obstacle_name(probe, obstacles, flags)
            if blocker:
                break
        clearance[label] = f"blocked by {blocker}" if blocker else "clear"
    return clearance


def _far_clearance(state: dict[str, Any], player: dict[str, Any]) -> dict[str, str]:
    """Probe up to ~3.5 units ahead using steps."""
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
    
    # Far probes check beyond local
    steps = [2.4, 3.5]
    
    clearance: dict[str, str] = {}
    for label, (dx, dz) in directions.items():
        blocker = None
        for dist in steps:
            probe = {"x": player_x + dx * dist, "z": player_z + dz * dist}
            blocker = _blocking_obstacle_name(probe, obstacles, flags)
            if blocker:
                break
        clearance[label] = f"blocked by {blocker}" if blocker else "clear"
    return clearance


def _maze_open_corridors(
    state: dict[str, Any], player: dict[str, Any]
) -> dict[str, str] | None:
    """When the player is inside the maze area, return which cardinal
    directions have open corridors visible from the current position.

    This is equivalent to what a player sees looking at the 3D maze from
    the third-person camera — obvious open vs. walled corridors.  It is
    NOT a path solver; it only reports immediate corridor openings.
    """
    position = player.get("position")
    if not isinstance(position, dict):
        return None
    player_x = float(position.get("x", 0.0))
    player_z = float(position.get("z", 0.0))
    if not (_MAZE_BOUNDS_X[0] <= player_x <= _MAZE_BOUNDS_X[1]
            and _MAZE_BOUNDS_Z[0] <= player_z <= _MAZE_BOUNDS_Z[1]):
        return None

    obstacles = state.get("obstacles", [])
    if not isinstance(obstacles, list):
        return None
    flags = state.get("flags", {})
    if not isinstance(flags, dict):
        flags = {}

    # Probe a series of points along each corridor to check walkability.
    # A corridor is "open" if no wall blocks any of the intermediate steps.
    step = 0.45  # sub-cell resolution
    max_dist = 1.85  # one maze cell
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
        corridors[label] = "open" if open_corridor else "wall"
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
    """Return a player-visible projection of a single event.

    Puzzle cue sequences and dialogue lines are what a player sees/hears
    on screen, so they are preserved.  Internal flags, quest-item hidden
    data, and other engine internals are stripped.
    """
    base = {key: value for key, value in event.items() if key != "data"}
    data = event.get("data")
    if not isinstance(data, dict):
        return base

    event_type = data.get("type")
    if event_type == "puzzle_cue":
        # The player watches colored pads flash on screen.
        base["puzzle_cue"] = data.get("sequence", [])
    elif event_type == "dialogue":
        # The player reads dialogue in a box overlay.
        base["dialogue"] = {
            "speaker": data.get("speaker"),
            "line": data.get("line"),
        }
    elif event_type == "quest_item":
        # The player sees an item appear/disappear but not hidden flags.
        base["item_event"] = data.get("type")
    return base


def _npc_summaries(
    state: dict[str, Any], player: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return coarse NPC positions and directions relative to the player."""
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
        summaries.append({
            "name": actor.get("name"),
            "role": actor.get("role"),
            "direction": _compass_from_vector(dx, dz),
            "distance": _distance_band(distance),
            "debug_position": _format_position(actor_pos),
        })
    return summaries
