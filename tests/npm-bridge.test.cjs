const { test } = require('node:test');
const assert = require('node:assert/strict');
const { join } = require('node:path');
const { findCommand } = require('../bin/cbone.js');

test('executable and Python overrides remain supported', () => {
  assert.deepEqual(findCommand('darwin', { CODEBONE_MCP: '/custom/cbone' }), { command: '/custom/cbone', args: [] });
  assert.deepEqual(findCommand('darwin', { CODEBONE_PYTHON: '/custom/python' }), { command: '/custom/python', args: ['-m', 'codebone_mcp.server'] });
});
test('source fallback and macOS bundle paths are selected', () => {
  assert.equal(findCommand('darwin', {}, () => false, '/home').command, 'python3');
  assert.equal(findCommand('darwin', {}, p => p.startsWith('/Applications'), '/home').command, '/Applications/codebone.app/Contents/Resources/venv/bin/python3');
});
