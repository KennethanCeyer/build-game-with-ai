from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import sqrt
from typing import Any


class Gait(str, Enum):
    WALK = "walk"
    RUN = "run"


class ActorBehavior(str, Enum):
    IDLE = "idle"
    WALKING = "walking"
    RUNNING = "running"
    JUMP = "jump"
    WAVE = "wave"
    TALK = "talk"
    INSPECT = "inspect"
    CALIBRATE = "calibrate"


class ScenarioStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def distance_to(self, other: Vec3) -> float:
        return sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2)

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass(frozen=True)
class Zone:
    zone_id: str
    display_name: str
    center: Vec3
    radius: float
    purpose: str
    required_behavior: ActorBehavior | None = None
    success_flag: str | None = None

    def contains(self, position: Vec3) -> bool:
        return self.center.distance_to(position) <= self.radius

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.zone_id,
            "name": self.display_name,
            "center": self.center.as_dict(),
            "radius": self.radius,
            "purpose": self.purpose,
            "required_behavior": (
                self.required_behavior.value if self.required_behavior is not None else None
            ),
            "success_flag": self.success_flag,
        }


@dataclass(frozen=True)
class NavigationObstacle:
    obstacle_id: str
    display_name: str
    center: Vec3
    half_extent_x: float
    half_extent_z: float
    disabled_by_flag: str | None = None

    def blocks(
        self,
        position: Vec3,
        actor_radius: float = 0.32,
        flags: dict[str, bool] | None = None,
    ) -> bool:
        if self.disabled_by_flag is not None and flags and flags.get(self.disabled_by_flag, False):
            return False
        return (
            abs(position.x - self.center.x) <= self.half_extent_x + actor_radius
            and abs(position.z - self.center.z) <= self.half_extent_z + actor_radius
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.obstacle_id,
            "name": self.display_name,
            "center": self.center.as_dict(),
            "half_extent_x": self.half_extent_x,
            "half_extent_z": self.half_extent_z,
            "disabled_by_flag": self.disabled_by_flag,
        }


@dataclass
class Actor:
    actor_id: str
    display_name: str
    role: str
    position: Vec3
    behavior: ActorBehavior = ActorBehavior.IDLE
    gait: Gait = Gait.WALK
    facing_degrees: float = 0.0
    last_zone_id: str | None = None
    last_teleport_tick: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.actor_id,
            "name": self.display_name,
            "role": self.role,
            "position": self.position.as_dict(),
            "behavior": self.behavior.value,
            "gait": self.gait.value,
            "facing_degrees": self.facing_degrees,
            "last_zone_id": self.last_zone_id,
        }


@dataclass(frozen=True)
class WorldEvent:
    tick: int
    timestamp: float
    message: str
    severity: str = "info"
    data: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        event = {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "message": self.message,
            "severity": self.severity,
        }
        if self.data is not None:
            event["data"] = self.data
        return event


@dataclass
class WorldState:
    scenario_id: str
    display_name: str
    design_intent: str
    tick: int = 0
    status: ScenarioStatus = ScenarioStatus.READY
    actors: dict[str, Actor] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    obstacles: list[NavigationObstacle] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)
    inventory: list[str] = field(default_factory=list)
    events: list[WorldEvent] = field(default_factory=list)
    agent_memory: dict[str, Any] = field(default_factory=dict)
    last_input_buffer: dict[str, Any] | None = None

    def visible_goals(self) -> list[str]:
        goals: list[str] = []
        for zone in self.zones.values():
            if zone.success_flag is None:
                continue
            state = "done" if self.flags.get(zone.success_flag, False) else "pending"
            goals.append(f"{zone.display_name}: {state}")
        return goals

    def as_dict(self) -> dict[str, Any]:
        # 최신 이벤트를 상단에 배치하고 최대 30개까지 노출
        sorted_events = sorted(self.events, key=lambda e: e.timestamp, reverse=True)
        data = {
            "scenario_id": self.scenario_id,
            "display_name": self.display_name,
            "design_intent": self.design_intent,
            "tick": self.tick,
            "status": self.status.value,
            "actors": [actor.as_dict() for actor in self.actors.values()],
            "zones": [zone.as_dict() for zone in self.zones.values()],
            "obstacles": [obstacle.as_dict() for obstacle in self.obstacles],
            "flags": self.flags,
            "inventory": list(self.inventory),
            "goals": self.visible_goals(),
            "events": [event.as_dict() for event in sorted_events[:30]],
            "agent_memory": self.agent_memory,
        }
        if self.last_input_buffer:
            data["last_input_buffer"] = self.last_input_buffer
        return data
