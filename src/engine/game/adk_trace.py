from __future__ import annotations

from typing import Any


def trace_from_adk_events(
    model: str,
    user_message: str,
    screenshot_data_url: str | None,
    tool_events: list[dict[str, Any]],
    raw_events: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "model_1",
            "type": "model",
            "title": "Real ADK model turn",
            "model": model,
            "input_summary": (
                f"user={user_message[:120]!r}; screenshot={'attached' if screenshot_data_url else 'none'}"
            ),
            "output_summary": f"ADK emitted {len(raw_events)} events and {len(tool_events)} tool event records.",
            "payload": {"execution_mode": "real_adk"},
        }
    ]
    edges: list[dict[str, str]] = []
    previous = "model_1"
    for index, tool_event in enumerate(tool_events, start=2):
        node_id = f"tool_{index}"
        nodes.append(
            {
                "id": node_id,
                "type": "tool",
                "title": f"{tool_event['type']}: {tool_event.get('name', 'unknown')}",
                "model": None,
                "input_summary": _compact_json(tool_event.get("args")),
                "output_summary": _compact_json(tool_event.get("response")),
                "payload": tool_event,
            }
        )
        edges.append({"from": previous, "to": node_id})
        previous = node_id
    return {"nodes": nodes, "edges": edges}


def summarize_tool_response(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    value = unwrap_tool_response(value)
    state = value.get("state")
    if not isinstance(state, dict):
        return value
    flags = state.get("flags", {})
    return {
        "ok": value.get("ok", True),
        "message": value.get("message", ""),
        "degraded": value.get("degraded", False),
        "player": state.get("player", {}),
        "navigation_observation": state.get("navigation_observation", {}),
        "flags": flags,
        "goals": state.get("goals", []),
        "last_events": state.get("events", [])[-3:],
    }


def answer_from_tool_events(tool_events: list[dict[str, Any]]) -> str:
    for event in reversed(tool_events):
        if event.get("type") != "tool_response":
            continue
        response = event.get("response")
        if not isinstance(response, dict):
            continue
        response = unwrap_tool_response(response)
        state = response.get("state")
        if not isinstance(state, dict):
            continue
        player = state.get("player", {})
        flags = state.get("flags", {})
        goals = state.get("goals", [])
        events = state.get("events", [])
        nearby = None
        if isinstance(player, dict):
            nearby_data = player.get("nearby_interaction")
            if isinstance(nearby_data, dict):
                nearby = nearby_data.get("name")
        recent_message = ""
        if isinstance(events, list) and events:
            last_event = events[-1]
            if isinstance(last_event, dict):
                recent_message = str(last_event.get("message", ""))
        return (
            "현재 런타임 관찰을 기준으로 정리하면, "
            f"목표 상태는 {goals}, 완료 플래그는 {flags}입니다. "
            f"가까운 상호작용 대상은 {nearby or '없고'}, "
            f"최근 이벤트는 {recent_message or '아직 없습니다'}."
        )
    return "요청은 처리했지만 콘솔에 요약할 수 있는 도구 결과가 아직 없습니다."


def normalize_model_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    allowed = {"KeyW", "KeyA", "KeyS", "KeyD", "ShiftLeft", "ShiftRight", "Space", "KeyE"}
    mapping = {
        "W": "KeyW",
        "A": "KeyA",
        "S": "KeyS",
        "D": "KeyD",
        "E": "KeyE",
        "Shift": "ShiftLeft",
        "w": "KeyW",
        "a": "KeyA",
        "s": "KeyS",
        "d": "KeyD",
        "e": "KeyE",
    }
    for frame in frames:
        keys = frame.get("keys")
        if not keys and isinstance(frame.get("keyboard_state"), dict):
            keys = [key for key, pressed in frame["keyboard_state"].items() if pressed is True]
        if not keys:
            keys = [k for k in (list(mapping.keys()) + list(allowed)) if frame.get(k) is True]

        raw_keys = [str(k) for k in keys or []]
        normalized_keys: list[str] = []
        for k in raw_keys:
            if k in allowed:
                normalized_keys.append(k)
            elif k in mapping:
                normalized_keys.append(mapping[k])

        raw_duration = int(frame.get("duration_ms", frame.get("duration", 120)))
        max_duration = 650 if normalized_keys else 180
        duration_ms = max(60, min(max_duration, raw_duration))
        normalized.append({"keys": list(set(normalized_keys)), "duration_ms": duration_ms})
    return normalized


def unwrap_tool_response(response: dict[str, Any]) -> dict[str, Any]:
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return response


def _compact_json(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text if len(text) <= 260 else text[:257] + "..."
