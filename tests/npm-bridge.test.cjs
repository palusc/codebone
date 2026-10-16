const { test } = require('node:test');
const assert = require('node:assert/strict');
const { join } = require('node:path');
const { findCommand } = require('../bin/cbone.js');

test('Windows installed MCP executable is launched directly, preserving spaces', () => {
  const result = findCommand('win32', { LOCALAPPDATA: '/User Name/AppData/Local' }, p => p.endsWith(join('Programs', 'codebone', 'cbone.exe')), '/User Name');
  assert.equal(result.command, join('/User Name/AppData/Local', 'Programs', 'codebone', 'cbone.exe'));
  assert.deepEqual(result.args, []);
});
test('portable executable and Python overrides remain supported', () => {
  assert.deepEqual(findCommand('win32', { CODEBONE_MCP: 'D:/portable/cbone.exe' }), { command: 'D:/portable/cbone.exe', args: [] });
  assert.deepEqual(findCommand('darwin', { CODEBONE_PYTHON: '/custom/python' }), { command: '/custom/python', args: ['-m', 'codebone_mcp.server'] });
});
test('source fallback and macOS bundle paths are selected', () => {
  assert.equal(findCommand('win32', {}, () => false, '/home').command, 'python');
  assert.equal(findCommand('darwin', {}, () => false, '/home').command, 'python3');
  assert.equal(findCommand('darwin', {}, p => p.startsWith('/Applications'), '/home').command, '/Applications/codebone.app/Contents/Resources/venv/bin/python3');
});
