from __future__ import annotations

from agentic_game_demo.game.a2a_cards import build_a2a_task, public_agent_cards


def test_public_agent_cards_include_qa_agent() -> None:
    cards = public_agent_cards("http://local.test")
    names = {agent["name"] for agent in cards["agents"]}

    assert names == {"qa-automation-agent"}
    assert cards["agents"][0]["url"].startswith("http://local.test")


def test_build_a2a_task_explains_delegation_boundary() -> None:
    task = build_a2a_task(
        "qa-automation-agent",
        "observe_and_control_with_input_buffer",
        {"scenario": "market"},
    )

    assert task["target_agent"] == "qa-automation-agent"
    assert "MCP remains the tool layer" in task["teaching_note"]
