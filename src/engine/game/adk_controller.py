from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.sessions import InMemorySessionService

from .adk_trace import (
    answer_from_tool_events,
    normalize_model_frames,
    summarize_tool_response,
    trace_from_adk_events,
)
from game_agent.agent import (
    build_loop_agent,
    build_user_content,
    workshop_model_profiles,
)
from .simulation import RuntimeSimulator


def run_real_adk_turn(
    runtime: RuntimeSimulator,
    user_message: str,
    screenshot_data_url: str | None = None,
) -> dict[str, Any]:
    return _run_real_adk_turn(runtime, user_message, screenshot_data_url)


def visible_tool_plan(call_name: str, call_args: dict[str, Any]) -> str:
    """도구 호출 의도를 사용자에게 친숙한 텍스트로 변환합니다."""
    if call_name == "transfer_to_agent":
        return f"🔄 [{call_args.get('agent_name', '하위 에이전트')}]에게 작업을 인계합니다."
    if call_name.endswith("inspect_game_state"):
        return "🔍 [관측자] 현재 위치, 목표, 주변 이동 가능 경로를 구조화된 데이터로 확인합니다."
    if call_name.endswith("capture_visual_observation"):
        return f"📸 [관측자] 추가 시각 정보가 필요하여 화면을 캡처합니다. (사유: {call_args.get('reason', 'N/A')})"
    if call_name.endswith("capture_visual_crop"):
        return f"🔎 [관측자] 특정 영역({call_args.get('x')},{call_args.get('y')})을 정밀하게 확대 관측합니다."
    if call_name.endswith("diagnose_engine_state"):
        return "🛠️ [관측자] 엔진 플래그와 진행 상태를 심층 검증합니다."
    if call_name.endswith("load_memory"):
        return "📚 [전략가] 이전 경로와 실패 기록을 작업 기억에서 불러옵니다."
    if call_name.endswith("save_memory"):
        return f"📝 [전략가] 현재 판단과 경로 정보를 기록합니다. ({call_args.get('key', 'info')})"
    if call_name.endswith("apply_input_buffer"):
        frames = call_args.get("frames", [])
        return f"🎮 [행동가] 입력 버퍼 {len(frames)}개 프레임을 실행하여 캐릭터를 움직입니다."
    return f"⚙️ [에이전트] {call_name} 도구를 호출합니다."


def summarize_observation_response(response: Any) -> str:
    """관측 결과를 요약하여 UI에 표시합니다."""
    if not isinstance(response, dict):
        return str(response)[:100]
    
    if response.get("budget_exhausted"):
        return f"⚠️ {response.get('message', '예산 소진')}"
        
    summary = response.get("summary", {}) # inspect_game_state에서 summary를 넣어주는 경우
    nav = response.get("navigation_observation", {})
    
    # inspect_game_state 반환 구조 대응
    player = response.get("player", {})
    pos = player.get("debug_position") if player else summary.get("pos", "unknown")
    goals = response.get("goals", [])
    
    return (
        f"✅ 관측 완료: 위치={pos}, 목표={goals}, "
        f"통로={nav.get('maze_corridors', 'N/A')}, "
        f"근거리={nav.get('local_clearance', 'N/A')}"
    )


