# Building and distributing anonhook

## Install from Python source

From the repository root, install the package with `python -m pip install .`.
For development and tests, use `python -m pip install -e ".[dev]"`. The
`anonhook` command is registered as the primary project script. `llm-shield`
remains available as a Python entrypoint alias.

## Build standalone binaries

Build separately on each target operating system and architecture; PyInstaller
does not cross-compile. In a clean environment for each target:

```sh
python -m pip install .
python -m pip install pyinstaller
pyinstaller --onefile --name anonhook --collect-all yaml \
  --paths src scripts/entrypoint.py
```

Smoke-test the resulting `dist/anonhook` (or `dist/anonhook.exe`) with
`init`, `scrub`, and `restore`. Include the PyYAML data and modules in the
frozen application as shown; keep configuration and session files outside the
binary so they remain project-local.

## Install and publish through NPM

The NPM package is `anonhook` and is defined in `npm-wrapper/`. On
`npm install -g anonhook`, its postinstall script downloads the matching
standalone binary from the GitHub Release tagged with the same version. The
wrapper exposes the `anonhook` command and forwards arguments and standard
streams to that executable.

Supported release targets are Linux x64, macOS x64/arm64, and Windows x64.
The GitHub Actions workflow `.github/workflows/release.yml` builds these
executables for each version tag and attaches them to the matching GitHub
Release.

To publish a new version:

1. Update the Python and NPM versions together in `pyproject.toml` and
   `npm-wrapper/package.json`.
2. Commit and push a matching version tag, for example `v0.1.0`. Wait for the
   release workflow to finish and check that it attached every target binary.
3. From `npm-wrapper/`, log in with `npm login`, run `npm pack --dry-run` to
   inspect package contents, then run `npm publish`.

The NPM postinstall downloads and executes a native binary from the project's
GitHub Releases. Review release workflow changes and protect version tags
appropriately before publishing.

## Session and input notes

Run `anonhook init` once in the project root, then edit `.llm-shield.yml`.
Use `anonhook scrub` to read stdin and write anonymized text to stdout; the
session ID is reported on stderr. `anonhook restore --session <id>` restores
the latest model response and deletes that session after the output is
successfully written. Omitting `--session` uses the latest scrub session.
`--input` accepts an existing file path, literal text, or `-` for stdin;
`--output` accepts a file path or `-` for stdout.

`anonhook wrap -- command [args...]` sends anonymized stdin to the child
process and restores its stdout. It forwards the child's stderr and exit code.
Sessions from failed commands are retained for recovery. Avoid running multiple
unrelated scrub/restore flows concurrently when relying on the implicit latest
session; pass the ID explicitly when flows overlap.

Session mappings contain the original sensitive values. The cache directory
is project-local, is added to `.gitignore` by `init`, and is created with
owner-only permissions where supported.

## Claude Code project hook

Run `anonhook install claude` from the project root (or pass
`--project-dir <path>`) to merge the Read pre-hook and session cleanup hook
into that project's `.claude/settings.json`. This is project-level
configuration; it does not edit account-level Claude Code settings. Ensure
`anonhook` is installed and available on `PATH` for Claude Code to execute
the configured command.

The pre-hook redirects Claude Code's `Read` tool to an anonymized snapshot
instead of modifying the original file. It does not intercept file access
through Bash, search tools, or other tools, and it cannot rewrite Claude's final
response. Claude Code hook integration therefore requires a separate workflow
to restore placeholders in generated output.
