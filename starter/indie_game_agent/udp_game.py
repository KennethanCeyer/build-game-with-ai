from __future__ import annotations

import argparse
import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logging_utils import get_logger
from .runtime_bridge import BUFFER_SIZE, UDP_HOST, UDP_PORT


logger = get_logger("indie_game_agent.udp_game")


MOVE_DELTAS = {
    "up": (0, -1),
    "right": (1, 0),
    "down": (0, 1),
    "left": (-1, 0),
}

FACING_DELTAS = {
    "up": (0, -1),
    "right": (1, 0),
    "down": (0, 1),
    "left": (-1, 0),
}

FACING_SYMBOLS = {
    "up": "^",
    "right": ">",
    "down": "v",
    "left": "<",
}

ROOM_PRESETS = {
    "vault_intro": {
        "name": "Vault Intro",
        "objective": "Read the watcher lane, take the lower route to the relic, then leave through the exit.",
        "grid": [
            "#########",
            "#....v.E#",
            "#.......#",
            "#.......#",
            "#....C..#",
            "#.....R.#",
            "#.......#",
            "#P......#",
            "#########",
        ],
    },
    "crossfire_gallery": {
        "name": "Crossfire Gallery",
        "objective": "Collect both relics while avoiding the crossing watcher lanes, then circle back to the exit.",
        "grid": [
            "#########",
            "#E......#",
            "#..>....#",
            "#.....R.#",
            "#.......#",
            "#.R..^..#",
            "#...C...#",
            "#P......#",
            "#########",
        ],
    },
    "switchback_archive": {
        "name": "Switchback Archive",
        "objective": "Follow the switchback route, collect both relics, and exit without entering a watcher lane.",
        "grid": [
            "#########",
            "#E.....##",
            "#..#...R#",
            "#..#.^..#",
            "#..#..C.#",
            "#.R..#..#",
            "#..<.#..#",
            "#P......#",
            "#########",
        ],
    },
}


@dataclass
class Sentry:
    sentry_id: int
    name: str
    x: int
    y: int
    facing: str

    def as_dict(self, threat_tiles: list[tuple[int, int]]) -> dict[str, Any]:
        return {
            "id": self.sentry_id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "facing": self.facing,
            "pattern": "static lane watcher",
            "threat_tiles": [{"x": x, "y": y} for x, y in threat_tiles],
        }


