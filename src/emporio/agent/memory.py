"""Sessions saved as JSON in sessions/, kept out of git because they hold what customers wrote (D-005, rule 13).

A session keeps the neutral history (emporio.llm.base) and the tools' session state, so a resumed conversation keeps
its failed order lookups and the products already looked up (D-008).
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from emporio.llm.base import Message

SESSIONS_DIR = Path(__file__).resolve().parents[3] / "sessions"
_SESSION_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")


class SessionError(Exception):
    pass


@dataclass
class Session:
    id: str
    provider: str
    model: str
    created_at: str
    messages: list[Message] = field(default_factory=list)
    failed_order_lookups: int = 0
    seen_products: list[int] = field(default_factory=list)


def new_session(provider: str, model: str, now: datetime) -> Session:
    session_id = f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    return Session(session_id, provider, model, now.isoformat(timespec="seconds"))


class SessionStore:
    def __init__(self, directory: Path = SESSIONS_DIR) -> None:
        self.directory = directory

    def save(self, session: Session) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(session.id)
        path.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def load(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise SessionError(f"no saved session {session_id!r} in {self.directory}")
        return Session(**json.loads(path.read_text(encoding="utf-8")))

    def _path(self, session_id: str) -> Path:
        if not _SESSION_ID.fullmatch(session_id):  # also keeps the id from naming a path outside the folder
            raise SessionError(f"invalid session id {session_id!r}")
        return self.directory / f"{session_id}.json"
