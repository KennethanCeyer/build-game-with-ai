from __future__ import annotations

from pathlib import Path

from engine.game.memory import JsonlMemoryStore


def test_memory_store_searches_records(tmp_path: Path) -> None:
    store = JsonlMemoryStore(tmp_path / "memory.jsonl")
    store.add("quest", "NPC quest completed through dialogue", {"flag": "quest_complete"})
    store.add("quest", "Dialogue clue mentioned apple trade", {"npc": "토마"})

    results = store.search("apple")

    assert len(results) == 1
    assert results[0].kind == "quest"
