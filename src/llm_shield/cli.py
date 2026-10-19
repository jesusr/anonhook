from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from .anonymizer import restore as restore_text
from .anonymizer import scrub as scrub_text
from .claude_hook import handle as handle_claude_hook
from .config import ConfigError, initialize, install_claude_hook, load_config
from .sessions import SessionError, SessionStore


def _read_input(value: str | None, stdin: TextIO) -> str:
    if value is None or value == "-":
        return stdin.read()
    path = Path(value).expanduser()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def _write_output(value: str, destination: str | None, stdout: TextIO) -> None:
    if destination is None or destination == "-":
        stdout.write(value)
        stdout.flush()
    else:
        Path(destination).expanduser().write_text(value, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anonhook")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create a default configuration and update .gitignore")
    install = commands.add_parser("install", help="install a project-level application hook")
    install.add_argument("application", choices=("claude",))
    install.add_argument("--project-dir", default=".", help="project root (default: current directory)")

    for name, help_text in (
        ("scrub", "anonymize input and create a restorable session"),
        ("restore", "restore placeholders using a saved session"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--input", help="input file, literal text, or - for stdin (default: stdin)")
        command.add_argument("--output", help="output file or - for stdout (default: stdout)")
        command.add_argument("--config", help="configuration file or project directory")
        if name == "restore":
            command.add_argument("--session", help="session ID printed by scrub; defaults to the latest session")

    wrap = commands.add_parser("wrap", help="run a command with anonymized stdin and restored stdout")
    wrap.add_argument("--config", help="configuration file or project directory")
    wrap.add_argument("command_args", nargs=argparse.REMAINDER, help="command to run, after --")
    hook = commands.add_parser("hook", help="run an application integration hook")
    hook.add_argument("hook_name", choices=("claude-pre", "claude-session-end"))
    return parser


def _scrub_command(args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    config = load_config(args.config)
    source = _read_input(args.input, stdin)
    result = scrub_text(source, config)
    session_id = SessionStore(config.cache_dir).create(result.mapping)
    _write_output(result.text, args.output, stdout)
    stderr.write(f"anonhook session: {session_id}\n")
    return 0


def _restore_command(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    config = load_config(args.config)
    store = SessionStore(config.cache_dir)
    session_id, mapping = store.load(args.session)
    source = _read_input(args.input, stdin)
    _write_output(restore_text(source, mapping), args.output, stdout)
    store.delete(session_id)
    return 0


def _wrap_command(args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    command = args.command_args
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("wrap requires a command after --")

    config = load_config(args.config)
    result = scrub_text(stdin.read(), config)
    store = SessionStore(config.cache_dir)
    session_id = store.create(result.mapping)
    completed = subprocess.run(command, input=result.text, text=True, capture_output=True, check=False)
    stderr.write(completed.stderr)
    _write_output(restore_text(completed.stdout, result.mapping), "-", stdout)
    if completed.returncode == 0:
        store.delete(session_id)
    else:
        stderr.write(f"anonhook session retained: {session_id}\n")
    return completed.returncode


def main(
    argv: list[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            config_path = initialize()
            stdout.write(f"Created {config_path}\n")
            return 0
        if args.command == "install":
            settings_path = install_claude_hook(args.project_dir)
            stdout.write(f"Installed project-level Claude Code hook in {settings_path}\n")
            return 0
        if args.command == "scrub":
            return _scrub_command(args, stdin, stdout, stderr)
        if args.command == "restore":
            return _restore_command(args, stdin, stdout)
        if args.command == "hook":
            stdout.write(handle_claude_hook(args.hook_name, stdin.read()))
            stdout.write("\n")
            return 0
        return _wrap_command(args, stdin, stdout, stderr)
    except (ConfigError, SessionError, OSError, UnicodeError, ValueError) as error:
        stderr.write(f"anonhook: {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
