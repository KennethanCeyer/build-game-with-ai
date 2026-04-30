from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentModelProfile:
    agent_name: str
    model: str
    role: str

    def as_dict(self) -> dict[str, str]:
        return {"agent_name": self.agent_name, "model": self.model, "role": self.role}


DIRECTOR_MODEL = AgentModelProfile(
    agent_name="director",
    model="gemini-3-flash-preview",
    role="Fast workshop-facing planner and tool caller.",
)
QA_MODEL = AgentModelProfile(
    agent_name="qa_automation",
    model="gemini-3.1-pro-preview",
    role="Careful multi-step QA reasoning over state, screenshots, and expected outcomes.",
)
VISION_MODEL = AgentModelProfile(
    agent_name="vision_verifier",
    model="gemini-3.1-flash-lite-preview",
    role="Fast screenshot confirmation for capture-heavy hands-on steps.",
)


def workshop_model_profiles() -> list[dict[str, str]]:
    return [
        DIRECTOR_MODEL.as_dict(),
        QA_MODEL.as_dict(),
        VISION_MODEL.as_dict(),
    ]
