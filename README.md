# llm-shield

`llm-shield` is a local privacy wrapper for text sent to language models. It
replaces configured sensitive terms and regex matches with placeholders such
as `REDACTED_0`, saves the mapping locally, and can restore those values in a
model response.

## Requirements

- Python 3.9 or newer
- PyYAML (installed automatically with the package)

## Install

From a checkout of this repository:

```sh
python -m pip install .
```

To install an editable development version and test dependencies:

```sh
python -m pip install -e ".[dev]"
```

## Set up a project

From the root of the project whose text you want to scrub, run:

```sh
llm-shield init
```

This creates `.llm-shield.yml` and adds `.llm-shield/` to `.gitignore`. Edit
the configuration to list the terms and patterns to protect:

```yaml
version: "1.0"
terms:
  - "Antonio"
  - "Perico"
  - "77323214P"
patterns:
  - name: "Spanish NIF/NIE"
    regex: "[0-9]{8}[A-Z]"
  - name: "API keys"
    regex: "sk_live_[0-9a-zA-Z]{24}"
options:
  placeholder_prefix: "REDACTED_"
  cache_dir: ".llm-shield"
```

Configuration is read from the current directory or its parent directories.
Use `--config <file-or-directory>` to select a configuration explicitly.

## Scrub and restore

Scrub a file and write the anonymized text to another file:

```sh
llm-shield scrub --input prompt.txt --output prompt.scrubbed.txt
```

The input may instead be literal text, or `-` to read from standard input.
With no `--input`, the command reads stdin; with no `--output`, it writes the
scrubbed text to stdout. The generated session ID is printed to stderr, so
stdout remains suitable for piping:

```sh
cat prompt.txt | llm-shield scrub > prompt.scrubbed.txt
```

Send only the scrubbed text to the external model. Then restore its response
using the session ID reported by `scrub`:

```sh
llm-shield restore --session <session-id> --input response.txt --output response.restored.txt
```

`restore` also accepts stdin and stdout. If `--session` is omitted, it uses the
latest scrub session:

```sh
cat response.txt | llm-shield restore > response.restored.txt
```

After a successful restore, that session is deleted. Pass the session ID
explicitly when multiple scrub/restore workflows may overlap.

## Claude Code project hook

Initialize the project configuration and add the sensitive terms and patterns
first. Then, from the project root, install the hook:

```sh
llm-shield init
# Edit .llm-shield.yml to configure sensitive terms and patterns.
llm-shield install claude
```

This merges a `PreToolUse` hook for Claude Code's `Read` tool and a `SessionEnd`
cleanup hook into the project's `.claude/settings.json`. It does not modify
account-level settings in `~/.claude/`. The `llm-shield` command must be
installed and available on `PATH` wherever the project hook runs. To target a
project without changing directories, pass `--project-dir <path>`.

When Claude Code reads a file, the hook scrubs its text into a private,
project-local snapshot and redirects that `Read` call to the snapshot. The
original file is not changed. Placeholder mappings are shared across reads in
the same Claude Code session, and snapshots and mappings are removed at
`SessionEnd`.

This integration covers Claude Code's `Read` tool only. It does not intercept
file contents read through `Bash`, search tools, other integrations, or prompts
submitted directly to Claude. The hook also cannot rewrite Claude's final
response, so automatic restoration of generated output is not provided.

## Wrap another command

`wrap` scrubs stdin before passing it to a child command, restores placeholders
in the child command's stdout, and forwards the child's stderr and exit code:

```sh
cat prompt.txt | llm-shield wrap -- your-llm-command --stdin
```

The command must accept input on stdin and return its response on stdout for
the response to be restored. A session is retained if the child exits with a
nonzero status.

## How matching works

- Terms are matched as literal, case-sensitive text. Longer overlapping terms
  take precedence.
- Regex patterns use Python's regular-expression syntax.
- Repeated occurrences of the same matched value share a placeholder within a
  session.
- Placeholder-like text already present in the input is not reused for a new
  replacement.

Session files contain the original sensitive values. Keep the `.llm-shield/`
cache private and do not share it; `init` ignores it in Git, and the CLI
restricts its permissions where supported.

## Development and distribution

Run the tests with:

```sh
python -m unittest discover -s tests -v
```

For PyInstaller builds and the companion NPM wrapper scaffold, see
[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).
