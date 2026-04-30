from __future__ import annotations

from pathlib import Path

from google import genai
from google.genai import types

from .logging_utils import get_logger
from .settings import apply_environment, load_settings


logger = get_logger("indie_game_agent.vision")
DEFAULT_VISUAL_PROMPT = (
    "You are reviewing a small top-down roguelike puzzle room for an indie game workshop. "
    "Use this legend: blue circle = player, gold diamond = relic, green rounded square = exit, "
    "red triangle = watcher, red tinted tiles = danger lane, cyan tinted tiles = suggested path. "
    "Identify what is visible, mention uncertainty when the image is ambiguous, and say whether "
    "the next few moves look safe. Keep the answer short and concrete."
)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def resolve_snapshot_path(snapshot_path: str) -> Path:
    candidate = Path(snapshot_path)

    if candidate.is_absolute():
        return candidate

    root = _root_dir()
    direct = (root / candidate).resolve()
    if direct.exists():
        return direct

    exports_path = (_package_dir() / "runtime_exports" / candidate.name).resolve()
    if exports_path.exists():
        return exports_path

    return direct


def analyze_snapshot(
    snapshot_path: str,
    prompt: str | None = None,
    model: str = "gemini-3.1-flash-lite-preview",
) -> dict:
    settings = load_settings()
    apply_environment(settings)

    image_path = resolve_snapshot_path(snapshot_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {image_path}")

    client = genai.Client(api_key=settings.google_api_key)
    visual_prompt = prompt or DEFAULT_VISUAL_PROMPT
    response = client.models.generate_content(
        model=model,
        contents=[
            visual_prompt,
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png"),
        ],
    )

    logger.info("Visual analysis completed for %s", image_path.name)
    return {
        "snapshot_path": str(image_path),
        "model": model,
        "prompt": visual_prompt,
        "analysis": (response.text or "").strip(),
    }
