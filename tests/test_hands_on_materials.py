from __future__ import annotations

from pathlib import Path


# Root is 1 level up from tests/
ROOT = Path(__file__).resolve().parents[1]


def test_handson_agent_setup_exists_and_is_learner_focused() -> None:
    path = ROOT / "handson/agentic_game_demo/agent_setup.py"
    assert path.exists()
    text = path.read_text(encoding="utf-8")

    assert "TODO:" in text
    assert "build_controller_agent" in text
    assert "build_mcp_toolset" in text
    assert "CONTROLLER_INSTRUCTION" in text
    assert "LoopAgent" in text
    assert "McpToolset" in text
