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

const { spawnSync } = require('node:child_process');
test('unsupported arguments exit with instructions instead of starting MCP', () => {
  for (const argument of ['upadate', '--help']) {
    const result = spawnSync(process.execPath, [join(__dirname, '../bin/cbone.js'), argument], {
      encoding: 'utf8', timeout: 2000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, argument === '--help' ? 0 : 1);
    assert.match(result.stderr, /desktop app updates/);
    assert.equal(result.stdout, '');
  }
});
