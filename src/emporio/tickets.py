"""Support tickets (complaints and hand-offs), appended to a local JSONL file kept out of git (decision D-006).

Tickets hold what customers wrote, so the folder is in .gitignore (D-005, rule 13).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

TICKETS_PATH = Path(__file__).resolve().parents[2] / "tickets" / "tickets.jsonl"


class TicketLog:
    def __init__(self, path: Path = TICKETS_PATH) -> None:
        self.path = path

    def open(self, kind: str, created_at: datetime, **fields: str) -> str:
        """Append a ticket and return its id, for example EMP-20260323-0001 (the number runs across days)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ticket_id = f"EMP-{created_at:%Y%m%d}-{self._count() + 1:04d}"
        record = {"id": ticket_id, "kind": kind, "created_at": created_at.isoformat(timespec="seconds"), **fields}
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return ticket_id

    def read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]

    def _count(self) -> int:
        return len(self.read())
