from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_solution_agent_setup_is_complete_and_adk_focused() -> None:
    text = (ROOT / "solution/agentic_game_demo/agent_setup.py").read_text(encoding="utf-8")

    assert "..." not in text
    assert "LoopAgent(" in text
    assert "LlmAgent(" in text
    assert "McpToolset(" in text
    assert "exit_loop" in text
    assert "apply_input_buffer only" in text
    assert "teleport" in text.lower()


def test_starter_agent_setup_only_blanks_simple_agent_wiring() -> None:
    text = (ROOT / "starter/agentic_game_demo/agent_setup.py").read_text(encoding="utf-8")

    assert "TODO(starter-1)" in text
    assert "TODO(starter-5)" in text
    assert "..." in text
    assert "CONTROLLER_INSTRUCTION" in text
    assert "apply_input_buffer only" in text
    assert "LoopAgent" in text
    assert "McpToolset" in text
