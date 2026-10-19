from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path


class SessionError(ValueError):
    """Raised when session state cannot be loaded or saved."""


class SessionStore:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def _ensure_directory(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.cache_dir.chmod(0o700)

    def _atomic_write(self, destination: Path, content: str) -> None:
        self._ensure_directory()
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.cache_dir, delete=False
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            if os.name != "nt":
                temporary_path.chmod(0o600)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def create(self, mapping: dict[str, str]) -> str:
        session_id = uuid.uuid4().hex
        self.save(session_id, mapping)
        self._atomic_write(self.cache_dir / "latest-session", session_id)
        return session_id

    def save(self, session_id: str, mapping: dict[str, str]) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise SessionError(f"Invalid session ID: {session_id}")
        payload = json.dumps({"session_id": session_id, "mapping": mapping}, ensure_ascii=False)
        self._atomic_write(self.cache_dir / f"session_{session_id}.json", payload)

    def load_or_empty(self, session_id: str) -> tuple[str, dict[str, str]]:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise SessionError(f"Invalid session ID: {session_id}")
        if not (self.cache_dir / f"session_{session_id}.json").exists():
            return session_id, {}
        return self.load(session_id)

    def load(self, session_id: str | None = None) -> tuple[str, dict[str, str]]:
        self._ensure_directory()
        if session_id is None:
            try:
                session_id = (self.cache_dir / "latest-session").read_text(encoding="utf-8").strip()
            except OSError as error:
                raise SessionError("No active session; supply --session or run 'scrub' first") from error
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise SessionError(f"Invalid session ID: {session_id}")
        session_path = self.cache_dir / f"session_{session_id}.json"
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            mapping = payload["mapping"]
            if payload["session_id"] != session_id or not isinstance(mapping, dict):
                raise ValueError("invalid session data")
            if any(not isinstance(key, str) or not isinstance(value, str) for key, value in mapping.items()):
                raise ValueError("invalid session mapping")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise SessionError(f"Could not load session {session_id}: {error}") from error
        return session_id, mapping

    def delete(self, session_id: str) -> None:
        session_path = self.cache_dir / f"session_{session_id}.json"
        try:
            session_path.unlink()
        except FileNotFoundError:
            return
        latest_path = self.cache_dir / "latest-session"
        try:
            if latest_path.read_text(encoding="utf-8").strip() == session_id:
                latest_path.unlink()
        except FileNotFoundError:
            pass
