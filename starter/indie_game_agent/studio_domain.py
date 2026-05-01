from __future__ import annotations

from collections import deque
from math import ceil
from typing import Any, Literal

from pydantic import BaseModel


ROLE_LIBRARY = {
    "chaser": {
        "speed": 160,
        "hp": 3,
        "threat": "pins the player in motion",
        "cue": "bright face and pointed silhouette",
    },
    "turret": {
        "speed": 70,
        "hp": 4,
        "threat": "locks space with ranged fire",
        "cue": "anchored body and pre-shot flash",
    },
    "support": {
        "speed": 110,
        "hp": 2,
        "threat": "amplifies nearby enemies",
        "cue": "aura ring and soft idle pose",
    },
    "bruiser": {
        "speed": 95,
        "hp": 6,
        "threat": "slow but punishing contact damage",
        "cue": "large shadow and slow windup",
    },
}

FOCUS_ROLE_ORDER = {
    "melee": ["chaser", "bruiser", "support", "chaser"],
    "ranged": ["turret", "support", "chaser", "turret"],
    "mix": ["chaser", "turret", "support", "bruiser"],
}

DIFFICULTY_MULTIPLIERS = {
    "easy": 0.82,
    "normal": 1.0,
    "hard": 1.24,
}

DISCIPLINE_KEYWORDS = {
    "design": ["boring", "unfair", "confusing", "balance", "difficulty", "wave", "enemy", "boss"],
    "engineering": ["crash", "bug", "stuck", "freeze", "save", "load", "lag", "spawn"],
    "ui": ["hud", "menu", "tooltip", "button", "read", "font", "map", "objective"],
    "art": ["sprite", "animation", "silhouette", "background", "effect", "vfx", "color"],
    "audio": ["music", "sound", "sfx", "volume", "mix", "footstep"],
    "qa": ["repro", "edge case", "inconsistent", "sometimes"],
}

SEVERITY_KEYWORDS = {
    "critical": ["crash", "save", "load", "freeze", "blocked", "softlock"],
    "high": ["unfair", "broken", "stuck", "can't", "cannot", "invisible", "missing"],
    "medium": ["confusing", "too hard", "too easy", "boring", "annoying", "slow"],
    "low": ["nice to have", "polish", "flavor", "minor", "small"],
}

SEVERITY_SCORE = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


class Milestone(BaseModel):
    week: int
    focus: str
    exit_criteria: list[str]


class EnemyArchetype(BaseModel):
    name: str
    role: str
    move_speed: int
    max_hp: int
    threat: str
    readability_cue: str


class PlaytestIssue(BaseModel):
    note: str
    discipline: str
    severity: str
    bucket: str
    owner_hint: str
    action: str


class BacklogTask(BaseModel):
    title: str
    discipline: str
    estimate_days: int
    outcome: str


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def _detect_discipline(note: str) -> str:
    lowered = note.lower()
    scores = {discipline: 0 for discipline in DISCIPLINE_KEYWORDS}

    for discipline, keywords in DISCIPLINE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                scores[discipline] += 1

    discipline, score = max(scores.items(), key=lambda item: item[1])
    return discipline if score > 0 else "design"


def _detect_severity(note: str) -> str:
    lowered = note.lower()

    for severity in ("critical", "high", "medium", "low"):
        for keyword in SEVERITY_KEYWORDS[severity]:
            if keyword in lowered:
                return severity

    return "medium"


def _bucket_for_issue(severity: str, release_days: int) -> str:
    score = SEVERITY_SCORE[severity]

    if score >= 4:
        return "now"
    if score >= 3 and release_days <= 30:
        return "now"
    if score >= 2 and release_days <= 21:
        return "next"
    if score >= 2:
        return "next"
    return "later"


def _owner_hint(discipline: str) -> str:
    return {
        "design": "combat or systems owner",
        "engineering": "gameplay engineer",
        "ui": "ui owner",
        "art": "art generalist",
        "audio": "audio owner",
        "qa": "qa sweep owner",
    }[discipline]


def _action_hint(discipline: str, note: str) -> str:
    short_note = note.strip().rstrip(".")
    return {
        "design": f"Re-tune the rule behind: {short_note}.",
        "engineering": f"Reproduce and patch the failure behind: {short_note}.",
        "ui": f"Improve readability and feedback for: {short_note}.",
        "art": f"Adjust presentation and readability for: {short_note}.",
        "audio": f"Retune audio timing or mix for: {short_note}.",
        "qa": f"Write a stable repro case for: {short_note}.",
    }[discipline]


