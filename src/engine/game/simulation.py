from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, radians, sin
from random import Random
from typing import Any

from .contracts import (
    Actor,
    ActorBehavior,
    Gait,
    NavigationObstacle,
    ScenarioStatus,
    Vec3,
    WorldEvent,
    WorldState,
    Zone,
)

SIMON_PADS = [
    "puzzle_red",
    "puzzle_green",
    "puzzle_blue",
    "puzzle_yellow",
    "puzzle_purple",
]
QUEST_FLAGS = [
    "quest_started",
    "apple_harvested",
    "apple_collected",
    "orange_received",
    "quest_complete",
    "maze_started",
]
WORLD_X_LIMIT = 17.2
WORLD_Z_LIMIT = 9.7
MAZE_COLS = 7
MAZE_ROWS = 5
MAZE_CELL_SIZE = 1.85
MAZE_WALL_THICKNESS = 0.18
MAZE_ORIGIN_X = -17.05
MAZE_ORIGIN_Z = -8.75
MAZE_START_CELL = (MAZE_COLS - 1, MAZE_ROWS - 1)
MAZE_EXIT_CELL = (0, 0)
SPAWN_POSITION = Vec3(2.4, 0.0, 0.1)


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str
    state: dict[str, Any]
    degraded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "state": self.state,
            "degraded": self.degraded,
        }


