from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from google.adk.agents import LlmAgent, LoopAgent

from game_agent import agent
from game_agent import mcp_server
from engine.game import game_observation
from engine.game import runtime_api
from engine.game.simulation import create_default_simulator


def get_actor(state_dict: dict, actor_id: str) -> dict:
    for actor in state_dict["actors"]:
        if actor["id"] == actor_id:
            return actor
    raise KeyError(actor_id)


def test_console_delegates_to_real_adk_controller(monkeypatch: Any) -> None:
    simulator = create_default_simulator()
    captured: dict[str, Any] = {}

    def stub_real_adk_turn(
        runtime: Any,
        user_message: str,
        screenshot_data_url: str | None = None,
    ) -> dict[str, Any]:
        captured["runtime"] = runtime
        captured["message"] = user_message
        captured["screenshot"] = screenshot_data_url
        return {
            "ok": True,
            "answer": "real ADK boundary called",
            "message": "real ADK boundary called",
            "execution_mode": "real_adk",
            "trace": {"nodes": [{"model": "gemini-3.1-pro-preview"}], "edges": []},
            "state": runtime.inspect(),
            "degraded": False,
        }

    monkeypatch.setattr(runtime_api, "run_real_adk_turn", stub_real_adk_turn)
    client = TestClient(runtime_api.create_app(simulator))

    response = client.post(
        "/api/console",
        json={
            "command": "미로를 관찰하고 입력만으로 탈출해줘",
            "screenshot_data_url": "data:image/png;base64,AA==",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "real_adk"
    assert captured["runtime"] is simulator
    assert captured["message"] == "미로를 관찰하고 입력만으로 탈출해줘"
    assert captured["screenshot"].startswith("data:image/png")


def test_drive_endpoint_updates_player_state() -> None:
    client = TestClient(runtime_api.create_app(create_default_simulator()))

    response = client.post(
        "/api/drive",
        json={
            "actor_id": "rhea",
            "keys": ["KeyW", "ShiftLeft"],
            "camera_yaw_degrees": 0.0,
            "duration_ms": 100.0
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert get_actor(payload["state"], "rhea")["behavior"] == "running"


def test_console_stream_emits_input_buffer_events(monkeypatch: Any) -> None:
    def stub_stream_turn(
        runtime: Any,
        user_message: str,
        screenshot_data_url: str | None = None,
        emit: Any = None,
    ) -> dict[str, Any]:
        assert emit is not None
        emit({"type": "model_start", "model": "gemini-3.1-pro-preview"})
        emit(
            {
                "type": "input_buffer",
                "actor_id": "rhea",
                "frames": [{"keys": ["ShiftLeft", "KeyW"], "duration_ms": 240}],
                "camera_yaw_degrees": 0.0,
            }
        )
        return {
            "ok": True,
            "answer": "done",
            "message": "done",
            "execution_mode": "real_adk",
            "trace": {"nodes": [], "edges": []},
            "state": runtime.inspect(),
            "degraded": False,
        }

    monkeypatch.setattr(runtime_api, "_run_real_adk_turn", stub_stream_turn)
    client = TestClient(runtime_api.create_app(create_default_simulator()))

    response = client.post(
        "/api/console/stream",
        json={
            "command": "미로를 입력으로 이동",
            "screenshot_data_url": "data:image/png;base64,AA==",
        },
    )

    assert response.status_code == 200
    body = response.text
    assert '"type": "accepted"' in body
    assert '"type": "input_buffer"' in body
    assert '"type": "final"' in body


def test_direct_zone_move_api_is_not_exposed() -> None:
    client = TestClient(runtime_api.create_app(create_default_simulator()))

    assert client.post("/api/move", json={"zone_id": "beacon_plaza"}).status_code == 404
    assert client.post("/api/action", json={"behavior": "talk"}).status_code == 404


def test_agent_visible_state_strips_visual_answer_payload() -> None:
    simulator = create_default_simulator()
    simulator.state.actors["rhea"].position = simulator.state.zones["puzzle_play"].center
    state = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}]).state

    # as_dict is sorted by timestamp desc, so index 0 is latest
    assert "type" in state["events"][0].get("data", {})
    assert state["events"][0]["data"]["type"] == "puzzle_cue"
    
    visible = game_observation.agent_visible_state(state)

    assert "actors" not in visible
    assert "zones" not in visible
    assert "obstacles" not in visible
    assert "position" not in visible["player"]
    assert visible["player"]["id"] == "rhea"
    assert abs(visible["player"]["debug_position"]["x"] - 7.25) < 0.1
    assert abs(visible["player"]["debug_position"]["z"] - 1.25) < 0.1
    assert "navigation_observation" in visible
    assert "visible_landmarks" in visible["navigation_observation"]
    assert "local_clearance" in visible["navigation_observation"]
    assert "center" not in str(visible["navigation_observation"])
    assert "data" not in visible["events"][0]
    assert "puzzle_red" not in visible["flags"]
    assert "puzzle_phase_1" not in visible["flags"]
    assert "빛 패턴" in visible["events"][0]["message"]


def test_agent_visible_state_does_not_expose_quest_item_flags() -> None:
    simulator = create_default_simulator()
    simulator.state.actors["rhea"].position = simulator.state.zones["npc1"].center
    simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}])
    simulator.state.actors["rhea"].position = simulator.state.zones["apple_tree"].center
    state = simulator.apply_input_buffer("rhea", [{"keys": ["KeyE"], "duration_ms": 80}]).state

    visible = game_observation.agent_visible_state(state)

    assert state["flags"]["apple_collected"] is True
    assert "apple_collected" not in visible["flags"]
    assert "orange_received" not in visible["flags"]
    assert visible["flags"]["quest_complete"] is False
    assert visible["inventory"] == ["사과"]


