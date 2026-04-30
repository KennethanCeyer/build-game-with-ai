from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any
import json

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .a2a_cards import public_agent_cards
from .adk_controller import _run_real_adk_turn, run_real_adk_turn
from .contracts import Gait
from .model_config import workshop_model_profiles
from .simulation import RuntimeSimulator, create_default_simulator


class DriveRequest(BaseModel):
    actor_id: str = "rhea"
    x: float
    z: float
    facing_degrees: float
    gait: Gait = Gait.WALK
    jumping: bool = False
    moving: bool = True


class InputFrameRequest(BaseModel):
    keys: list[str] = []
    duration_ms: int = 100


class InputBufferRequest(BaseModel):
    actor_id: str = "rhea"
    frames: list[InputFrameRequest]
    camera_yaw_degrees: float = 0.0


class ConsoleRequest(BaseModel):
    command: str
    screenshot_data_url: str | None = None


class CameraControlRequest(BaseModel):
    yaw_delta_degrees: float = 0.0
    pitch_delta_degrees: float = 0.0
    zoom_delta: float = 0.0


HELP_MESSAGE = """자연어로 요청하면 실제 ADK Agent에게 현재 캔버스 이미지와 게임 state가 전달됩니다.

예시:
- NPC 퀘스트를 대화와 화면 단서만 보고 입력 버퍼로 완료해봐
- 미로를 입력만으로 탈출해봐
- 퍼즐을 화면 단서 기반으로 풀고 호출 그래프를 보여줘

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


def create_app(simulator: RuntimeSimulator | None = None) -> FastAPI:
    runtime = simulator or create_default_simulator()
    app = FastAPI(title="Agentic Game Demo Runtime")
    web_dir = Path(__file__).resolve().parents[2] / "web"
    camera_commands: list[dict[str, Any]] = []
    next_camera_command_id = 0

    @app.middleware("http")
    async def no_store_static_assets(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return {"ok": True, "state": runtime.inspect()}

    @app.get("/api/models")
    def models() -> dict[str, Any]:
        return {"ok": True, "models": workshop_model_profiles()}

    @app.get("/.well-known/agent-card.json")
    def agent_cards() -> dict[str, Any]:
        return public_agent_cards()

    @app.post("/api/reset")
    def reset() -> dict[str, Any]:
        return {"ok": True, "state": runtime.reset()}

    @app.post("/api/drive")
    def drive(request: DriveRequest) -> dict[str, Any]:
        return runtime.drive_actor(
            request.actor_id,
            request.x,
            request.z,
            request.facing_degrees,
            request.gait,
            request.jumping,
            request.moving,
        ).as_dict()

    @app.post("/api/input-buffer")
    def input_buffer(request: InputBufferRequest) -> dict[str, Any]:
        frames = [frame.model_dump() for frame in request.frames]
        return runtime.apply_input_buffer(
            request.actor_id,
            frames,
            request.camera_yaw_degrees,
        ).as_dict()

    @app.post("/api/camera-control")
    def camera_control(request: CameraControlRequest) -> dict[str, Any]:
        nonlocal next_camera_command_id
        next_camera_command_id += 1
        command = {
            "id": next_camera_command_id,
            "yaw_delta_degrees": request.yaw_delta_degrees,
            "pitch_delta_degrees": request.pitch_delta_degrees,
            "zoom_delta": request.zoom_delta,
        }
        camera_commands.append(command)
        del camera_commands[:-30]
        return {
            "ok": True,
            "message": "카메라 입력을 브라우저 세션에 전달했습니다.",
            "command": command,
        }

    @app.get("/api/camera-commands")
    def camera_command_feed(after: int = 0) -> dict[str, Any]:
        return {
            "ok": True,
            "commands": [command for command in camera_commands if command["id"] > after],
        }

    @app.post("/api/console")
    def console(request: ConsoleRequest) -> dict[str, Any]:
        if _is_help_command(request.command):
            return _help_payload(runtime)
        return run_real_adk_turn(runtime, request.command, request.screenshot_data_url)

    @app.post("/api/console/stream")
    def console_stream(request: ConsoleRequest) -> StreamingResponse:
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
        return run_real_adk_turn(runtime, request.command, request.screenshot_data_url)

    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=web_dir), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    return app


def main() -> None:
    uvicorn.run(
        "agentic_game_demo.runtime_api:create_app", factory=True, host="127.0.0.1", port=8787
    )


if __name__ == "__main__":
    main()
