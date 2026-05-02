from __future__ import annotations

import asyncio

from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any
import json

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .a2a_cards import public_agent_cards
from .adk_controller import _run_real_adk_turn, run_real_adk_turn, reset_adk_session_cache
from game_agent.agent import workshop_model_profiles
from .simulation import RuntimeSimulator, create_default_simulator


class DriveRequest(BaseModel):
    actor_id: str = "rhea"
    keys: list[str] = []
    camera_yaw_degrees: float = 0.0
    duration_ms: float = 100.0


class InputFrameRequest(BaseModel):
    keys: list[str] = []
    duration_ms: float = 100.0


class InputBufferRequest(BaseModel):
    actor_id: str = "rhea"
    frames: list[InputFrameRequest]
    camera_yaw_degrees: float = 0.0


class ConsoleRequest(BaseModel):
    command: str
    screenshot_data_url: str | None = None


class ScreenshotRequest(BaseModel):
    screenshot_data_url: str


class CameraControlRequest(BaseModel):
    yaw_delta_degrees: float = 0.0
    pitch_delta_degrees: float = 0.0
    zoom_delta: float = 0.0


class SaveMemoryRequest(BaseModel):
    key: str
    value: Any
    source: str = "agent"


class LoadMemoryRequest(BaseModel):
    key: str | None = None


HELP_MESSAGE = """자연어로 요청하면 실제 ADK Agent에게 현재 캔버스 이미지와 게임 state가 전달됩니다.

예시:
- NPC 대화와 주변 환경 단서를 분석해 퀘스트를 완수해봐
- 입력 버퍼를 사용하여 미로를 정밀하게 통과해봐
- 시각 정보로 퍼즐 패턴을 파악해 해결하고 분석 그래프를 보여줘

Agent가 이동할 때는 apply_input_buffer tool이 보낸 WASD/Shift/Space/E 프레임을 화면에서 그대로 재생합니다.
콘솔의 `Gemini tool call`, `입력 재생`, `관찰 반환` 로그가 모델 입출력 흐름입니다."""


def _is_help_command(command: str) -> bool:
    return command.strip().lower() == "/help"


def _help_payload(runtime: RuntimeSimulator) -> dict[str, Any]:
    return {
        "ok": True,
        "message": HELP_MESSAGE,
        "answer": HELP_MESSAGE,
        "trace": {"nodes": [], "edges": []},
        "state": runtime.inspect(),
    }


class CameraStateRequest(BaseModel):
    yaw_degrees: float
    pitch_degrees: float
    distance: float


from fastapi.middleware.cors import CORSMiddleware