def plan_vertical_slice_payload(
    game_name: str,
    fantasy: str,
    core_loop: str,
    scope_weeks: int = 8,
    team_size: int = 2,
) -> dict:
    scope_weeks = _clamp(scope_weeks, 4, 16)
    team_size = _clamp(team_size, 1, 6)

    cut_count = 4 if team_size <= 2 else 3
    milestones = [
        Milestone(
            week=1,
            focus="lock pillars and input feel",
            exit_criteria=["one room playable", "one enemy placeholder", "one reward loop"],
        ),
        Milestone(
            week=max(2, scope_weeks // 3),
            focus="make combat readable",
            exit_criteria=["three enemy verbs", "clear hit feedback", "basic fail state"],
        ),
        Milestone(
            week=max(3, (scope_weeks * 2) // 3),
            focus="connect progression",
            exit_criteria=["one build choice", "one pickup economy", "one short session loop"],
        ),
        Milestone(
            week=scope_weeks,
            focus="ship the slice",
            exit_criteria=[
                "playtest notes triaged",
                "performance checked",
                "store capture or deck ready",
            ],
        ),
    ]

    return {
        "game_name": game_name,
        "fantasy": fantasy,
        "core_loop": core_loop,
        "team_size": team_size,
        "scope_weeks": scope_weeks,
        "pillars": [
            f"Readable {fantasy} combat at a glance",
            "One run should create a clear before/after power curve",
            "Every room should force one movement decision and one damage decision",
        ],
        "must_have_features": [
            "one room or micro-map that can be replayed quickly",
            "one player attack and one defensive choice",
            "three enemy archetypes with distinct silhouettes",
            "one reward or upgrade between fights",
            "one restart loop that gets the player back into action fast",
        ],
        "safe_cuts": [
            "meta progression outside the run",
            "narrative framing scenes",
            "multiple biomes or tilesets",
            "full boss fight phase changes",
        ][:cut_count],
        "milestones": [milestone.model_dump(mode="json") for milestone in milestones],
    }


def design_enemy_roster_payload(
    theme: str,
    combat_focus: Literal["melee", "ranged", "mix"] = "mix",
    roster_size: int = 3,
) -> dict:
    roster_size = _clamp(roster_size, 2, 5)
    order = FOCUS_ROLE_ORDER[combat_focus]
    roster = []

    for index in range(roster_size):
        role = order[index]
        base = ROLE_LIBRARY[role]
        variant = EnemyArchetype(
            name=f"{theme.title()} {role.title()} {index + 1}",
            role=role,
            move_speed=base["speed"] + index * 6,
            max_hp=base["hp"] + (1 if role == "bruiser" and index > 0 else 0),
            threat=base["threat"],
            readability_cue=base["cue"],
        )
        roster.append(variant.model_dump(mode="json"))

    return {
        "theme": theme,
        "combat_focus": combat_focus,
        "roster": roster,
        "encounter_pattern": "Open with pressure, then add one support or space-control enemy once the player is moving confidently.",
    }


def balance_combat_wave_payload(
    player_dps: float,
    player_hp: int,
    target_duration_sec: int = 40,
    difficulty: Literal["easy", "normal", "hard"] = "normal",
) -> dict:
    multiplier = DIFFICULTY_MULTIPLIERS[difficulty]
    target_enemy_hp_budget = max(int(player_dps * target_duration_sec * 0.14 * multiplier), 12)
    baseline_enemy_hp = max(int(round((4.4 + player_hp * 0.45) * multiplier)), 3)
    enemy_count = max(ceil(target_enemy_hp_budget / baseline_enemy_hp), 3)
    spawn_interval_sec = round(
        max(0.7, min(2.8, target_duration_sec / max(enemy_count * 1.45, 1))), 2
    )
    elite_count = 1 if difficulty != "easy" and enemy_count >= 10 else 0

    return {
        "difficulty": difficulty,
        "recommended_wave": {
            "enemy_count": enemy_count,
            "hp_per_enemy": baseline_enemy_hp,
            "spawn_interval_sec": spawn_interval_sec,
            "elite_count": elite_count,
            "estimated_total_hp_budget": target_enemy_hp_budget,
        },
        "tuning_notes": [
            "Increase spawn interval before lowering enemy HP if the wave feels unfair.",
            "Increase count before HP if the wave feels empty.",
            "Use one elite to create a memorable spike instead of raising every stat at once.",
        ],
    }


def triage_playtest_notes_payload(notes: list[str], release_days: int = 30) -> dict:
    cleaned_notes = [note.strip() for note in notes if note.strip()]
    issues = []

    for note in cleaned_notes:
        discipline = _detect_discipline(note)
        severity = _detect_severity(note)
        bucket = _bucket_for_issue(severity, release_days)
        issue = PlaytestIssue(
            note=note,
            discipline=discipline,
            severity=severity,
            bucket=bucket,
            owner_hint=_owner_hint(discipline),
            action=_action_hint(discipline, note),
        )
        issues.append(issue)

    issues.sort(key=lambda issue: (-SEVERITY_SCORE[issue.severity], issue.bucket, issue.discipline))

    return {
        "release_days": release_days,
        "issue_count": len(issues),
        "fix_now": [issue.model_dump(mode="json") for issue in issues if issue.bucket == "now"],
        "fix_next": [issue.model_dump(mode="json") for issue in issues if issue.bucket == "next"],
        "defer": [issue.model_dump(mode="json") for issue in issues if issue.bucket == "later"],
    }


def draft_feature_backlog_payload(
    feature_name: str,
    design_goal: str,
    sprint_days: int = 10,
) -> dict:
    sprint_days = _clamp(sprint_days, 5, 20)
    tasks = [
        BacklogTask(
            title=f"Define the player-facing rule for {feature_name}",
            discipline="design",
            estimate_days=1,
            outcome="short ruleset and fail conditions",
        ),
        BacklogTask(
            title=f"Implement the gameplay spine for {feature_name}",
            discipline="engineering",
            estimate_days=max(2, sprint_days // 4),
            outcome="working mechanic in playable build",
        ),
        BacklogTask(
            title=f"Create readable visuals for {feature_name}",
            discipline="art",
            estimate_days=max(1, sprint_days // 5),
            outcome="final silhouette or placeholder set",
        ),
        BacklogTask(
            title=f"Add HUD or feedback hooks for {feature_name}",
            discipline="ui",
            estimate_days=1,
            outcome="player can read the state quickly",
        ),
        BacklogTask(
            title=f"Add supporting SFX for {feature_name}",
            discipline="audio",
            estimate_days=1,
            outcome="one-shot and loop cues in place",
        ),
        BacklogTask(
            title=f"Write the test pass for {feature_name}",
            discipline="qa",
            estimate_days=1,
            outcome="repro cases and acceptance checklist",
        ),
    ]

    return {
        "feature_name": feature_name,
        "design_goal": design_goal,
        "sprint_days": sprint_days,
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "critical_path": [
            "design rule is stable",
            "engineering implementation is playable",
            "ui feedback is readable",
            "qa pass is clean enough for playtest",
        ],
    }


def build_launch_checklist_payload(
    platforms: list[str],
    demo_available: bool = True,
    localization_count: int = 1,
) -> dict:
    normalized_platforms = [platform.strip() for platform in platforms if platform.strip()]
    build_track = [f"final smoke test on {platform}" for platform in normalized_platforms]
    store_track = [f"store assets prepared for {platform}" for platform in normalized_platforms]

    checklist = {
        "build": build_track + ["crash reporting verified", "save compatibility checked"],
        "qa": [
            "one full clean-room run",
            "one regression pass on known issues",
            "controller and keyboard sanity pass",
        ],
        "store": store_track,
        "marketing": [
            "trailer capture list ready",
            "patch notes draft ready",
            "announcement copy reviewed",
        ],
        "localization": [f"{localization_count} language set reviewed for truncation and overflow"],
    }

    if demo_available:
        checklist["marketing"].append("demo-to-full-game messaging reviewed")

    return {
        "platforms": normalized_platforms,
        "demo_available": demo_available,
        "localization_count": localization_count,
        "checklist": checklist,
    }


def _entries_to_coords(
    entries: list[dict[str, Any]], include_collected: bool = True
) -> set[tuple[int, int]]:
    coords = set()
    for entry in entries:
        if not include_collected and entry.get("collected", False):
            continue
        coords.add((int(entry["x"]), int(entry["y"])))
    return coords


def _neighbors(x: int, y: int) -> list[tuple[str, tuple[int, int]]]:
    return [
        ("up", (x, y - 1)),
        ("right", (x + 1, y)),
        ("down", (x, y + 1)),
        ("left", (x - 1, y)),
    ]


def _bfs_path(
    width: int,
    height: int,
    start: tuple[int, int],
    goals: set[tuple[int, int]],
    blocked: set[tuple[int, int]],
    unsafe: set[tuple[int, int]],
    exit_pos: tuple[int, int],
    exit_locked: bool,
) -> list[tuple[int, int]] | None:
    queue = deque([start])
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while queue:
        current = queue.popleft()
        if current in goals:
            path = [current]
            while parents[path[-1]] is not None:
                path.append(parents[path[-1]])
            path.reverse()
            return path

        cx, cy = current
        for _, candidate in _neighbors(cx, cy):
            nx, ny = candidate
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if candidate in parents:
                continue
            if candidate in blocked:
                continue
            if exit_locked and candidate == exit_pos and candidate not in goals:
                continue
            if candidate in unsafe:
                continue
            parents[candidate] = current
            queue.append(candidate)

    return None


def _path_to_moves(path: list[tuple[int, int]]) -> list[str]:
    moves: list[str] = []
    for current, nxt in zip(path, path[1:]):
        dx = nxt[0] - current[0]
        dy = nxt[1] - current[1]
        for move_name, (mx, my) in {
            "up": (0, -1),
            "right": (1, 0),
            "down": (0, 1),
            "left": (-1, 0),
        }.items():
            if (dx, dy) == (mx, my):
                moves.append(move_name)
                break
    return moves


def suggest_safe_route_payload(state: dict[str, Any], step_limit: int = 4) -> dict:
    width = 9
    height = 9
    player = state["player"]
    start = (int(player["x"]), int(player["y"]))
    exit_pos = (int(state["exit"]["x"]), int(state["exit"]["y"]))
    relic_targets = _entries_to_coords(state["relics"], include_collected=False)
    blocked = (
        _entries_to_coords(state["walls"])
        | _entries_to_coords(state["cover"])
        | {(int(sentry["x"]), int(sentry["y"])) for sentry in state["sentries"]}
    )
    unsafe = _entries_to_coords(state["threat_tiles"])

    preview_limit = max(1, min(step_limit, 8))
    current = start
    remaining_relics = set(relic_targets)
    full_path = [start]
    waypoints: list[str] = []

    while remaining_relics:
        path = _bfs_path(
            width, height, current, remaining_relics, blocked, unsafe, exit_pos, exit_locked=True
        )
        if path is None:
            return {
                "status": "no_safe_route",
                "room_name": state["room_name"],
                "objective": state["objective"],
                "recommended_moves": [],
                "preview_path": [],
                "explanation": [
                    "No safe route to the remaining relics was found with the current watcher lanes.",
                    "Load another preset or change the room before asking for another plan.",
                ],
            }
        target = path[-1]
        full_path.extend(path[1:])
        current = target
        remaining_relics.remove(target)
        waypoints.append(f"Collect relic at {target}.")

    path_to_exit = _bfs_path(
        width, height, current, {exit_pos}, blocked, unsafe, exit_pos, exit_locked=False
    )
    if path_to_exit is None:
        return {
            "status": "no_safe_route",
            "room_name": state["room_name"],
            "objective": state["objective"],
            "recommended_moves": [],
            "preview_path": [],
            "explanation": [
                "The relic route is clear, but there is no safe route from the last relic to the exit.",
                "Try another preset or review the watcher lanes visually.",
            ],
        }

    full_path.extend(path_to_exit[1:])
    full_moves = _path_to_moves(full_path)
    preview_moves = full_moves[:preview_limit]
    preview_path = full_path[1 : 1 + len(preview_moves)]

    explanation = [
        "The route avoids watcher fire and blocked tiles.",
        "It collects all remaining relics before stepping onto the exit.",
    ]
    if state.get("snapshot_hint"):
        explanation.append(
            "Because the room is static, you can also verify the route from a screenshot."
        )

    return {
        "status": "route_found",
        "room_id": state["room_id"],
        "room_name": state["room_name"],
        "objective": state["objective"],
        "turn_count": state["turn_count"],
        "recommended_moves": preview_moves,
        "full_move_count": len(full_moves),
        "remaining_move_count": max(len(full_moves) - len(preview_moves), 0),
        "preview_path": [{"x": x, "y": y} for x, y in preview_path],
        "waypoints": waypoints + [f"Reach exit at {exit_pos}."],
        "explanation": explanation,
    }


def topdown_roguelike_pillars() -> str:
    return "\n".join(
        [
            "1. A room should stay readable from a single screenshot.",
            "2. Threat lanes should be stable long enough for the player or the model to plan.",
            "3. Each room should teach one tactical idea, not five at once.",
            "4. Unlocking the exit after relic pickup is clearer than hidden fail states.",
        ]
    )


def topdown_combat_rules() -> str:
    return topdown_roguelike_pillars()


def indie_scope_heuristics() -> str:
    return "\n".join(
        [
            "1. A vertical slice should prove feel, clarity, and one progression loop.",
            "2. Cut content variety before cutting readability or restart speed.",
            "3. One memorable elite is cheaper than making every enemy complex.",
            "4. Triage playtest notes by release risk, not by who reported them first.",
        ]
    )
