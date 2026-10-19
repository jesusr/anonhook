from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CONFIG_NAME = ".llm-shield.yml"
DEFAULT_CONFIG = """\
version: "1.0"
terms: []
patterns: []
options:
  placeholder_prefix: "REDACTED_"
  cache_dir: ".llm-shield"
"""


class ConfigError(ValueError):
    """Raised when the shield configuration is missing or invalid."""


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: str


@dataclass(frozen=True)
class ShieldConfig:
    root: Path
    terms: tuple[str, ...]
    patterns: tuple[Pattern, ...]
    placeholder_prefix: str
    cache_dir: Path


def find_config(config_path: str | Path | None = None, start_dir: str | Path | None = None) -> Path:
    if config_path is not None:
        path = Path(config_path).expanduser().resolve()
        if path.is_dir():
            path = path / CONFIG_NAME
        if not path.is_file():
            raise ConfigError(f"Configuration file not found: {path}")
        return path

    start = Path(start_dir).expanduser().resolve() if start_dir is not None else Path.cwd()
    if start.is_file():
        start = start.parent
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise ConfigError(f"{CONFIG_NAME} not found; run 'llm-shield init' first")


def load_config(
    config_path: str | Path | None = None,
    start_dir: str | Path | None = None,
) -> ShieldConfig:
    path = find_config(config_path, start_dir=start_dir)
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"Could not read configuration {path}: {error}") from error

    if not isinstance(raw, dict):
        raise ConfigError(f"Configuration must be a YAML mapping: {path}")

    terms = raw.get("terms", [])
    patterns = raw.get("patterns", [])
    options = raw.get("options", {})
    if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
        raise ConfigError("'terms' must be a list of strings")
    if not isinstance(patterns, list):
        raise ConfigError("'patterns' must be a list")
    if not isinstance(options, dict):
        raise ConfigError("'options' must be a mapping")

    parsed_patterns: list[Pattern] = []
    for index, item in enumerate(patterns):
        if not isinstance(item, dict) or not isinstance(item.get("regex"), str):
            raise ConfigError(f"'patterns[{index}]' must have a string 'regex'")
        regex = item["regex"]
        try:
            re.compile(regex)
        except re.error as error:
            raise ConfigError(f"Invalid regex in 'patterns[{index}]': {error}") from error
        name = item.get("name", f"pattern {index + 1}")
        if not isinstance(name, str):
            raise ConfigError(f"'patterns[{index}].name' must be a string")
        parsed_patterns.append(Pattern(name=name, regex=regex))

    prefix = options.get("placeholder_prefix", "REDACTED_")
    cache_dir = options.get("cache_dir", ".llm-shield")
    if not isinstance(prefix, str) or not prefix:
        raise ConfigError("'options.placeholder_prefix' must be a non-empty string")
    if not isinstance(cache_dir, str) or not cache_dir:
        raise ConfigError("'options.cache_dir' must be a non-empty string")

    root = path.parent
    return ShieldConfig(
        root=root,
        terms=tuple(terms),
        patterns=tuple(parsed_patterns),
        placeholder_prefix=prefix,
        cache_dir=(root / cache_dir).resolve(),
    )


def initialize(directory: str | Path = ".") -> Path:
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / CONFIG_NAME
    if config_path.exists():
        raise ConfigError(f"Configuration already exists: {config_path}")
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    ignore_entry = ".llm-shield/"
    if ignore_entry not in {line.strip() for line in existing.splitlines()}:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        gitignore.write_text(f"{existing}{separator}{ignore_entry}\n", encoding="utf-8")
    return config_path


def install_claude_hook(directory: str | Path = ".") -> Path:
    root = Path(directory).expanduser().resolve()
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError(f"Could not read Claude Code settings {settings_path}: {error}") from error
    else:
        settings = {}
    if not isinstance(settings, dict):
        raise ConfigError(f"Claude Code settings must contain a JSON object: {settings_path}")

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ConfigError(f"'hooks' must be an object in {settings_path}")

    registrations = {
        "PreToolUse": {
            "matcher": "Read",
            "hooks": [{"type": "command", "command": "llm-shield hook claude-pre"}],
        },
        "SessionEnd": {
            "hooks": [{"type": "command", "command": "llm-shield hook claude-session-end"}],
        },
    }
    for event, registration in registrations.items():
        handlers = hooks.setdefault(event, [])
        if not isinstance(handlers, list):
            raise ConfigError(f"'hooks.{event}' must be a list in {settings_path}")
        for group in handlers:
            if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
                raise ConfigError(f"Each entry in 'hooks.{event}' must contain a hooks list")
        command = registration["hooks"][0]["command"]
        if not any(
            isinstance(group, dict)
            and group.get("matcher") == registration.get("matcher")
            and any(
                isinstance(handler, dict) and handler.get("command") == command
                for handler in group.get("hooks", [])
            )
            for group in handlers
        ):
            handlers.append(registration)

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return settings_path
