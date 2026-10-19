from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any
from collections.abc import Iterator

from .anonymizer import scrub
from .config import load_config
from .sessions import SessionStore


def _session_key(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"llm-shield could not anonymize this file: {reason}",
        }
    }


@contextmanager
def _session_lock(cache_dir: Path, session_key: str) -> Iterator[None]:
    lock_dir = cache_dir / "claude"
    lock_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        lock_dir.chmod(0o700)
    lock_path = lock_dir / f"{session_key}.lock"
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_snapshot(directory: Path, original_path: Path, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    suffix = original_path.suffix
    if not re.fullmatch(r"\.[A-Za-z0-9_-]{1,16}", suffix):
        suffix = ".txt"
    destination = directory / f"{uuid.uuid4().hex}{suffix}"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as temporary:
            temporary.write(text)
            temporary_path = Path(temporary.name)
        if os.name != "nt":
            temporary_path.chmod(0o600)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return destination


def pre_tool_use(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("tool_name") != "Read":
        return {}

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or not isinstance(tool_input.get("file_path"), str):
        return _deny("the Read tool did not provide a file path")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return _deny("Claude Code did not provide a session ID")

    cwd = payload.get("cwd", str(Path.cwd()))
    if not isinstance(cwd, str):
        return _deny("Claude Code provided an invalid working directory")
    try:
        config = load_config(start_dir=cwd)
        original_path = Path(tool_input["file_path"]).expanduser()
        if not original_path.is_absolute():
            original_path = Path(cwd) / original_path
        original_path = original_path.resolve(strict=True)
        if not original_path.is_file():
            return _deny("the requested path is not a regular file")
        if original_path.is_relative_to(config.cache_dir):
            return {}

        session_key = _session_key(session_id)
        content = original_path.read_text(encoding="utf-8")
        with _session_lock(config.cache_dir, session_key):
            store = SessionStore(config.cache_dir)
            _, existing_mapping = store.load_or_empty(session_key)
            result = scrub(content, config, existing_mapping)
            if result.text == content:
                return {}

            store.save(session_key, result.mapping)
            snapshot_dir = config.cache_dir / "claude" / session_key
            snapshot_path = _write_snapshot(snapshot_dir, original_path, result.text)
        updated_input = dict(tool_input)
        updated_input["file_path"] = str(snapshot_path)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": updated_input,
            }
        }
    except (OSError, UnicodeError, ValueError) as error:
        return _deny(str(error))


def session_end(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return {}
    cwd = payload.get("cwd", str(Path.cwd()))
    if not isinstance(cwd, str):
        return {}
    config = load_config(start_dir=cwd)
    session_key = _session_key(session_id)
    with _session_lock(config.cache_dir, session_key):
        SessionStore(config.cache_dir).delete(session_key)
        snapshot_dir = (config.cache_dir / "claude" / session_key).resolve()
        claude_dir = (config.cache_dir / "claude").resolve()
        if snapshot_dir.parent == claude_dir and snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)
    return {}


def handle(event: str, raw_input: str) -> str:
    try:
        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
    except (json.JSONDecodeError, ValueError) as error:
        result = _deny(f"invalid Claude Code hook input: {error}") if event == "claude-pre" else {}
    else:
        if event == "claude-pre":
            result = pre_tool_use(payload)
        else:
            result = session_end(payload)
    return json.dumps(result)