def _run_real_adk_turn(
    runtime: RuntimeSimulator,
    user_message: str,
    screenshot_data_url: str | None = None,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """실제 브라우저 런타임에 대해 ADK 루프를 한 번 실행합니다."""

    _ensure_google_api_key()

    model = "gemini-3.1-pro-preview"
    tool_events: list[dict[str, Any]] = []
    if emit is not None:
        emit(
            {
                "type": "model_start",
                "model": model,
                "agent_name": "agent_collaboration_system",
                "role": "에이전트 협업 시스템 (자율 루프)",
                "screenshot_attached": bool(screenshot_data_url),
            }
        )

    # 안전 장치 (Safety Fuses)
    tool_call_counts: dict[tuple[str, str], int] = {}
    total_tool_calls = 0
    MAX_TOTAL_TOOL_CALLS = 50
    
    # 에이전트/도구별 엄격한 예산 설정
    MAX_TOOL_CALLS_BY_AGENT = {
        ("state_observer_agent", "inspect_game_state"): 3,
        ("visual_observer_agent", "inspect_game_state"): 3,
        ("visual_observer_agent", "capture_visual_observation"): 3,
        ("visual_observer_agent", "capture_visual_crop"): 3,
        ("actor_agent", "apply_input_buffer"): 3,
        ("actor_agent", "save_memory"): 3,
        ("state_actor_agent", "apply_input_buffer"): 3,
        ("state_actor_agent", "save_memory"): 3,
        ("visual_actor_agent", "apply_input_buffer"): 2,
        ("visual_actor_agent", "save_memory"): 2,
    }

    # 개발 중 세션 오염 방지를 위해 fresh_session=True 사용
    runner, session_id = _build_runner(model, fresh_session=True)
    content = build_user_content(user_message, screenshot_data_url)
    final_text = ""
    raw_events: list[dict[str, Any]] = []
    current_agent = "agent_collaboration_system"
    sub_agent_profiles = {p["agent_name"]: p for p in workshop_model_profiles()}
    last_tool_args_by_name: dict[str, dict[str, Any]] = {}

    try:
        for event in runner.run(
            user_id="browser",
            session_id=session_id,
            new_message=content,
        ):
            event_dump = event.model_dump(mode="json", exclude_none=True)
            raw_events.append(event_dump)
            
            # 1. author 기반 에이전트 전환 감지
            author = event_dump.get("author")
            if author and author != current_agent and emit is not None:
                current_agent = author
                profile = sub_agent_profiles.get(author, {
                    "agent_name": author,
                    "model": model,
                    "role": "delegated worker",
                })
                emit({
                    "type": "agent_switch",
                    "agent_name": profile["agent_name"],
                    "model": profile.get("model", model),
                    "role": profile.get("role", "")
                })

            # 모델의 가시적 텍스트 출력
            if event.content and event.content.parts:
                chunk_text = "".join(part.text or "" for part in event.content.parts).strip()
                if chunk_text and emit is not None:
                    emit({"type": "agent_thought", "text": chunk_text})

            for call in event.get_function_calls():
                call_name = call.name or ""
                call_args = dict(call.args or {})
                last_tool_args_by_name[call_name] = call_args

                # 안전 장치 체크 (Safety Fuses)
                total_tool_calls += 1
                key = (current_agent, call_name)
                tool_call_counts[key] = tool_call_counts.get(key, 0) + 1

                if total_tool_calls > MAX_TOTAL_TOOL_CALLS:
                    raise RuntimeError(f"과도한 도구 호출({total_tool_calls}회)로 실행을 중단했습니다.")
                
                # 에이전트/도구별 예산 체크
                limit = MAX_TOOL_CALLS_BY_AGENT.get((current_agent, call_name))
                if limit is not None and tool_call_counts[key] > limit:
                    raise RuntimeError(
                        f"[{current_agent}]이 {call_name}을 반복 호출({tool_call_counts[key]}회)하여 중단했습니다. "
                        f"이 단계의 도구 예산({limit}회)을 초과했습니다."
                    )
                
                # 2. 도구 호출 의도 시각화
                if emit is not None:
                    emit({"type": "agent_thought", "text": visible_tool_plan(call_name, call_args)})

                # 3. transfer_to_agent 명시적 처리
                if call_name == "transfer_to_agent" and emit is not None:
                    target = str(call_args.get("agent_name", "하위 에이전트"))
                    emit({
                        "type": "agent_switch",
                        "agent_name": target,
                        "model": model,
                        "role": "delegated agent"
                    })

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
                    "args": last_tool_args_by_name.get(response.name, {}),
                    "response": response.response,
                }
                tool_events.append(response_event)
                if emit is not None:
                    # 관측 결과인 경우 상세 요약 표시
                    display_resp = response.response
                    if response.name.endswith("inspect_game_state"):
                        display_resp = summarize_observation_response(response.response)
                    else:
                        display_resp = summarize_tool_response(response.response)

                    emit(
                        {
                            "type": "tool_response",
                            "name": response.name,
                            "args": last_tool_args_by_name.get(response.name, {}),
                            "response": display_resp,
                        }
                    )
            if event.is_final_response() and event.content:
                final_text = "".join(part.text or "" for part in event.content.parts or []).strip()
    except Exception as exc:
        final_text = f"❌ 실행 오류: {str(exc)}"


    state = runtime.inspect()
    
    # 4. 최종 응답 보존 로직 (무조건 덮어쓰지 않음)
    tool_summary = answer_from_tool_events(tool_events)
    if not final_text:
        final_text = tool_summary

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
        "agent_name": "agent_collaboration_system",
    }
    if emit is not None:
        emit({"type": "final_text", "answer": final_text, "degraded": degraded})
    return result


# ADK 서비스 인스턴스를 공유하여 대화 세션 및 MCP 서버 유지
_session_service = InMemorySessionService()
_cached_runner: Runner | None = None
_cached_session_id: str | None = None


def reset_adk_session_cache() -> None:
    """ADK 러너와 세션 캐시를 초기화하여 다음 실행 시 새로운 세션을 시작하게 합니다."""
    global _cached_runner, _cached_session_id
    _cached_runner = None
    _cached_session_id = None


def _build_runner(model: str, fresh_session: bool = False) -> tuple[Runner, str]:
    """ADK Runner 인스턴스를 생성하거나 캐시된 인스턴스를 반환합니다."""
    global _cached_runner, _cached_session_id
    
    if not fresh_session and _cached_runner is not None and _cached_session_id is not None:
        return _cached_runner, _cached_session_id

    import game_agent.agent as agent_module
    print(f"[ADK DEBUG] Building runner. agent.py = {agent_module.__file__}")
    print(f"[ADK DEBUG] Observer tools = {getattr(agent_module, 'OBSERVER_TOOLS', [])}")

    agent = build_loop_agent(model=model)
    app_name = "game_playtest_app"
    
    app = App(
        name=app_name,
        root_agent=agent,
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=3,
            overlap_size=1
        ),
        context_cache_config=ContextCacheConfig(
            min_tokens=2048,
            ttl_seconds=600,
            cache_intervals=5
        )
    )
    
    session = _session_service.create_session_sync(
        app_name=app_name,
        user_id="browser"
    )
    
    runner = Runner(
        app=app,
        session_service=_session_service
    )
    
    if not fresh_session:
        _cached_runner = runner
        _cached_session_id = session.id
        print(f"[ADK DEBUG] Cached runner and session_id: {session.id}")
    
    return runner, session.id


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