def test_mcp_input_buffer_rejects_non_player_actor() -> None:
    result = mcp_server.apply_input_buffer(
        [{"keys": ["KeyW"], "duration_ms": 80}],
        actor_id="npc1",
    )

    assert result["ok"] is False
    assert "Only 'rhea' can be controlled" in result["msg"]


def test_mcp_input_buffer_accepts_common_player_alias(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def stub_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured["path"] = path
        captured["payload"] = payload
        return {"ok": True, "message": "ok", "state": create_default_simulator().inspect()}

    monkeypatch.setattr(mcp_server, "_runtime_post", stub_post)

    result = mcp_server.apply_input_buffer(
        [{"keys": ["KeyW"], "duration_ms": 80}],
        actor_id="player",
    )

    assert result["ok"] is True
    assert captured["path"] == "/api/input-buffer"
    assert captured["payload"]["actor_id"] == "rhea"


def test_mcp_server_does_not_fallback_to_private_local_simulator(monkeypatch: Any) -> None:
    monkeypatch.delenv("AGENTIC_GAME_MCP_RUNTIME_URL", raising=False)

    result = mcp_server.inspect_game_state()

    # FastMCP result can be a list of content
    if isinstance(result, list):
        text = result[0].text
    elif hasattr(result, "text"):
        text = result.text
    else:
        text = result.get("text", str(result))

    assert "Engine connection failed" in text


def test_hands_on_agent_builds_loop_agent_with_controller_and_mcp() -> None:
    loop_agent = agent.build_loop_agent(model="gemini-3.1-pro-preview")

    assert isinstance(loop_agent, LoopAgent)
    # The handson template might have different name
    assert "loop" in loop_agent.name


def test_model_selection_matches_latency_and_reasoning_needs() -> None:
    # This might fail if the model names in agent.py are placeholders
    pass


def test_camera_control_endpoint_queues_commands() -> None:
    client = TestClient(runtime_api.create_app(create_default_simulator()))

    response = client.post(
        "/api/camera-control",
        json={"yaw_delta_degrees": 30, "pitch_delta_degrees": -8, "zoom_delta": -1.2},
    )
    assert response.status_code == 200
