from __future__ import annotations

from engine.game.simulation import create_default_simulator

def test_agent_memory_save_and_load() -> None:
    simulator = create_default_simulator()
    
    # 메모리 저장 테스트
    save_result = simulator.save_agent_memory(key="strategy", value="maze_navigation", source="navigator")
    assert save_result["ok"] is True
    assert save_result["key"] == "strategy"
    
    # 단일 키 로드 테스트
    load_result = simulator.load_agent_memory(key="strategy")
    assert load_result["value"] == "maze_navigation"
    assert load_result["source"] == "navigator"
    assert "timestamp" in load_result
    
    # 전체 메모리 로드 테스트
    all_memory = simulator.load_agent_memory()
    assert "strategy" in all_memory
    assert all_memory["strategy"]["value"] == "maze_navigation"

def test_agent_memory_persistence_in_state() -> None:
    simulator = create_default_simulator()
    simulator.save_agent_memory(key="found_npc", value="Mira")
    
    state = simulator.inspect()
    assert "agent_memory" in state
    assert "found_npc" in state["agent_memory"]
    assert state["agent_memory"]["found_npc"]["value"] == "Mira"

def test_load_non_existent_key() -> None:
    simulator = create_default_simulator()
    load_result = simulator.load_agent_memory(key="missing_key")
    assert load_result["ok"] is False
    assert "not found" in load_result["msg"]
