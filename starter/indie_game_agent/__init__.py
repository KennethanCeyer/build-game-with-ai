from __future__ import annotations

import json
from typing import Any

from google.adk.events.event import Event


def _sanitize_surrogates(value: Any) -> Any:
    if isinstance(value, str):
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    if isinstance(value, list):
        return [_sanitize_surrogates(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_surrogates(item) for item in value)
    if isinstance(value, set):
        return {_sanitize_surrogates(item) for item in value}
    if isinstance(value, dict):
        return {
            _sanitize_surrogates(key): _sanitize_surrogates(item) for key, item in value.items()
        }
    return value


def _patch_event_json_serialization() -> None:
    if getattr(Event, "_indie_game_agent_surrogate_patch", False):
        return

    original_model_dump_json = Event.model_dump_json

    def safe_model_dump_json(self: Event, *args: Any, **kwargs: Any) -> str:
        try:
            return original_model_dump_json(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            if "surrogates not allowed" not in repr(exc):
                raise

            payload = self.model_dump(
                include=kwargs.get("include"),
                exclude=kwargs.get("exclude"),
                context=kwargs.get("context"),
                by_alias=kwargs.get("by_alias"),
                exclude_unset=kwargs.get("exclude_unset", False),
                exclude_defaults=kwargs.get("exclude_defaults", False),
                exclude_none=kwargs.get("exclude_none", False),
                exclude_computed_fields=kwargs.get("exclude_computed_fields", False),
                round_trip=kwargs.get("round_trip", False),
                warnings=kwargs.get("warnings", True),
                fallback=kwargs.get("fallback"),
                serialize_as_any=kwargs.get("serialize_as_any", False),
            )
            safe_payload = _sanitize_surrogates(payload)
            return json.dumps(
                safe_payload,
                ensure_ascii=kwargs.get("ensure_ascii", False),
                indent=kwargs.get("indent"),
                separators=(",", ":") if kwargs.get("indent") is None else None,
            )

    Event.model_dump_json = safe_model_dump_json
    Event._indie_game_agent_surrogate_patch = True


_patch_event_json_serialization()


def __getattr__(name: str):
    if name == "root_agent":
        from .agent import root_agent

        return root_agent
    raise AttributeError(name)
