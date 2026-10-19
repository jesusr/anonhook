#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const platform = process.platform;
const architecture = process.arch;
const executableName = platform === "win32" ? "llm-shield.exe" : "llm-shield";
const executable = path.join(__dirname, "..", "vendor", `${platform}-${architecture}`, executableName);

const result = spawnSync(executable, process.argv.slice(2), { stdio: "inherit" });

if (result.error) {
  if (result.error.code === "ENOENT") {
    console.error(
      `No llm-shield binary is packaged for ${platform}/${architecture}. ` +
      "Build it with PyInstaller and place it under npm-wrapper/vendor/<platform>-<arch>/."
    );
  } else {
    console.error(`Could not start llm-shield: ${result.error.message}`);
  }
  process.exit(1);
}

process.exit(result.status ?? 1);
