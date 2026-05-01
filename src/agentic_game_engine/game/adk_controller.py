from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from .adk_trace import (
    answer_from_tool_events,
    normalize_model_frames,
    summarize_tool_response,
    trace_from_adk_events,
)
from agentic_game_demo.agent import (
    build_loop_agent,
    build_user_content,
    select_model_profile,
    validate_agent_answer,
)
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
    """실제 브라우저 런타임에 대해 ADK 루프를 한 번 실행합니다.

    이 파일은 웹 서버 경계 로직만을 담당합니다: 모델 선택, Gemini용 데이터 구성,
    ADK 러너 실행, 그리고 브라우저로 전송할 이벤트 스트림을 관리합니다.
    실제 에이전트 구성과 MCP 코드는 agent_setup.py에 위치합니다.
    """

    _ensure_google_api_key()

    model_profile = select_model_profile(user_message, screenshot_data_url)
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
    content = build_user_content(user_message, screenshot_data_url)
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
    final_text = validate_agent_answer(
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
        "GOOGLE_API_KEY가 필요합니다. "
        "워크스페이스 루트의 .env 파일에 GOOGLE_API_KEY=... 형식으로 입력해 주세요."
    )