def create_app(simulator: RuntimeSimulator | None = None) -> FastAPI:
    runtime = simulator or create_default_simulator()
    app = FastAPI(title="Agentic Game Demo Runtime")

    # Cloud Shell 프록시 및 외부 접근을 위한 CORS 설정
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    web_dir = Path(__file__).resolve().parents[2] / "web"
    next_camera_command_id = 0

    latest_camera_state = {
        "yaw_degrees": 0.0,
        "pitch_degrees": 0.0,
        "distance": 7.2,
    }

    @app.middleware("http")
    async def no_store_static_assets(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    latest_screenshot: str | None = None
    active_websockets: list[WebSocket] = []

    # 온디맨드 스크린샷 처리를 위한 상태 변수
    pending_screenshot_event: asyncio.Event | None = None
    current_screenshot_data: str | None = None

    async def broadcast_state(
        camera_commands_to_send: list[dict[str, Any]] | None = None,
        include_screenshot: bool = False,
        request_screenshot: bool = False,
    ):
        world_inspect = runtime.inspect()
        world_inspect["camera"] = latest_camera_state

        state_data = {
            "ok": True,
            "state": world_inspect,
            "camera_commands": camera_commands_to_send or [],
        }
        if include_screenshot:
            state_data["screenshot"] = latest_screenshot
        if request_screenshot:
            state_data["type"] = "screenshot_request"

        async def send_to_ws(ws: WebSocket):
            try:
                # 0.5초 타임아웃 설정으로 지연 차단
                await asyncio.wait_for(ws.send_json(state_data), timeout=0.5)
            except:
                if ws in active_websockets:
                    active_websockets.remove(ws)

        if active_websockets:
            # 리스트 복사본을 순회하여 순회 중 삭제 안전성 확보
            current_sockets = active_websockets[:]
            await asyncio.gather(
                *(send_to_ws(ws) for ws in current_sockets), return_exceptions=True
            )
        else:
            # 연결된 클라이언트가 없을 때의 디버그 출력
            pass

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        active_websockets.append(websocket)
        try:
            # 첫 연결시에만 스크린샷 포함 전송
            world_inspect = runtime.inspect()
            world_inspect["camera"] = latest_camera_state
            await websocket.send_json(
                {
                    "ok": True,
                    "state": world_inspect,
                    "screenshot": latest_screenshot,
                    "camera_commands": [],
                }
            )
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "drive":
                    # HTTP POST /api/drive와 동일한 로직을 WebSocket 스트림에서 처리
                    runtime.drive_actor(
                        actor_id=data.get("actor_id", "rhea"),
                        keys=data.get("keys", []),
                        camera_yaw_degrees=data.get("camera_yaw_degrees", 0.0),
                        duration_ms=data.get("duration_ms", 100.0),
                    )
                    # 이동 후 즉시 모든 클라이언트에게 상태 브로드캐스트
                    await broadcast_state()

        except WebSocketDisconnect:
            pass
        finally:
            if websocket in active_websockets:
                active_websockets.remove(websocket)

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        world_inspect = runtime.inspect()
        world_inspect["camera"] = latest_camera_state
        return {
            "ok": True,
            "state": world_inspect,
            "screenshot": latest_screenshot,
        }

    @app.post("/api/camera-state")
    async def update_camera_state(request: CameraStateRequest) -> dict[str, Any]:
        nonlocal latest_camera_state
        latest_camera_state = {
            "yaw_degrees": request.yaw_degrees,
            "pitch_degrees": request.pitch_degrees,
            "distance": request.distance,
        }
        return {"ok": True}

    @app.get("/api/capture")
    async def capture() -> dict[str, Any]:
        """에이전트가 호출하는 실시간 스크린샷 요청 엔드포인트"""
        nonlocal pending_screenshot_event, current_screenshot_data

        if not active_websockets:
            return {"ok": False, "error": "연결된 브라우저 클라이언트가 없습니다."}

        pending_screenshot_event = asyncio.Event()
        current_screenshot_data = None

        # 브라우저에게 스크린샷 요청 메시지 전송
        await broadcast_state(request_screenshot=True)

        try:
            # 브라우저가 업로드할 때까지 최대 3초 대기
            await asyncio.wait_for(pending_screenshot_event.wait(), timeout=3.0)
            return {"ok": True, "screenshot": current_screenshot_data}
        except asyncio.TimeoutError:
            return {"ok": False, "error": "스크린샷 요청 시간이 초과되었습니다."}
        finally:
            pending_screenshot_event = None

    @app.get("/api/diagnostics")
    async def diagnostics() -> dict[str, Any]:
        return {
            "ok": True,
            "diagnostics": runtime.diagnose(),
        }

    @app.post("/api/agent-memory/save")
    async def save_agent_memory(request: SaveMemoryRequest) -> dict[str, Any]:
        result = runtime.save_agent_memory(
            key=request.key,
            value=request.value,
            source=request.source,
        ).as_dict()
        await broadcast_state()
        return result

    @app.post("/api/agent-memory/load")
    async def load_agent_memory(request: LoadMemoryRequest) -> dict[str, Any]:
        return runtime.load_agent_memory(key=request.key).as_dict()

    @app.post("/api/agent-memory/clear")
    async def clear_agent_memory() -> dict[str, Any]:
        result = runtime.clear_agent_memory().as_dict()
        await broadcast_state()
        return result

    @app.get("/api/models")
    async def models() -> dict[str, Any]:
        return {"ok": True, "models": workshop_model_profiles()}

    @app.get("/.well-known/agent-card.json")
    async def agent_cards() -> dict[str, Any]:
        return public_agent_cards()

    @app.post("/api/screenshot")
    async def upload_screenshot(request: ScreenshotRequest) -> dict[str, Any]:
        nonlocal latest_screenshot, current_screenshot_data
        latest_screenshot = request.screenshot_data_url

        # 온디맨드 요청 대기 중인 경우 이벤트 해제
        if pending_screenshot_event:
            current_screenshot_data = request.screenshot_data_url
            pending_screenshot_event.set()

        return {"ok": True}

    @app.post("/api/reset")
    async def reset() -> dict[str, Any]:
        nonlocal latest_screenshot
        latest_screenshot = None
        reset_adk_session_cache()
        result = runtime.reset()
        await broadcast_state(include_screenshot=True)
        return {"ok": True, "state": result}

    @app.post("/api/adk-reset")
    async def adk_reset() -> dict[str, Any]:
        reset_adk_session_cache()
        return {"ok": True}

    @app.get("/api/adk-debug")
    async def adk_debug() -> dict[str, Any]:
        import game_agent.agent as agent_module
        from .adk_controller import _cached_runner, _cached_session_id

        return {
            "ok": True,
            "agent_file": agent_module.__file__,
            "cached_runner": _cached_runner is not None,
            "cached_session_id": _cached_session_id,
            "profiles": workshop_model_profiles(),
        }

    @app.post("/api/drive")
    async def drive(request: DriveRequest) -> dict[str, Any]:
        result = runtime.drive_actor(
            actor_id=request.actor_id,
            keys=request.keys,
            camera_yaw_degrees=request.camera_yaw_degrees,
            duration_ms=request.duration_ms,
        ).as_dict()
        await broadcast_state()
        return result

    @app.post("/api/input-buffer")
    async def input_buffer(request: InputBufferRequest) -> dict[str, Any]:
        frames = [frame.model_dump() for frame in request.frames]
        result = runtime.apply_input_buffer(
            request.actor_id,
            frames,
            request.camera_yaw_degrees,
        ).as_dict()
        await broadcast_state()
        return result

    @app.post("/api/camera-control")
    async def camera_control(request: CameraControlRequest) -> dict[str, Any]:
        nonlocal next_camera_command_id
        command = request.model_dump()
        command["id"] = next_camera_command_id
        next_camera_command_id += 1
        await broadcast_state(camera_commands_to_send=[command])
        return {"ok": True}

    @app.post("/api/console")
    def console(request: ConsoleRequest) -> dict[str, Any]:
        nonlocal latest_screenshot
        if request.screenshot_data_url:
            latest_screenshot = request.screenshot_data_url
        if _is_help_command(request.command):
            return _help_payload(runtime)
        return run_real_adk_turn(runtime, request.command, request.screenshot_data_url)

    @app.post("/api/console/stream")
    def console_stream(request: ConsoleRequest) -> StreamingResponse:
        nonlocal latest_screenshot
        if request.screenshot_data_url:
            latest_screenshot = request.screenshot_data_url
        events: Queue[dict[str, Any] | None] = Queue()

        def worker() -> None:
            try:
                result = _run_real_adk_turn(
                    runtime,
                    request.command,
                    request.screenshot_data_url,
                    emit=events.put,
                )
                events.put({"type": "final", "payload": result})
            except Exception as exc:
                events.put({"type": "error", "message": str(exc)})
            finally:
                events.put(None)

        def stream() -> Any:
            events.put(
                {
                    "type": "accepted",
                    "screenshot_attached": bool(request.screenshot_data_url),
                }
            )
            if _is_help_command(request.command):
                events.put({"type": "final", "payload": _help_payload(runtime)})
                events.put(None)
            else:
                Thread(target=worker, daemon=True).start()
            while True:
                event = events.get()
                if event is None:
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/command")
    def command(request: ConsoleRequest) -> dict[str, Any]:
        nonlocal latest_screenshot
        if request.screenshot_data_url:
            latest_screenshot = request.screenshot_data_url
        return run_real_adk_turn(runtime, request.command, request.screenshot_data_url)

    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=web_dir), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    return app


def main() -> None:
    uvicorn.run("engine.game.runtime_api:create_app", factory=True, host="127.0.0.1", port=8787)


if __name__ == "__main__":
    main()
