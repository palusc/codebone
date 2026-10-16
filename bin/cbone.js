#!/usr/bin/env node
/** Launch the MCP bridge bundled with codebone on macOS or Windows. */
const { spawn } = require('child_process');
const { existsSync } = require('fs');
const { homedir } = require('os');
const { join } = require('path');

function findCommand(platform = process.platform, env = process.env, exists = existsSync, home = homedir()) {
  if (env.CODEBONE_MCP) return { command: env.CODEBONE_MCP, args: [] };
  if (env.CODEBONE_PYTHON) return { command: env.CODEBONE_PYTHON, args: ['-m', 'codebone_mcp.server'] };
  if (platform === 'win32') {
    const local = env.LOCALAPPDATA || join(home, 'AppData', 'Local');
    const candidates = [
      join(local, 'Programs', 'codebone', 'cbone.exe'),
      join(local, 'codebone', 'cbone.exe'),
    ];
    for (const command of candidates) if (exists(command)) return { command, args: [] };
    return { command: 'python', args: ['-m', 'codebone_mcp.server'] };
  }
  for (const command of [
    join(home, 'Library', 'Application Support', 'codebone', 'venv', 'bin', 'python3'),
    '/Applications/codebone.app/Contents/Resources/venv/bin/python3',
  ]) if (exists(command)) return { command, args: ['-m', 'codebone_mcp.server'] };
  return { command: 'python3', args: ['-m', 'codebone_mcp.server'] };
}

function main() {
  const { command, args } = findCommand();
  const child = spawn(command, args, { stdio: 'inherit', env: process.env, windowsHide: true });
  child.on('error', (err) => {
    console.error('[cbone] Could not launch ' + command + ': ' + err.message + '\n' +
      'Install codebone: https://github.com/palusc/codebone/releases\n' +
      'For portable Windows installs, set CODEBONE_MCP to cbone.exe.');
    process.exit(1);
  });
  child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
}
if (require.main === module) main();
module.exports = { findCommand, main };
