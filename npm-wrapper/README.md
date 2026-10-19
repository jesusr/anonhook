# anonhook

Install the command globally:

```sh
npm install --global anonhook
anonhook --help
```

`anonhook` installs a native executable for Linux x64, macOS x64/arm64, or
Windows x64 during package installation. Python is not required. The binary is
downloaded over HTTPS from the matching GitHub Release for this package
version. Other platforms are not currently supported.

In a project, initialize configuration, add the terms and patterns to protect,
and install the project-local Claude Code hook:

```sh
anonhook init
# Edit .llm-shield.yml
anonhook install claude
```

See the [project README](https://github.com/jesusr/anonhook#readme) for scrub,
restore, hook limitations, and command examples.
