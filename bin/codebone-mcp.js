#!/usr/bin/env node
/**
 * codebone-mcp — npm bridge for the codebone MCP server.
 *
 * Locates the Python interpreter bundled with codebone and spawns
 * `python3 -m codebone_mcp.server`, passing MCP stdio straight through.
 *
 * Install locations tried (in order):
 *   1. CODEBONE_PYTHON env var (override for custom installs)
 *   2. ~/Library/Application Support/codebone/venv/bin/python3
 *   3. python3 on PATH (source installs / Homebrew)
 */

const { spawn } = require("child_process");
const { existsSync } = require("fs");
const { homedir } = require("os");
const { join } = require("path");

const VENV_PYTHON = join(
  homedir(),
  "Library",
  "Application Support",
  "codebone",
  "venv",
  "bin",
  "python3"
);

const APP_BUNDLE_PYTHON = "/Applications/codebone.app/Contents/Resources/venv/bin/python3";

function findPython() {
  if (process.env.CODEBONE_PYTHON) return process.env.CODEBONE_PYTHON;
  if (existsSync(VENV_PYTHON)) return VENV_PYTHON;
  if (existsSync(APP_BUNDLE_PYTHON)) return APP_BUNDLE_PYTHON;
  return "python3"; // fallback — source install or Homebrew
}

const python = findPython();

const child = spawn(python, ["-m", "codebone_mcp.server"], {
  stdio: "inherit",
  env: {
    ...process.env,
    // Forward port override if set
    ...(process.env.CODEBONE_PORT ? { CODEBONE_PORT: process.env.CODEBONE_PORT } : {}),
  },
});

child.on("error", (err) => {
  if (err.code === "ENOENT") {
    console.error(
      "[codebone-mcp] Python not found at: " + python + "\n" +
      "Make sure codebone is installed: https://github.com/palusc/codebone/releases"
    );
  } else {
    console.error("[codebone-mcp] Failed to start:", err.message);
  }
  process.exit(1);
});

child.on("exit", (code) => process.exit(code ?? 0));