class RuntimeGame:
    width = 1080
    height = 640
    play_width = 660
    grid_size = 9
    cell_size = 64
    board_origin = (24, 32)
    snapshot_dir_name = "runtime_exports"

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self._configure_pygame()
        import pygame

        self.pygame = pygame
        pygame.init()
        pygame.display.set_caption("Build with AI Top-Down Roguelike Puzzle Room")
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.small_font = pygame.font.SysFont("consolas", 14)
        self.snapshot_dir = Path(__file__).resolve().parent / self.snapshot_dir_name

        self.current_room_id = "vault_intro"
        self.room_name = ""
        self.room_objective = ""
        self.turn_count = 0
        self.status = "in_progress"
        self.overlay_note = ""
        self.note_expires_at = 0.0
        self.player_pos = (1, 1)
        self.exit_pos = (1, 1)
        self.walls: set[tuple[int, int]] = set()
        self.cover: set[tuple[int, int]] = set()
        self.relics: list[dict[str, Any]] = []
        self.sentries: list[Sentry] = []
        self.recent_events: list[str] = []
        self.hint_path: list[tuple[int, int]] = []

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((UDP_HOST, UDP_PORT))
        self.socket.setblocking(False)
        self.load_room("vault_intro", announce=False)
        logger.info("Runtime game listening on udp://%s:%s", UDP_HOST, UDP_PORT)
        logger.info("Room loaded: %s. Ask the agent for the next safe route.", self.room_name)

    def _configure_pygame(self) -> None:
        if self.headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    def _default_note(self) -> str:
        if self.status == "victory":
            return "Room cleared. Load another preset or reset the room."
        if self.relics_remaining() > 0:
            return (
                f"Turn-based room. Collect {self.relics_remaining()} relic(s) to unlock the exit."
            )
        return "Turn-based room. Exit is unlocked. Reach the green door."

    def _within_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.grid_size and 0 <= y < self.grid_size

    def _parse_grid(self, grid: list[str]) -> None:
        self.walls.clear()
        self.cover.clear()
        self.relics = []
        self.sentries = []
        sentry_id = 1

        for y, row in enumerate(grid):
            for x, cell in enumerate(row):
                if cell == "#":
                    self.walls.add((x, y))
                elif cell == "C":
                    self.cover.add((x, y))
                elif cell == "P":
                    self.player_pos = (x, y)
                elif cell == "E":
                    self.exit_pos = (x, y)
                elif cell == "R":
                    self.relics.append({"x": x, "y": y, "collected": False})
                elif cell in "^>v<":
                    facing = {
                        "^": "up",
                        ">": "right",
                        "v": "down",
                        "<": "left",
                    }[cell]
                    self.sentries.append(
                        Sentry(
                            sentry_id=sentry_id,
                            name=f"Watcher {sentry_id}",
                            x=x,
                            y=y,
                            facing=facing,
                        )
                    )
                    sentry_id += 1

    def load_room(self, room_id: str, announce: bool = True) -> dict[str, Any]:
        preset = ROOM_PRESETS.get(room_id, ROOM_PRESETS["vault_intro"])
        self.current_room_id = room_id if room_id in ROOM_PRESETS else "vault_intro"
        self.room_name = preset["name"]
        self.room_objective = preset["objective"]
        self.turn_count = 0
        self.status = "in_progress"
        self.hint_path = []
        self.note_expires_at = 0.0
        self._parse_grid(preset["grid"])
        self.overlay_note = self._default_note()
        self.recent_events = [
            f"Room loaded: {self.room_name}. Nothing moves until you or the agent apply a turn."
        ]

        if announce:
            self.add_event(f"Loaded preset {self.current_room_id}.")

        return {
            "room_id": self.current_room_id,
            "state": self.get_state(),
        }

    def reset_room(self) -> dict[str, Any]:
        self.load_room(self.current_room_id, announce=False)
        self.add_event("Room reset.")
        return {"state": self.get_state()}

    def add_event(self, message: str) -> None:
        self.recent_events.insert(0, message)
        del self.recent_events[6:]
        self.overlay_note = message
        self.note_expires_at = time.time() + 5.0
        logger.info("Runtime event: %s", message)

    def relics_remaining(self) -> int:
        return sum(1 for relic in self.relics if not relic["collected"])

    def exit_locked(self) -> bool:
        return self.relics_remaining() > 0

    def sentry_positions(self) -> set[tuple[int, int]]:
        return {(sentry.x, sentry.y) for sentry in self.sentries}

    def sentry_threat_tiles(self, sentry: Sentry) -> list[tuple[int, int]]:
        dx, dy = FACING_DELTAS[sentry.facing]
        x = sentry.x + dx
        y = sentry.y + dy
        threat_tiles: list[tuple[int, int]] = []

        while self._within_bounds(x, y):
            if (x, y) in self.walls or (x, y) in self.cover:
                break
            threat_tiles.append((x, y))
            x += dx
            y += dy

        return threat_tiles

    def all_threat_tiles(self) -> set[tuple[int, int]]:
        tiles: set[tuple[int, int]] = set()
        for sentry in self.sentries:
            tiles.update(self.sentry_threat_tiles(sentry))
        return tiles

    def available_moves(self) -> list[str]:
        moves = []
        for move_name, (dx, dy) in MOVE_DELTAS.items():
            target = (self.player_pos[0] + dx, self.player_pos[1] + dy)
            if self._move_block_reason(target) is None:
                moves.append(move_name)
        return moves

    def _move_block_reason(self, target: tuple[int, int]) -> str | None:
        x, y = target

        if not self._within_bounds(x, y):
            return "That move would leave the board."
        if target in self.walls:
            return "That tile is a wall."
        if target in self.cover:
            return "That tile is blocked by cover."
        if target in self.sentry_positions():
            return "A watcher occupies that tile."
        if target == self.exit_pos and self.exit_locked():
            return "The exit is still locked."
        if target in self.all_threat_tiles():
            return "That tile is under watcher fire."
        return None

    def _collect_relic_if_present(self) -> None:
        for relic in self.relics:
            if not relic["collected"] and (relic["x"], relic["y"]) == self.player_pos:
                relic["collected"] = True
                self.add_event(f"Collected relic shard at ({relic['x']}, {relic['y']}).")
                if self.relics_remaining() == 0:
                    self.add_event("Exit unlocked.")
                break

    def apply_moves(self, moves: list[str]) -> dict[str, Any]:
        normalized_moves = [move.strip().lower() for move in moves if move and move.strip()]
        applied_moves: list[str] = []

        if self.status == "victory":
            self.add_event("Room already cleared. Reset or load another preset.")
            return {"applied_moves": applied_moves, "state": self.get_state()}

        self.hint_path = []

        for move in normalized_moves:
            if move not in MOVE_DELTAS:
                self.add_event(f"Unknown move: {move}.")
                break

            dx, dy = MOVE_DELTAS[move]
            target = (self.player_pos[0] + dx, self.player_pos[1] + dy)
            reason = self._move_block_reason(target)
            if reason is not None:
                self.add_event(reason)
                break

            self.player_pos = target
            self.turn_count += 1
            applied_moves.append(move)
            self._collect_relic_if_present()

            if self.player_pos == self.exit_pos and not self.exit_locked():
                self.status = "victory"
                self.add_event("Room cleared.")
                break

        return {"applied_moves": applied_moves, "state": self.get_state()}

    def preview_plan(self, moves: list[str], label: str = "Suggested plan") -> dict[str, Any]:
        normalized_moves = [move.strip().lower() for move in moves if move and move.strip()]
        preview_positions: list[tuple[int, int]] = []
        x, y = self.player_pos

        for move in normalized_moves:
            if move not in MOVE_DELTAS:
                break
            dx, dy = MOVE_DELTAS[move]
            target = (x + dx, y + dy)
            if self._move_block_reason(target) is not None:
                break
            preview_positions.append(target)
            x, y = target

        self.hint_path = preview_positions
        self.add_event(f"{label}: {len(preview_positions)} safe step(s) highlighted.")
        return {
            "highlighted_steps": len(preview_positions),
            "state": self.get_state(),
        }

    def show_note(self, message: str) -> dict[str, Any]:
        self.add_event(message)
        return {"message": message, "state": self.get_state()}

    def save_snapshot(self, filename: str | None = None) -> dict[str, Any]:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        safe_name = filename or f"{self.current_room_id}_{int(time.time())}.png"
        if not safe_name.endswith(".png"):
            safe_name = f"{safe_name}.png"
        snapshot_path = self.snapshot_dir / safe_name
        self.draw()
        self.pygame.image.save(self.screen, str(snapshot_path))
        self.add_event(f"Saved board snapshot to {snapshot_path.name}.")
        return {"path": str(snapshot_path), "state": self.get_state()}

    def board_ascii(self) -> str:
        threat_tiles = self.all_threat_tiles()
        hint_tiles = set(self.hint_path)
        grid = [["." for _ in range(self.grid_size)] for _ in range(self.grid_size)]

        for x, y in self.walls:
            grid[y][x] = "#"
        for x, y in self.cover:
            grid[y][x] = "C"
        for x, y in threat_tiles:
            if grid[y][x] == ".":
                grid[y][x] = "!"
        for x, y in hint_tiles:
            if grid[y][x] in {".", "!"}:
                grid[y][x] = "*"
        for relic in self.relics:
            if not relic["collected"]:
                grid[relic["y"]][relic["x"]] = "R"
        for sentry in self.sentries:
            grid[sentry.y][sentry.x] = FACING_SYMBOLS[sentry.facing]

        exit_symbol = "E" if not self.exit_locked() else "L"
        grid[self.exit_pos[1]][self.exit_pos[0]] = exit_symbol
        grid[self.player_pos[1]][self.player_pos[0]] = "P"
        return "\n".join("".join(row) for row in grid)

    def get_state(self) -> dict[str, Any]:
        threat_tiles = sorted(self.all_threat_tiles())

        return {
            "room_id": self.current_room_id,
            "room_name": self.room_name,
            "turn_count": self.turn_count,
            "status": self.status,
            "objective": self.room_objective,
            "player": {"x": self.player_pos[0], "y": self.player_pos[1]},
            "exit": {"x": self.exit_pos[0], "y": self.exit_pos[1], "locked": self.exit_locked()},
            "relics": [
                {"x": relic["x"], "y": relic["y"], "collected": relic["collected"]}
                for relic in self.relics
            ],
            "relics_remaining": self.relics_remaining(),
            "walls": [{"x": x, "y": y} for x, y in sorted(self.walls)],
            "cover": [{"x": x, "y": y} for x, y in sorted(self.cover)],
            "sentries": [
                sentry.as_dict(self.sentry_threat_tiles(sentry)) for sentry in self.sentries
            ],
            "threat_tiles": [{"x": x, "y": y} for x, y in threat_tiles],
            "available_moves": self.available_moves(),
            "hint_path": [{"x": x, "y": y} for x, y in self.hint_path],
            "overlay_note": self.overlay_note,
            "recent_events": self.recent_events,
            "board_ascii": self.board_ascii(),
            "turn_model": "turn-based, static watcher lanes, no real-time enemy movement",
            "legend": {
                "player": "blue circle",
                "relic": "gold diamond",
                "exit": "green door",
                "watcher": "red triangle",
                "danger": "red tinted tile",
                "preview": "cyan highlighted tile",
            },
            "snapshot_hint": "Take a screenshot or export a snapshot and ask Gemini to reason about the board visually.",
        }

    def handle_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = payload.get("command")

        if command == "ping":
            return {"ok": True, "reply": "pong", "state": self.get_state()}
        if command == "get_state":
            return {"ok": True, "state": self.get_state()}
        if command == "reset_room":
            return {"ok": True, **self.reset_room()}
        if command == "load_room":
            return {"ok": True, **self.load_room(payload.get("room_id", self.current_room_id))}
        if command == "preview_plan":
            moves = payload.get("moves", [])
            if isinstance(moves, str):
                moves = [moves]
            return {"ok": True, **self.preview_plan(moves, payload.get("label", "Suggested plan"))}
        if command == "apply_moves":
            moves = payload.get("moves", [])
            if isinstance(moves, str):
                moves = [moves]
            return {"ok": True, **self.apply_moves(moves)}
        if command == "show_note":
            return {"ok": True, **self.show_note(payload.get("message", "Runtime note"))}
        if command == "save_snapshot":
            return {"ok": True, **self.save_snapshot(payload.get("filename"))}

        return {"ok": False, "error": f"Unknown command: {command}"}

    def process_udp(self) -> None:
        while True:
            try:
                raw_message, address = self.socket.recvfrom(BUFFER_SIZE)
            except BlockingIOError:
                break

            try:
                payload = json.loads(raw_message.decode("utf-8"))
                response = self.handle_command(payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to process UDP command")
                response = {"ok": False, "error": str(exc)}

            self.socket.sendto(json.dumps(response).encode("utf-8"), address)

    def _grid_rect(self, x: int, y: int) -> tuple[int, int, int, int]:
        origin_x, origin_y = self.board_origin
        return (
            origin_x + x * self.cell_size,
            origin_y + y * self.cell_size,
            self.cell_size,
            self.cell_size,
        )

    def _draw_floor_tile(self, x: int, y: int, rect: tuple[int, int, int, int]) -> None:
        pygame = self.pygame
        tile_surface = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        base_a = (22, 31, 52)
        base_b = (28, 39, 63)
        tint = base_a if (x + y) % 2 == 0 else base_b
        tile_surface.fill((*tint, 255))
        pygame.draw.rect(
            tile_surface, (48, 65, 98, 120), (8, 8, rect[2] - 16, rect[3] - 16), 1, border_radius=10
        )
        pygame.draw.line(tile_surface, (62, 82, 118, 70), (10, rect[3] - 14), (rect[2] - 10, 14), 1)
        self.screen.blit(tile_surface, rect[:2])

    def _draw_wall_tile(self, rect: tuple[int, int, int, int]) -> None:
        pygame = self.pygame
        tile_surface = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(tile_surface, (64, 74, 98), (0, 0, rect[2], rect[3]), border_radius=12)
        pygame.draw.rect(
            tile_surface, (94, 108, 138), (5, 5, rect[2] - 10, rect[3] - 10), border_radius=10
        )
        pygame.draw.rect(
            tile_surface, (42, 52, 74), (9, 9, rect[2] - 18, rect[3] - 18), border_radius=8
        )
        pygame.draw.line(tile_surface, (122, 140, 176), (12, 16), (rect[2] - 14, 16), 2)
        pygame.draw.line(
            tile_surface, (32, 40, 59), (12, rect[3] - 14), (rect[2] - 12, rect[3] - 14), 2
        )
        self.screen.blit(tile_surface, rect[:2])

    def _draw_cover_tile(self, rect: tuple[int, int, int, int]) -> None:
        pygame = self.pygame
        tile_surface = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(tile_surface, (53, 72, 86), (0, 0, rect[2], rect[3]), border_radius=12)
        pygame.draw.circle(tile_surface, (109, 138, 153), (rect[2] // 2, rect[3] // 2), 18)
        pygame.draw.circle(tile_surface, (185, 215, 222), (rect[2] // 2, rect[3] // 2), 18, 2)
        pygame.draw.circle(tile_surface, (76, 100, 114), (rect[2] // 2, rect[3] // 2), 7)
        pygame.draw.line(tile_surface, (205, 225, 232), (18, 46), (46, 18), 2)
        self.screen.blit(tile_surface, rect[:2])

    def _draw_threat_overlay(self, rect: tuple[int, int, int, int], sentries: list[Sentry]) -> None:
        pygame = self.pygame
        overlay = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        overlay.fill((245, 78, 78, 96))
        pygame.draw.rect(
            overlay, (255, 186, 186, 130), (3, 3, rect[2] - 6, rect[3] - 6), 2, border_radius=10
        )
        for stripe_y in range(-rect[3] // 2, rect[3], 14):
            pygame.draw.line(
                overlay, (255, 214, 214, 70), (0, stripe_y), (rect[2], stripe_y + rect[2]), 2
            )
        if sentries:
            arrow = FACING_SYMBOLS[sentries[0].facing].upper()
            label = self.small_font.render(arrow, True, (255, 238, 238))
            overlay.blit(label, (rect[2] - 18, 6))
        self.screen.blit(overlay, rect[:2])

    def _draw_hint_overlay(
        self,
        rect: tuple[int, int, int, int],
        step_number: int | None,
        also_threatened: bool,
    ) -> None:
        pygame = self.pygame
        overlay = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        overlay.fill((71, 199, 255, 68 if also_threatened else 92))
        pygame.draw.rect(
            overlay, (184, 245, 255, 180), (4, 4, rect[2] - 8, rect[3] - 8), 2, border_radius=10
        )
        diamond = [
            (rect[2] // 2, 9),
            (rect[2] - 9, rect[3] // 2),
            (rect[2] // 2, rect[3] - 9),
            (9, rect[3] // 2),
        ]
        pygame.draw.polygon(overlay, (193, 251, 255, 110), diamond)
        if step_number is not None:
            badge_center = (rect[2] - 14, rect[3] - 14)
            pygame.draw.circle(overlay, (11, 26, 40), badge_center, 12)
            pygame.draw.circle(overlay, (193, 251, 255), badge_center, 12, 2)
            step_surface = self.small_font.render(str(step_number), True, (244, 252, 255))
            step_rect = step_surface.get_rect(center=badge_center)
            overlay.blit(step_surface, step_rect)
        self.screen.blit(overlay, rect[:2])

    def _draw_sentry(self, sentry: Sentry) -> None:
        pygame = self.pygame
        rect = self._grid_rect(sentry.x, sentry.y)
        cx = rect[0] + rect[2] // 2
        cy = rect[1] + rect[3] // 2
        pygame.draw.circle(self.screen, (64, 18, 24), (cx, cy + 2), 22)
        pygame.draw.circle(self.screen, (150, 44, 52), (cx, cy), 22)
        pygame.draw.circle(self.screen, (255, 218, 218), (cx, cy), 22, 2)
        points = {
            "up": [(cx, cy - 18), (cx - 16, cy + 12), (cx + 16, cy + 12)],
            "right": [(cx + 18, cy), (cx - 12, cy - 16), (cx - 12, cy + 16)],
            "down": [(cx, cy + 18), (cx - 16, cy - 12), (cx + 16, cy - 12)],
            "left": [(cx - 18, cy), (cx + 12, cy - 16), (cx + 12, cy + 16)],
        }[sentry.facing]
        pygame.draw.polygon(self.screen, (255, 111, 97), points)
        pygame.draw.polygon(self.screen, (255, 222, 218), points, 2)
        pygame.draw.circle(self.screen, (255, 244, 207), (cx, cy), 6)
        pygame.draw.circle(self.screen, (120, 19, 25), (cx, cy), 2)

    def _draw_relic(self, relic: dict[str, Any]) -> None:
        pygame = self.pygame
        rect = self._grid_rect(relic["x"], relic["y"])
        cx = rect[0] + rect[2] // 2
        cy = rect[1] + rect[3] // 2
        glow = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 214, 102, 55), (rect[2] // 2, rect[3] // 2), 24)
        self.screen.blit(glow, rect[:2])
        points = [(cx, cy - 20), (cx + 18, cy), (cx, cy + 20), (cx - 18, cy)]
        pygame.draw.polygon(self.screen, (255, 199, 71), points)
        pygame.draw.polygon(self.screen, (255, 243, 210), points, 2)
        pygame.draw.line(self.screen, (255, 250, 226), (cx, cy - 14), (cx, cy + 14), 2)
        pygame.draw.line(self.screen, (255, 250, 226), (cx - 12, cy), (cx + 12, cy), 2)

    def _draw_exit(self) -> None:
        pygame = self.pygame
        rect = self._grid_rect(*self.exit_pos)
        frame_rect = (rect[0] + 9, rect[1] + 8, rect[2] - 18, rect[3] - 14)
        exit_color = (69, 189, 118) if not self.exit_locked() else (94, 109, 128)
        glow = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(
            glow, (*exit_color, 45), (8, 8, rect[2] - 16, rect[3] - 16), border_radius=12
        )
        self.screen.blit(glow, rect[:2])
        pygame.draw.rect(self.screen, (221, 241, 226), frame_rect, 3, border_radius=10)
        pygame.draw.rect(
            self.screen,
            exit_color,
            (frame_rect[0] + 4, frame_rect[1] + 4, frame_rect[2] - 8, frame_rect[3] - 8),
            border_radius=8,
        )
        glyph = "LOCK" if self.exit_locked() else "EXIT"
        glyph_surface = self.small_font.render(glyph, True, (243, 250, 244))
        glyph_rect = glyph_surface.get_rect(center=(rect[0] + rect[2] // 2, rect[1] + rect[3] // 2))
        self.screen.blit(glyph_surface, glyph_rect)

    def _draw_player(self) -> None:
        pygame = self.pygame
        player_rect = self._grid_rect(*self.player_pos)
        cx = player_rect[0] + player_rect[2] // 2
        cy = player_rect[1] + player_rect[3] // 2
        glow = pygame.Surface((player_rect[2], player_rect[3]), pygame.SRCALPHA)
        pygame.draw.circle(glow, (77, 162, 255, 60), (player_rect[2] // 2, player_rect[3] // 2), 24)
        self.screen.blit(glow, player_rect[:2])
        shadow = [(cx, cy + 18), (cx - 18, cy + 4), (cx, cy - 22), (cx + 18, cy + 4)]
        pygame.draw.polygon(self.screen, (45, 92, 184), shadow)
        pygame.draw.circle(self.screen, (205, 247, 255), (cx, cy - 4), 13)
        pygame.draw.circle(self.screen, (64, 130, 255), (cx, cy - 4), 17, 3)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx - 4, cy - 6), 2)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx + 4, cy - 6), 2)

    def draw(self) -> None:
        pygame = self.pygame
        threat_tiles = self.all_threat_tiles()
        hint_tiles = set(self.hint_path)
        self.screen.fill((8, 11, 19))
        for band in range(0, self.height, 64):
            color = (8, 12, 20) if (band // 64) % 2 == 0 else (11, 16, 28)
            pygame.draw.rect(self.screen, color, (0, band, self.width, 64))
        pygame.draw.rect(self.screen, (15, 24, 39), (0, 0, self.play_width, self.height))
        pygame.draw.rect(
            self.screen,
            (34, 48, 78),
            (18, 24, self.play_width - 36, self.grid_size * self.cell_size + 16),
            3,
            border_radius=18,
        )

        for y in range(self.grid_size):
            for x in range(self.grid_size):
                rect = self._grid_rect(x, y)
                self._draw_floor_tile(x, y, rect)
                if (x, y) in self.walls:
                    self._draw_wall_tile(rect)
                elif (x, y) in self.cover:
                    self._draw_cover_tile(rect)
                if (x, y) in threat_tiles and (x, y) not in self.walls and (x, y) not in self.cover:
                    tile_sentries = [
                        sentry
                        for sentry in self.sentries
                        if (x, y) in self.sentry_threat_tiles(sentry)
                    ]
                    self._draw_threat_overlay(rect, tile_sentries)
                if (x, y) in hint_tiles:
                    step_number = None
                    if (x, y) in self.hint_path:
                        step_number = self.hint_path.index((x, y)) + 1
                    self._draw_hint_overlay(rect, step_number, (x, y) in threat_tiles)
                pygame.draw.rect(self.screen, (40, 54, 84), rect, 1, border_radius=8)

        for relic in self.relics:
            if relic["collected"]:
                continue
            self._draw_relic(relic)

        self._draw_exit()

        for sentry in self.sentries:
            self._draw_sentry(sentry)

        self._draw_player()

        panel_x = self.play_width
        pygame.draw.rect(self.screen, (7, 11, 19), (panel_x, 0, self.width - panel_x, self.height))
        pygame.draw.line(self.screen, (38, 54, 84), (panel_x, 0), (panel_x, self.height), 3)
        lines = [
            "Build with AI Puzzle Room",
            "",
            f"Room: {self.room_name}",
            f"Status: {self.status}",
            f"Relics remaining: {self.relics_remaining()}",
            f"Exit locked: {self.exit_locked()}",
            f"Turns: {self.turn_count}",
            "Mode: turn-based",
            "",
            "Safe moves:",
            ", ".join(self.available_moves()) if self.available_moves() else "none",
            "",
            "Objective:",
            self.room_objective,
            "",
            "Recent events:",
        ]

        y = 22
        for line in lines:
            font = self.font if len(line) <= 42 else self.small_font
            color = (
                (236, 240, 247)
                if line not in {"Objective:", "Recent events:", "Safe moves:"}
                else (152, 208, 255)
            )
            surface = font.render(line, True, color)
            self.screen.blit(surface, (panel_x + 18, y))
            y += 24 if font is self.font else 20

        for event in self.recent_events:
            surface = self.small_font.render(f"- {event}", True, (190, 201, 218))
            self.screen.blit(surface, (panel_x + 20, y))
            y += 20

        y += 8
        controls = [
            "Controls:",
            "WASD move",
            "R reset room",
            "1/2/3 load preset",
            "",
            "Legend:",
            "Blue pawn: player",
            "Gold shard: relic",
            "Green gate: exit",
            "Red eye: watcher",
            "Red lane: danger",
            "Cyan lane: preview",
            "",
            "Optional multimodal:",
            "Take a screenshot now",
            "or export one via MCP",
            "",
            "UDP:",
            f"{UDP_HOST}:{UDP_PORT}",
        ]
        for line in controls:
            surface = self.small_font.render(line, True, (140, 204, 255))
            self.screen.blit(surface, (panel_x + 18, y))
            y += 20

        note_surface = self.small_font.render(self.overlay_note[:54], True, (255, 231, 160))
        self.screen.blit(note_surface, (24, self.height - 24))
        pygame.display.flip()

    def run(self, max_seconds: float | None = None) -> None:
        pygame = self.pygame
        start_time = time.time()
        running = True

        key_to_move = {
            pygame.K_w: "up",
            pygame.K_d: "right",
            pygame.K_s: "down",
            pygame.K_a: "left",
        }

        while running:
            self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key in key_to_move:
                        self.apply_moves([key_to_move[event.key]])
                    elif event.key == pygame.K_r:
                        self.reset_room()
                    elif event.key == pygame.K_1:
                        self.load_room("vault_intro")
                    elif event.key == pygame.K_2:
                        self.load_room("crossfire_gallery")
                    elif event.key == pygame.K_3:
                        self.load_room("switchback_archive")

            self.process_udp()
            self.draw()

            if self.note_expires_at and time.time() > self.note_expires_at:
                self.overlay_note = self._default_note()
                self.note_expires_at = 0.0

            if max_seconds and (time.time() - start_time) >= max_seconds:
                running = False

        pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=None)
    args = parser.parse_args()

    game = RuntimeGame(headless=args.headless)
    game.run(max_seconds=args.max_seconds)


if __name__ == "__main__":
    main()
