#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const platform = process.platform;
const architecture = process.arch;
const executableName = platform === "win32" ? "anonhook.exe" : "anonhook";
const executable = path.join(__dirname, "..", "vendor", executableName);

const result = spawnSync(executable, process.argv.slice(2), { stdio: "inherit" });

if (result.error) {
  if (result.error.code === "ENOENT") {
    console.error(
      `anonhook's standalone binary is missing for ${platform}/${architecture}. ` +
      "Reinstall the package or report this platform as unsupported."
    );
  } else {
    console.error(`Could not start anonhook: ${result.error.message}`);
  }
  process.exit(1);
}

process.exit(result.status ?? 1);
