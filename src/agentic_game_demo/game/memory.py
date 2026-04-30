from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import time


@dataclass(frozen=True)
class MemoryRecord:
    kind: str
    summary: str
    payload: dict[str, object]
    created_at: float

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "payload": self.payload,
            "created_at": self.created_at,
        }


class JsonlMemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, kind: str, summary: str, payload: dict[str, object]) -> MemoryRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = MemoryRecord(kind=kind, summary=summary, payload=payload, created_at=time())
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")
        return record

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        if not self.path.exists():
            return []
        needle = query.casefold()
        records: list[MemoryRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)
            haystack = f"{data['kind']} {data['summary']} {data['payload']}".casefold()
            if needle in haystack:
                records.append(
                    MemoryRecord(
                        kind=str(data["kind"]),
                        summary=str(data["summary"]),
                        payload=dict(data["payload"]),
                        created_at=float(data["created_at"]),
                    )
                )
        return records[-limit:]
