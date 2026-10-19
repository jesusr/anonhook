#!/usr/bin/env node

const fs = require("node:fs");
const https = require("node:https");
const path = require("node:path");
const { pipeline } = require("node:stream/promises");

const packageInfo = require("../package.json");
const assets = {
  "linux-x64": "anonhook-linux-x64",
  "darwin-x64": "anonhook-darwin-x64",
  "darwin-arm64": "anonhook-darwin-arm64",
  "win32-x64": "anonhook-win32-x64.exe",
};

function request(url, redirects = 0) {
  return new Promise((resolve, reject) => {
    https.get(url, (response) => {
      const status = response.statusCode || 0;
      if ([301, 302, 303, 307, 308].includes(status)) {
        response.resume();
        if (redirects >= 5 || !response.headers.location) {
          reject(new Error("Too many redirects while downloading the anonhook binary"));
          return;
        }
        const nextUrl = new URL(response.headers.location, url);
        if (nextUrl.protocol !== "https:") {
          reject(new Error("Refusing a non-HTTPS anonhook binary download"));
          return;
        }
        resolve(request(nextUrl, redirects + 1));
        return;
      }
      if (status !== 200) {
        response.resume();
        reject(new Error(`GitHub returned HTTP ${status} for ${url}`));
        return;
      }
      resolve(response);
    }).on("error", reject);
  });
}

async function install() {
  const target = `${process.platform}-${process.arch}`;
  const asset = assets[target];
  if (!asset) {
    throw new Error(`No prebuilt anonhook binary is available for ${target}`);
  }

  const version = `v${packageInfo.version}`;
  const url = `https://github.com/jesusr/anonhook/releases/download/${version}/${asset}`;
  const executable = process.platform === "win32" ? "anonhook.exe" : "anonhook";
  const destination = path.join(__dirname, "..", "vendor", executable);
  const temporary = `${destination}.${process.pid}.tmp`;

  fs.mkdirSync(path.dirname(destination), { recursive: true });
  try {
    const response = await request(url);
    await pipeline(response, fs.createWriteStream(temporary, { mode: 0o700 }));
    if (process.platform !== "win32") {
      fs.chmodSync(temporary, 0o755);
    }
    fs.renameSync(temporary, destination);
  } catch (error) {
    if (fs.existsSync(temporary)) {
      fs.unlinkSync(temporary);
    }
    throw error;
  }
}

if (require.main === module) {
  install().catch((error) => {
    console.error(`anonhook installation failed: ${error.message}`);
    console.error(`Expected release asset: https://github.com/jesusr/anonhook/releases/tag/v${packageInfo.version}`);
    process.exitCode = 1;
  });
}

module.exports = { assets, install };
