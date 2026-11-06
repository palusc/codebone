#!/usr/bin/env node
/** Launch the MCP bridge bundled with codebone on macOS. */
const { spawn } = require('child_process');
const { existsSync } = require('fs');
const { homedir } = require('os');
const { join } = require('path');

function findCommand(platform = process.platform, env = process.env, exists = existsSync, home = homedir()) {
  if (env.CODEBONE_MCP) return { command: env.CODEBONE_MCP, args: [] };
  if (env.CODEBONE_PYTHON) return { command: env.CODEBONE_PYTHON, args: ['-m', 'codebone_mcp.server'] };
  for (const command of [
    join(home, 'Library', 'Application Support', 'codebone', 'venv', 'bin', 'python3'),
    '/Applications/codebone.app/Contents/Resources/venv/bin/python3',
  ]) if (exists(command)) return { command, args: ['-m', 'codebone_mcp.server'] };
  return { command: 'python3', args: ['-m', 'codebone_mcp.server'] };
}

function main() {
  const update = process.argv.length === 3 && process.argv[2] === 'update';
  if (process.argv.length > 2 && !update) {
    const help = process.argv.length === 3 && ['--help', '-h'].includes(process.argv[2]);
    console.error('Usage: codebone | cb | igotaboner | gotaboner [update]\n' +
      'These commands start the MCP bridge for a coding agent.\n' +
      'Use update to check and install desktop app updates.');
    process.exit(help ? 0 : 1);
  }
  const { command, args } = findCommand(process.platform, update ? { ...process.env, CODEBONE_MCP: '' } : process.env);
  if (update) args.splice(0, args.length, join(__dirname, 'update.py'));
  const child = spawn(command, args, { stdio: 'inherit', env: process.env });
  child.on('error', (err) => {
    console.error('[cbone] Could not launch ' + command + ': ' + err.message + '\n' +
      'Install codebone: https://github.com/palusc/codebone/releases');
    process.exit(1);
  });
  child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
}
if (require.main === module) main();
module.exports = { findCommand, main };