class RuntimeSimulator:
    """에이전트 도구와 브라우저 UI에서 사용하는 결정론적 게임 런타임입니다.

    브라우저는 보간(interpolation)과 렌더링을 담당하며, 이 시뮬레이터는 캐릭터의 위치, 상호작용의 유효성, 목표 달성 여부 등 모든 게임 규칙을 관리합니다. 이를 통해 게임 로직을 3D 시각화 코드와 분리하여 독립적으로 테스트할 수 있습니다.
    """

    def __init__(self, state: WorldState) -> None:
        self.state = state
        self._reset_puzzle_runtime()

    def reset(self) -> dict[str, Any]:
        self.state = build_signal_market_state()
        self._reset_puzzle_runtime()
        self._event("시나리오를 초기화했습니다.")
        return self.state.as_dict()

    def inspect(self) -> dict[str, Any]:
        return self.state.as_dict()

    def move_actor(self, actor_id: str, zone_id: str, gait: Gait = Gait.WALK) -> CommandResult:
        actor = self.state.actors.get(actor_id)
        zone = self.state.zones.get(zone_id)
        if actor is None:
            return self._failure(f"알 수 없는 캐릭터입니다: {actor_id}")
        if zone is None:
            return self._failure(f"알 수 없는 상호작용 영역입니다: {zone_id}")

        previous = actor.position
        target = _zone_navigation_target(zone_id, zone.center)
        if self._blocked(target):
            return self._failure(f"{zone.display_name}까지 가는 길이 충돌 지형에 막혀 있습니다.")

        actor.position = target
        actor.gait = gait
        actor.behavior = ActorBehavior.RUNNING if gait is Gait.RUN else ActorBehavior.WALKING
        actor.facing_degrees = _facing_degrees(previous, zone.center)
        actor.last_zone_id = zone.zone_id
        self.state.tick += 1
        self.state.status = ScenarioStatus.RUNNING
        gait_text = "달려서" if gait is Gait.RUN else "걸어서"
        self._event(f"{actor.display_name}가 {zone.display_name}까지 {gait_text} 이동했습니다.")
        return CommandResult(
            True,
            f"{actor.display_name}가 {zone.display_name}까지 이동했습니다.",
            self.state.as_dict(),
        )

    def perform_action(self, actor_id: str, behavior: ActorBehavior) -> CommandResult:
        actor = self.state.actors.get(actor_id)
        if actor is None:
            return self._failure(f"알 수 없는 캐릭터입니다: {actor_id}")
        if behavior is ActorBehavior.JUMP:
            actor.behavior = ActorBehavior.JUMP
            self.state.tick += 1
            self.state.status = ScenarioStatus.RUNNING
            self._event(f"{actor.display_name}가 점프했습니다.")
            return CommandResult(
                True, f"{actor.display_name}가 점프했습니다.", self.state.as_dict()
            )

        current_zone = self._current_zone(actor)
        if current_zone is None:
            return self._failure(f"{actor.display_name}가 상호작용 영역 안에 있지 않습니다.")
        if (
            current_zone.required_behavior is not None
            and current_zone.required_behavior is not behavior
        ):
            expected = current_zone.required_behavior.value
            return self._failure(
                f"{current_zone.display_name}에는 '{expected}' 행동이 필요하지만 '{behavior.value}'가 입력되었습니다."
            )

        actor.behavior = behavior
        self.state.tick += 1
        if current_zone.success_flag is not None:
            self.state.flags[current_zone.success_flag] = True
        self._event(
            f"{actor.display_name}가 {current_zone.display_name}에서 {behavior.value} 행동을 했습니다."
        )
        self._refresh_status()
        return CommandResult(
            True,
            f"{current_zone.display_name}에서 {behavior.value} 행동을 처리했습니다.",
            self.state.as_dict(),
        )

    def drive_actor(
        self,
        actor_id: str,
        x: float,
        z: float,
        facing_degrees: float,
        gait: Gait = Gait.WALK,
        jumping: bool = False,
        moving: bool = True,
    ) -> CommandResult:
        actor = self.state.actors.get(actor_id)
        if actor is None:
            return self._failure(f"알 수 없는 캐릭터입니다: {actor_id}")

        candidate = Vec3(
            _clamp(x, -WORLD_X_LIMIT, WORLD_X_LIMIT),
            0.0,
            _clamp(z, -WORLD_Z_LIMIT, WORLD_Z_LIMIT),
        )
        blocked_by = self._blocking_obstacle(candidate)
        if blocked_by is not None:
            actor.behavior = ActorBehavior.JUMP if jumping else ActorBehavior.IDLE
            actor.facing_degrees = facing_degrees
            self.state.tick += 1
            self.state.status = ScenarioStatus.RUNNING
            self._event(
                f"{actor.display_name}가 {blocked_by.display_name}에 막혔습니다.", "warning"
            )
            return CommandResult(
                True,
                f"{actor.display_name} 이동 중 {blocked_by.display_name} 충돌로 막혔습니다.",
                self.state.as_dict(),
                degraded=True,
            )

        actor.position = candidate
        actor.gait = gait
        actor.behavior = (
            ActorBehavior.JUMP
            if jumping
            else (
                ActorBehavior.RUNNING
                if moving and gait is Gait.RUN
                else ActorBehavior.WALKING if moving else ActorBehavior.IDLE
            )
        )
        actor.facing_degrees = facing_degrees
        current_zone = self._current_zone(actor)
        actor.last_zone_id = current_zone.zone_id if current_zone is not None else None
        self.state.tick += 1
        self.state.status = ScenarioStatus.RUNNING
        return CommandResult(
            True, f"{actor.display_name}를 입력 방향으로 이동했습니다.", self.state.as_dict()
        )

    def apply_input_buffer(
        self,
        actor_id: str,
        frames: list[dict[str, Any]],
        camera_yaw_degrees: float = 0.0,
    ) -> CommandResult:
        actor = self.state.actors.get(actor_id)
        if actor is None:
            return self._failure(f"알 수 없는 캐릭터입니다: {actor_id}")
        if not frames:
            return self._failure("입력 버퍼가 비어 있습니다.")

        accepted_frames = 0
        blocked_frames = 0
        last_frame_was_locomotion = False
        for frame in frames[:80]:
            keys = {str(key) for key in frame.get("keys", [])}
            duration_ms = int(frame.get("duration_ms", 100))
            if duration_ms <= 0:
                continue
            if duration_ms > 1200:
                duration_ms = 1200

            if "KeyE" in keys:
                self._perform_context_action(actor)
                accepted_frames += 1
                last_frame_was_locomotion = False
                continue

            step_count = max(1, duration_ms // 80)
            step_seconds = duration_ms / 1000.0 / step_count
            moved_this_frame = False
            for _ in range(step_count):
                candidate = self._next_position_from_keys(
                    actor.position, keys, step_seconds, camera_yaw_degrees
                )
                if candidate == actor.position:
                    continue
                blocked_by = self._blocking_obstacle(candidate)
                if blocked_by is not None:
                    blocked_frames += 1
                    self._event(
                        f"{actor.display_name}가 {blocked_by.display_name}에 부딪혔습니다.",
                        "warning",
                    )
                    continue
                actor.position = candidate
                actor.gait = Gait.RUN if _running(keys) else Gait.WALK
                actor.behavior = (
                    ActorBehavior.RUNNING if actor.gait is Gait.RUN else ActorBehavior.WALKING
                )
                actor.facing_degrees = _facing_degrees_from_keys(keys, camera_yaw_degrees)
                self._apply_location_effects(actor)
                moved_this_frame = True
            accepted_frames += 1
            last_frame_was_locomotion = moved_this_frame

        if last_frame_was_locomotion:
            actor.behavior = ActorBehavior.IDLE
            actor.gait = Gait.WALK
        self.state.tick += 1
        self.state.status = ScenarioStatus.RUNNING
        self._refresh_status()
        message = (
            f"입력 프레임 {accepted_frames}개를 적용했습니다"
            if blocked_frames == 0
            else f"입력 프레임 {accepted_frames}개를 적용했고 이동 {blocked_frames}회가 충돌로 막혔습니다"
        )
        return CommandResult(
            True,
            message,
            self.state.as_dict(),
            degraded=blocked_frames > 0,
        )

    def _current_zone(self, actor: Actor) -> Zone | None:
        for zone in self.state.zones.values():
            if zone.contains(actor.position):
                return zone
        return None

    def _blocked(self, position: Vec3) -> bool:
        return self._blocking_obstacle(position) is not None

    def _blocking_obstacle(self, position: Vec3) -> NavigationObstacle | None:
        for obstacle in self.state.obstacles:
            if obstacle.blocks(position, flags=self.state.flags):
                return obstacle
        return None

    def _next_position_from_keys(
        self,
        position: Vec3,
        keys: set[str],
        step_seconds: float,
        camera_yaw_degrees: float,
    ) -> Vec3:
        move_x, move_z = _movement_axis(keys, camera_yaw_degrees)
        if move_x == 0.0 and move_z == 0.0:
            return position
        speed = 4.8 if _running(keys) else 2.45
        return Vec3(
            _clamp(position.x + move_x * speed * step_seconds, -WORLD_X_LIMIT, WORLD_X_LIMIT),
            0.0,
            _clamp(position.z + move_z * speed * step_seconds, -WORLD_Z_LIMIT, WORLD_Z_LIMIT),
        )

    def _perform_context_action(self, actor: Actor) -> None:
        zone = self._current_zone(actor)
        if zone is None:
            self._event(f"{actor.display_name}가 E를 눌렀지만 가까운 대상이 없습니다.", "warning")
            return
        if zone.zone_id == "npc1":
            self._handle_npc1_dialogue(actor)
            return
        if zone.zone_id == "npc2":
            self._handle_npc2_dialogue(actor)
            return
        if zone.zone_id == "apple_tree":
            self._handle_apple_tree(actor)
            return
        if zone.zone_id == "puzzle_play":
            self._handle_puzzle_play(actor)
            return
        if zone.zone_id in SIMON_PADS:
            self._handle_puzzle_pad(actor, zone)
            return
        if zone.zone_id == "maze_start":
            self._handle_maze_start(actor)
            return
        if zone.zone_id == "maze_exit":
            self._handle_maze_exit(actor)
            return
        if zone.required_behavior is not None:
            self.perform_action(actor.actor_id, zone.required_behavior)
            return
        self._event(f"{actor.display_name}가 {zone.display_name}을 사용했습니다.")

    def _handle_npc1_dialogue(self, actor: Actor) -> None:
        actor.behavior = ActorBehavior.TALK
        if self.state.flags.get("orange_received", False):
            self.state.flags["quest_complete"] = True
            self.state.flags["orange_received"] = False
            self._remove_inventory("오렌지")
            self._dialogue(
                "미라",
                "오렌지를 가져왔구나. 이걸 상자에 넣으면 퀘스트 검증 준비가 끝나. 정말 고마워.",
                "npc1",
                close_after_ms=4200,
            )
            self._refresh_status()
            return

        if self.state.flags.get("quest_complete", False):
            self._dialogue(
                "미라", "오렌지 전달은 완료됐어. 이제 다른 실습으로 넘어가도 좋아.", "npc1"
            )
            return

        if not self.state.flags.get("quest_started", False):
            self.state.flags["quest_started"] = True
            self._dialogue(
                "미라",
                "상자에 넣을 오렌지가 필요해. 아까 토마가 오렌지를 가지고 있던 것 같아.",
                "npc1",
            )
            return

        self._dialogue(
            "미라",
            "오렌지는 토마에게 물어봐 줘. 상자에 넣을 오렌지가 아직 필요해.",
            "npc1",
        )

    def _handle_npc2_dialogue(self, actor: Actor) -> None:
        actor.behavior = ActorBehavior.TALK
        if not self.state.flags.get("quest_started", False):
            self._dialogue(
                "토마",
                "과일 샘플을 정리하는 중이야. 할 일이 필요하면 미라에게 먼저 말을 걸어봐.",
                "npc2",
            )
            return

        if self.state.flags.get("apple_collected", False):
            self.state.flags["apple_collected"] = False
            self.state.flags["orange_received"] = True
            self._remove_inventory("사과")
            self._add_inventory("오렌지")
            self._dialogue(
                "토마",
                "사과를 가져왔네. 약속대로 오렌지를 줄게. 이제 미라에게 가져다줘.",
                "npc2",
                close_after_ms=4600,
            )
            return

        if self.state.flags.get("orange_received", False):
            self._dialogue(
                "토마", "오렌지는 이미 줬어. 미라가 실험장 길목에서 기다리고 있어.", "npc2"
            )
            return

        self._dialogue("토마", "오렌지를 줄 수는 있는데, 먼저 신선한 사과와 바꾸고 싶어.", "npc2")

    def _handle_apple_tree(self, actor: Actor) -> None:
        actor.behavior = ActorBehavior.INSPECT
        if not self.state.flags.get("quest_started", False):
            self._event(
                f"{actor.display_name}가 사과나무를 살폈지만 아직 사과가 필요하지 않습니다."
            )
            return
        if self.state.flags.get("apple_collected", False):
            self._event(
                f"{actor.display_name}가 사과나무를 다시 살폈지만 이미 사과를 하나 챙겼습니다."
            )
            return
        if self.state.flags.get("orange_received", False) or self.state.flags.get(
            "quest_complete", False
        ):
            self._event(f"{actor.display_name}가 거래를 마친 뒤 사과나무를 확인했습니다.")
            return
        self.state.flags["apple_harvested"] = True
        self.state.flags["apple_collected"] = True
        self._add_inventory("사과")
        self._event(
            f"{actor.display_name}가 나무에서 사과를 하나 땄습니다. 인벤토리에 사과가 들어왔습니다.",
            data={"type": "quest_item", "item": "apple", "visible": False},
        )

    def _reset_puzzle_runtime(self) -> None:
        self.puzzle_sequence = Random(29).sample(SIMON_PADS, k=5)
        self.puzzle_phase = 0
        self.puzzle_input_index = 0

    def _clear_puzzle_flags(self) -> None:
        phase_flags = [f"puzzle_phase_{phase}" for phase in range(1, len(SIMON_PADS) + 1)]
        for flag in ["puzzle_ready", *phase_flags, "puzzle_solved"]:
            self.state.flags[flag] = False
        for pad_id in SIMON_PADS:
            self.state.flags[pad_id] = False

    def _handle_puzzle_play(self, actor: Actor) -> None:
        if self.state.flags.get("puzzle_solved", False):
            self._event("기억 퍼즐 게이트는 이미 열려 있습니다.")
            return
        actor.behavior = ActorBehavior.INSPECT
        self.puzzle_phase = 1
        self.puzzle_input_index = 0
        self._clear_puzzle_flags()
        self.state.flags["puzzle_ready"] = True
        self._puzzle_cue_event(self.puzzle_sequence[:1])

    def _handle_puzzle_pad(self, actor: Actor, zone: Zone) -> None:
        if self.puzzle_phase == 0:
            self._event("기억 콘솔이 대기 중입니다. 먼저 재생 받침대를 눌러야 합니다.", "warning")
            return

        expected_zone_id = self.puzzle_sequence[self.puzzle_input_index]
        if zone.zone_id != expected_zone_id:
            self._reset_puzzle_runtime()
            self._clear_puzzle_flags()
            self._event(
                f"{actor.display_name}가 {zone.display_name}을 눌렀지만 순서가 틀려 기억 퍼즐이 초기화됩니다.",
                "warning",
            )
            return

        self.state.flags[zone.zone_id] = True
        actor.behavior = ActorBehavior.INSPECT
        self.puzzle_input_index += 1
        if self.puzzle_input_index < self.puzzle_phase:
            self._event(
                f"{actor.display_name}가 {_pad_label_ko(zone.zone_id)} 패드를 반복했습니다."
            )
            return

        phase_flag = f"puzzle_phase_{self.puzzle_phase}"
        self.state.flags[phase_flag] = True
        if self.puzzle_phase == len(self.puzzle_sequence):
            self.state.flags["puzzle_solved"] = True
            self._event(f"{actor.display_name}가 기억 순서를 완료해 게이트를 열었습니다.")
        else:
            self.puzzle_phase += 1
            self.puzzle_input_index = 0
            for pad_id in SIMON_PADS:
                self.state.flags[pad_id] = False
            self._puzzle_cue_event(self.puzzle_sequence[: self.puzzle_phase])

    def _puzzle_cue_event(self, zone_ids: list[str]) -> None:
        self._event(
            f"기억 콘솔이 {len(zone_ids)}단계 빛 패턴을 재생합니다.",
            data={
                "type": "puzzle_cue",
                "sequence": [_pad_label(zone_id) for zone_id in zone_ids],
            },
        )

    def _handle_maze_start(self, actor: Actor) -> None:
        if not self.state.flags.get("maze_started", False):
            self.state.flags["maze_started"] = True
            self._event(f"{actor.display_name}가 미로 검증을 시작했습니다. 이제 출구로 향하세요.")
            self._refresh_status()

    def _handle_maze_exit(self, actor: Actor) -> None:
        if self.state.flags.get("maze_escaped", False):
            return

        if not self.state.flags.get("maze_started", False):
            self._event(
                "미로 출구에 도착했지만 시작 지점을 거치지 않았습니다. 시작 지점부터 다시 통과해 주세요.",
                "warning",
            )
            return

        self.state.flags["maze_escaped"] = True
        actor.position = SPAWN_POSITION
        actor.behavior = ActorBehavior.WAVE
        self._event(
            f"{actor.display_name}가 미로를 완벽하게 탈출했습니다!",
            data={"type": "celebration", "sound": "goal"},
        )
        self._refresh_status()

    def _apply_location_effects(self, actor: Actor) -> None:
        zone = self._current_zone(actor)
        actor.last_zone_id = zone.zone_id if zone is not None else None
        if zone is None:
            return
        if zone.zone_id == "maze_start":
            self._handle_maze_start(actor)
            return
        if zone.zone_id == "maze_exit":
            self._handle_maze_exit(actor)
            return

    def _refresh_status(self) -> None:
        if all(
            self.state.flags.get(flag, False)
            for flag in ["maze_escaped", "puzzle_solved", "quest_complete"]
        ):
            self.state.status = ScenarioStatus.PASSED
            self._event("튜토리얼 목표를 모두 완료했습니다: NPC 퀘스트, 미로 탈출, 기억 퍼즐.")

    def _dialogue(
        self,
        speaker: str,
        line: str,
        zone_id: str,
        close_after_ms: int = 5200,
    ) -> None:
        self._event(
            f"{speaker}: {line}",
            data={
                "type": "dialogue",
                "speaker": speaker,
                "line": line,
                "zone_id": zone_id,
                "close_after_ms": close_after_ms,
            },
        )

    def _add_inventory(self, item: str) -> None:
        if item not in self.state.inventory:
            self.state.inventory.append(item)

    def _remove_inventory(self, item: str) -> None:
        self.state.inventory = [stored for stored in self.state.inventory if stored != item]

    def _event(
        self,
        message: str,
        severity: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.state.events.append(WorldEvent(self.state.tick, message, severity, data))

    def _failure(self, message: str) -> CommandResult:
        self.state.tick += 1
        self.state.status = ScenarioStatus.FAILED
        self._event(message, "error")
        return CommandResult(False, message, self.state.as_dict(), degraded=True)


def _facing_degrees(start: Vec3, end: Vec3) -> float:
    return degrees(atan2(end.x - start.x, end.z - start.z))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _running(keys: set[str]) -> bool:
    return "ShiftLeft" in keys or "ShiftRight" in keys or "Shift" in keys


def _movement_axis(keys: set[str], camera_yaw_degrees: float) -> tuple[float, float]:
    yaw = radians(camera_yaw_degrees)
    forward_x = -sin(yaw)
    forward_z = -cos(yaw)
    right_x = cos(yaw)
    right_z = -sin(yaw)
    x = 0.0
    z = 0.0
    if "KeyW" in keys or "W" in keys:
        x += forward_x
        z += forward_z
    if "KeyS" in keys or "S" in keys:
        x -= forward_x
        z -= forward_z
    if "KeyD" in keys or "D" in keys:
        x += right_x
        z += right_z
    if "KeyA" in keys or "A" in keys:
        x -= right_x
        z -= right_z
    length = (x * x + z * z) ** 0.5
    if length == 0.0:
        return (0.0, 0.0)
    return (x / length, z / length)


def _facing_degrees_from_keys(keys: set[str], camera_yaw_degrees: float) -> float:
    x, z = _movement_axis(keys, camera_yaw_degrees)
    if x == 0.0 and z == 0.0:
        return camera_yaw_degrees
    return degrees(atan2(x, z))


def _zone_navigation_target(zone_id: str, center: Vec3) -> Vec3:
    targets: dict[str, Vec3] = {}
    return targets.get(zone_id, center)


def _pad_label(zone_id: str) -> str:
    return {
        "puzzle_red": "red",
        "puzzle_green": "green",
        "puzzle_blue": "blue",
        "puzzle_yellow": "yellow",
        "puzzle_purple": "purple",
    }.get(zone_id, zone_id)


def _pad_label_ko(zone_id: str) -> str:
    return {
        "puzzle_red": "빨간색",
        "puzzle_green": "초록색",
        "puzzle_blue": "파란색",
        "puzzle_yellow": "노란색",
        "puzzle_purple": "보라색",
    }.get(zone_id, zone_id)


def _pad_names(zone_ids: list[str]) -> str:
    return " -> ".join(_pad_label(zone_id) for zone_id in zone_ids)


def _maze_cell_center(cell: tuple[int, int]) -> Vec3:
    col, row = cell
    return Vec3(
        round(MAZE_ORIGIN_X + col * MAZE_CELL_SIZE + MAZE_CELL_SIZE / 2, 3),
        0.0,
        round(MAZE_ORIGIN_Z + row * MAZE_CELL_SIZE + MAZE_CELL_SIZE / 2, 3),
    )


def _maze_start_position() -> Vec3:
    center = _maze_cell_center(MAZE_START_CELL)
    return Vec3(
        round(MAZE_ORIGIN_X + MAZE_COLS * MAZE_CELL_SIZE + 0.62, 3),
        0.0,
        center.z,
    )


def _maze_exit_position() -> Vec3:
    return _maze_cell_center(MAZE_EXIT_CELL)


def _generated_maze_walls() -> dict[tuple[int, int], set[str]]:
    walls = {
        (col, row): {"N", "S", "E", "W"} for row in range(MAZE_ROWS) for col in range(MAZE_COLS)
    }
    visited = {MAZE_START_CELL}
    stack = [MAZE_START_CELL]
    random = Random(17)
    directions = [
        ("N", (0, -1), "S"),
        ("S", (0, 1), "N"),
        ("E", (1, 0), "W"),
        ("W", (-1, 0), "E"),
    ]
    while stack:
        col, row = stack[-1]
        candidates: list[tuple[str, tuple[int, int], str]] = []
        for direction, (dx, dz), opposite in directions:
            neighbor = (col + dx, row + dz)
            if (
                0 <= neighbor[0] < MAZE_COLS
                and 0 <= neighbor[1] < MAZE_ROWS
                and neighbor not in visited
            ):
                candidates.append((direction, neighbor, opposite))
        if not candidates:
            stack.pop()
            continue
        direction, neighbor, opposite = random.choice(candidates)
        walls[(col, row)].remove(direction)
        walls[neighbor].remove(opposite)
        visited.add(neighbor)
        stack.append(neighbor)
    walls[MAZE_START_CELL].remove("E")
    walls[MAZE_EXIT_CELL].remove("W")
    return walls


def _maze_obstacles() -> list[NavigationObstacle]:
    obstacles: list[NavigationObstacle] = []
    walls = _generated_maze_walls()
    seen: set[tuple[float, float, float, float]] = set()
    half_thickness = MAZE_WALL_THICKNESS / 2
    for (col, row), cell_walls in walls.items():
        center = _maze_cell_center((col, row))
        wall_specs = {
            "N": (
                center.x,
                center.z - MAZE_CELL_SIZE / 2,
                MAZE_CELL_SIZE / 2 + half_thickness,
                half_thickness,
            ),
            "S": (
                center.x,
                center.z + MAZE_CELL_SIZE / 2,
                MAZE_CELL_SIZE / 2 + half_thickness,
                half_thickness,
            ),
            "E": (
                center.x + MAZE_CELL_SIZE / 2,
                center.z,
                half_thickness,
                MAZE_CELL_SIZE / 2 + half_thickness,
            ),
            "W": (
                center.x - MAZE_CELL_SIZE / 2,
                center.z,
                half_thickness,
                MAZE_CELL_SIZE / 2 + half_thickness,
            ),
        }
        for direction in sorted(cell_walls):
            x, z, half_x, half_z = wall_specs[direction]
            key = (round(x, 3), round(z, 3), round(half_x, 3), round(half_z, 3))
            if key in seen:
                continue
            seen.add(key)
            obstacles.append(
                NavigationObstacle(
                    f"maze_wall_{col}_{row}_{direction.lower()}",
                    "미로 벽",
                    Vec3(round(x, 3), 0.0, round(z, 3)),
                    round(half_x, 3),
                    round(half_z, 3),
                )
            )
    return obstacles


def build_signal_market_state() -> WorldState:
    state = WorldState(
        scenario_id="agent_playtest_lab",
        display_name="Agent Playtest Lab",
        design_intent=(
            "A small third-person playtest lab where an ADK agent helps game developers: "
            "drive the same character controls a player has, verify interaction outcomes, "
            "and solve gameplay tasks from screenshot evidence."
        ),
    )
    state.actors = {
        "rhea": Actor(
            actor_id="rhea",
            display_name="캐릭터",
            role="player character",
            position=SPAWN_POSITION,
        ),
        "npc1": Actor(
            actor_id="npc1",
            display_name="미라",
            role="quest giver",
            position=Vec3(4.3, 0.0, -2.25),
            facing_degrees=-55.0,
        ),
        "npc2": Actor(
            actor_id="npc2",
            display_name="토마",
            role="fruit trader",
            position=Vec3(0.0, 0.0, -1.0),
            facing_degrees=180.0,
        ),
    }
    state.zones = {
        "spawn": Zone(
            "spawn",
            "Training Hub",
            SPAWN_POSITION,
            1.2,
            "Starting point for repeatable agent playtest runs.",
        ),
        "npc1": Zone(
            "npc1",
            "미라",
            Vec3(4.3, 0.0, -2.25),
            1.05,
            "Talk with Mira through the same E interaction a player uses.",
        ),
        "npc2": Zone(
            "npc2",
            "토마",
            Vec3(0.0, 0.0, -1.0),
            1.05,
            "Talk with Toma through the same E interaction a player uses.",
        ),
        "apple_tree": Zone(
            "apple_tree",
            "Apple Tree",
            Vec3(14.35, 0.0, 6.45),
            1.15,
            "A harvestable tree that responds to the same E interaction a player uses.",
        ),
        "maze_start": Zone(
            "maze_start",
            "Maze Start",
            _maze_start_position(),
            0.72,
            "Required start marker for maze verification.",
        ),
        "quest_goal": Zone(
            "quest_goal",
            "NPC 퀘스트",
            Vec3(0.0, 0.0, 0.0),
            0.0,
            "Broad quest objective shown in the HUD without exposing the route.",
            None,
            "quest_complete",
        ),
        "maze_exit": Zone(
            "maze_exit",
            "미로 탈출",
            _maze_exit_position(),
            0.72,
            "Escape target for the input-buffer-only maze challenge.",
            None,
            "maze_escaped",
        ),
        "puzzle_play": Zone(
            "puzzle_play",
            "Memory Console",
            Vec3(7.25, 0.0, 1.25),
            0.95,
            "Start the memory sequence so the player can observe and repeat colored pads.",
        ),
        "puzzle_red": Zone(
            "puzzle_red",
            "Red Puzzle Pad",
            Vec3(6.05, 0.0, 2.72),
            0.58,
            "Red pad in the memory puzzle.",
        ),
        "puzzle_green": Zone(
            "puzzle_green",
            "Green Puzzle Pad",
            Vec3(7.25, 0.0, 3.55),
            0.58,
            "Green pad in the memory puzzle.",
        ),
        "puzzle_blue": Zone(
            "puzzle_blue",
            "Blue Puzzle Pad",
            Vec3(8.45, 0.0, 2.72),
            0.58,
            "Blue pad in the memory puzzle.",
        ),
        "puzzle_yellow": Zone(
            "puzzle_yellow",
            "Yellow Puzzle Pad",
            Vec3(6.55, 0.0, 4.28),
            0.58,
            "Yellow pad in the memory puzzle.",
        ),
        "puzzle_purple": Zone(
            "puzzle_purple",
            "Purple Puzzle Pad",
            Vec3(7.95, 0.0, 4.28),
            0.58,
            "Purple pad in the memory puzzle.",
        ),
        "puzzle_gate": Zone(
            "puzzle_gate",
            "퍼즐 게이트",
            Vec3(7.25, 0.0, 5.38),
            0.62,
            "Gate that opens after the visible floor-pad sequence is solved.",
            None,
            "puzzle_solved",
        ),
    }
    state.obstacles = [
        NavigationObstacle("north_wall", "북쪽 경계벽", Vec3(0.0, 0.0, -10.55), 18.2, 0.18),
        NavigationObstacle("south_wall", "남쪽 경계벽", Vec3(0.0, 0.0, 10.55), 18.2, 0.18),
        NavigationObstacle("west_wall", "서쪽 경계벽", Vec3(-17.85, 0.0, 0.0), 0.18, 10.7),
        NavigationObstacle("east_wall", "동쪽 경계벽", Vec3(17.85, 0.0, 0.0), 0.18, 10.7),
        NavigationObstacle("bench_south_a", "휴식 벤치", Vec3(-1.1, 0.0, 6.75), 0.78, 0.32),
        NavigationObstacle("bench_south_b", "휴식 벤치", Vec3(3.0, 0.0, 6.75), 0.78, 0.32),
        NavigationObstacle("tree_sw", "화단 나무", Vec3(-15.25, 0.0, 7.45), 0.5, 0.5),
        NavigationObstacle("tree_se", "화단 나무", Vec3(10.9, 0.0, 6.25), 0.5, 0.5),
        NavigationObstacle("tree_ne", "화단 나무", Vec3(13.9, 0.0, -6.45), 0.5, 0.5),
        NavigationObstacle("apple_tree", "사과나무", Vec3(14.35, 0.0, 6.45), 0.52, 0.52),
        NavigationObstacle("npc1_body", "미라", Vec3(4.3, 0.0, -2.25), 0.28, 0.28),
        NavigationObstacle("npc2_body", "토마", Vec3(0.0, 0.0, -1.0), 0.28, 0.28),
        NavigationObstacle("puzzle_console", "기억 콘솔 받침대", Vec3(7.25, 0.0, 1.25), 0.25, 0.25),
        *_maze_obstacles(),
        NavigationObstacle(
            "puzzle_gate_barrier",
            "퍼즐 게이트 장벽",
            Vec3(7.25, 0.0, 5.0),
            0.98,
            0.12,
            "puzzle_solved",
        ),
    ]
    state.flags = {
        "maze_escaped": False,
        "puzzle_ready": False,
        "puzzle_red": False,
        "puzzle_green": False,
        "puzzle_blue": False,
        "puzzle_yellow": False,
        "puzzle_purple": False,
        **{f"puzzle_phase_{phase}": False for phase in range(1, len(SIMON_PADS) + 1)},
        "puzzle_solved": False,
        **{flag: False for flag in QUEST_FLAGS},
    }
    state.events = [WorldEvent(0, "Agent Playtest Lab을 불러왔습니다.")]
    return state


def create_default_simulator() -> RuntimeSimulator:
    return RuntimeSimulator(build_signal_market_state())
