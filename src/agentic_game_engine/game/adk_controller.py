from __future__ import annotations

import base64
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .adk_trace import (
    answer_from_tool_events,
    normalize_model_frames,
    summarize_tool_response,
    trace_from_adk_events,
)
from agentic_game_demo.agent_setup import build_loop_agent
from .model_config import DIRECTOR_MODEL, QA_MODEL, VISION_MODEL, AgentModelProfile
from .simulation import RuntimeSimulator


def run_real_adk_turn(
    runtime: RuntimeSimulator,
    user_message: str,
    screenshot_data_url: str | None = None,
) -> dict[str, Any]:
    return _run_real_adk_turn(runtime, user_message, screenshot_data_url)


def _run_real_adk_turn(
    runtime: RuntimeSimulator,
    user_message: str,
    screenshot_data_url: str | None = None,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one real ADK turn against the live browser runtime.

    This file intentionally owns only the web-server boundary:
    model selection, Gemini content construction, ADK runner execution, and
    streamed browser events. The hands-on Agent/MCP code lives in
    agent_setup.py.
    """

    _ensure_google_api_key()

    model_profile = _select_model_profile(user_message, screenshot_data_url)
    model = model_profile.model
    tool_events: list[dict[str, Any]] = []
    if emit is not None:
        emit(
            {
                "type": "model_start",
                "model": model,
                "agent_name": model_profile.agent_name,
                "role": model_profile.role,
                "screenshot_attached": bool(screenshot_data_url),
            }
        )

    runner, session_id = _build_runner(model)
    content = _build_user_content(user_message, screenshot_data_url)
    final_text = ""
    raw_events: list[dict[str, Any]] = []
    for event in runner.run(
        user_id="browser",
        session_id=session_id,
        new_message=content,
    ):
        event_dump = event.model_dump(mode="json", exclude_none=True)
        raw_events.append(event_dump)
        for call in event.get_function_calls():
            call_name = call.name or ""
            call_args = dict(call.args or {})
            tool_event = {
                "type": "tool_call",
                "name": call_name,
                "args": call_args,
            }
            tool_events.append(tool_event)
            if emit is not None:
                emit(tool_event)
                if call_name.endswith("apply_input_buffer"):
                    normalized_frames = normalize_model_frames(call_args.get("frames", []))
                    emit(
                        {
                            "type": "input_buffer",
                            "actor_id": "rhea",
                            "frames": normalized_frames,
                            "camera_yaw_degrees": float(call_args.get("camera_yaw_degrees", 0.0)),
                        }
                    )
        for response in event.get_function_responses():
            response_event = {
                "type": "tool_response",
                "name": response.name,
                "response": response.response,
            }
            tool_events.append(response_event)
            if emit is not None:
                emit(
                    {
                        "type": "tool_response",
                        "name": response.name,
                        "response": summarize_tool_response(response.response),
                    }
                )
        if event.is_final_response() and event.content:
            final_text = "".join(part.text or "" for part in event.content.parts or []).strip()

    state = runtime.inspect()
    final_text = _validated_answer(
        user_message,
        final_text or answer_from_tool_events(tool_events),
        state,
    )
    degraded = final_text.startswith("ADK 모델이 입력 버퍼를 시도했지만")
    result = {
        "ok": True,
        "message": final_text,
        "answer": final_text,
        "trace": trace_from_adk_events(
            model,
            user_message,
            screenshot_data_url,
            tool_events,
            raw_events,
        ),
        "state": state,
        "degraded": degraded,
        "execution_mode": "real_adk",
        "model": model,
        "agent_name": model_profile.agent_name,
    }
    if emit is not None:
        emit({"type": "final_text", "answer": final_text, "degraded": degraded})
    return result


def _build_runner(model: str) -> tuple[Runner, str]:
    app_name = "agentic_game_engine"
    user_id = "browser"
    session_id = f"turn-{uuid4()}"
    session_service = InMemorySessionService()
    session_service.create_session_sync(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    return (
        Runner(
            app_name=app_name,
            agent=build_loop_agent(model=model),
            session_service=session_service,
        ),
        session_id,
    )


def _select_model(user_message: str, screenshot_data_url: str | None) -> str:
    return _select_model_profile(user_message, screenshot_data_url).model


def _select_model_profile(
    user_message: str,
    screenshot_data_url: str | None,
) -> AgentModelProfile:
    lowered = user_message.lower()
    realtime_tokens = [
        "준실시간",
        "빠르게",
        "빨리",
        "가볍",
        "간단",
        "상태",
        "status",
        "보고",
        "관찰",
    ]
    pro_tokens = [
        "전체",
        "계획",
        "복잡",
        "추론",
        "호출 그래프",
        "trace",
        "트레이스",
        "긴",
        "깊게",
        "분석",
        "리포트",
        "검증 보고서",
        "end-to-end",
    ]
    if any(token in lowered for token in pro_tokens):
        return QA_MODEL
    solve_tokens = [
        "풀",
        "탈출",
        "완료",
        "진행",
        "퀘스트",
        "quest",
        "npc",
        "퍼즐",
        "puzzle",
        "미로",
    ]
    if any(token in lowered for token in solve_tokens):
        return DIRECTOR_MODEL
    if screenshot_data_url and any(
        token in lowered for token in realtime_tokens + ["화면", "캡쳐", "관찰"]
    ):
        return VISION_MODEL
    return DIRECTOR_MODEL


def _build_user_content(user_message: str, screenshot_data_url: str | None) -> types.Content:
    parts: list[types.Part] = [types.Part(text=user_message)]
    image_bytes = _decode_data_url(screenshot_data_url)
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
    return types.Content(role="user", parts=parts)


def _decode_data_url(data_url: str | None) -> bytes | None:
    if not data_url or "," not in data_url:
        return None
    _, encoded = data_url.split(",", 1)
    try:
        return base64.b64decode(encoded)
    except ValueError:
        return None


def _validated_answer(user_message: str, answer: str, state: dict[str, Any]) -> str:
    lowered = user_message.lower()
    flags = state["flags"]
    required: list[str] = []
    if "퍼즐" in lowered or "puzzle" in lowered:
        required.append("puzzle_solved")
    if "미로" in lowered or "maze" in lowered or "탈출" in lowered:
        required.append("maze_escaped")
    if "검증" in lowered:
        required.extend(["quest_complete", "maze_escaped", "puzzle_solved"])
    if (
        "퀘스트" in lowered
        or "quest" in lowered
        or "npc" in lowered
        or "오렌지" in lowered
        or "사과" in lowered
    ):
        required.append("quest_complete")
    if not required:
        return answer
    missing = [flag for flag in required if not flags.get(flag, False)]
    if not missing:
        return answer
    return (
        "ADK 모델이 입력 버퍼를 시도했지만 최종 상태 검증은 아직 실패입니다. "
        f"미완료 플래그: {', '.join(missing)}. "
        "이 응답은 모델의 주장보다 런타임 state를 우선합니다. "
        "Trace에서 실제 apply_input_buffer 호출과 결과를 확인하세요."
    )


def _ensure_google_api_key() -> None:
    if os.getenv("GOOGLE_API_KEY"):
        return
    root = Path(__file__).resolve().parents[3]
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("GOOGLE_API_KEY="):
                continue
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                os.environ["GOOGLE_API_KEY"] = value
                return
    raise RuntimeError(
        "GOOGLE_API_KEY is required. Put it in the workspace root .env file as GOOGLE_API_KEY=..."
    )
