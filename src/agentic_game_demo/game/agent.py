from __future__ import annotations

from ..agent_setup import build_loop_agent


# ADK discovers this symbol when users run `adk run ./src/agentic_game_demo`.
# The editable workshop code is intentionally in agent_setup.py.
root_agent = build_loop_agent()
