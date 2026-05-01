from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from game_agent.agent import STRATEGY_AGENT


@dataclass(frozen=True)
class AgentCapability:
    name: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


@dataclass(frozen=True)
class DemoAgentCard:
    name: str
    description: str
    model: str
    url: str
    capabilities: list[AgentCapability]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "url": self.url,
            "capabilities": [capability.as_dict() for capability in self.capabilities],
        }


def qa_agent_card(base_url: str = "http://127.0.0.1:8787") -> dict[str, Any]:
    return DemoAgentCard(
        name="qa-automation-agent",
        description=(
            "Runs game QA by observing state and sending the same input buffer available "
            "to a player. It does not teleport actors or mutate flags directly."
        ),
        model=STRATEGY_AGENT.model,
        url=f"{base_url}/a2a/qa",
        capabilities=[
            AgentCapability(
                "observe_and_control_with_input_buffer",
                "Inspect the live scene and decide Shift+WASD, Space, and E inputs turn by turn.",
            ),
            AgentCapability("summarize_failures", "Explain failed game-state or vision checks."),
        ],
    ).as_dict()


def public_agent_cards(base_url: str = "http://127.0.0.1:8787") -> dict[str, Any]:
    return {
        "agents": [
            qa_agent_card(base_url),
        ]
    }


def build_a2a_task(target_agent: str, task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_agent": target_agent,
        "task_name": task_name,
        "payload": payload,
        "teaching_note": "A2A is used here for agent-to-agent delegation; MCP remains the tool layer.",
    }
