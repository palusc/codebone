"""Windows port contracts, with native-only checks on the Windows runner."""
import json
import sys
from pathlib import Path

import pytest

from src.config import Config
from src.platform_paths import data_dir
from src.providers import FastFallbackProvider
from src.windows_runtime import DesktopRuntime, smoke_test


def test_windows_data_path_uses_local_appdata_and_keeps_spaces():
    assert data_dir('win32', {'LOCALAPPDATA': '/Users/Test Name/AppData/Local'}, '/unused') == Path('/Users/Test Name/AppData/Local/codebone')
    assert data_dir('win32', {}, '/Users/Test') == Path('/Users/Test/AppData/Local/codebone')
    assert data_dir('darwin', {}, '/Users/Test') == Path('/Users/Test/Library/Application Support/codebone')


def test_runtime_scans_and_serves_context_over_http(tmp_path):
    report = tmp_path / 'smoke.json'
    smoke_test(report)
    result = json.loads(report.read_text())
    assert result['passed'] and result['indexed_files'] == result['context_matches'] == 1


def test_explicit_mcp_registration_preserves_and_backs_up_client_settings(tmp_path):
    runtime = DesktopRuntime(Config(tmp_path / 'data/config.json'))
    target = tmp_path / 'client/mcp.json'
    target.parent.mkdir()
    original = json.dumps({'theme': 'dark', 'mcpServers': {'other': {'command': 'other'}}})
    target.write_text(original)
    try:
        runtime.register_mcp(target)
        contents = json.loads(target.read_text())
        assert contents['theme'] == 'dark' and contents['mcpServers']['other']['command'] == 'other'
        assert contents['mcpServers']['codebone']['args'] == ['-m', 'codebone_mcp.server']
        assert target.with_name('mcp.json.codebone-backup').read_text() == original
        runtime.register_mcp(target)
        assert target.with_name('mcp.json.codebone-backup').read_text() == original
        target.write_text('{broken')
        with pytest.raises(ValueError):
            runtime.register_mcp(target)
        assert target.read_text() == '{broken'
    finally:
        runtime.close()


def test_frozen_mcp_command_uses_sibling_executable(tmp_path, monkeypatch):
    (tmp_path / 'cbone.exe').write_bytes(b'fake')
    runtime = DesktopRuntime(Config(tmp_path / 'data/config.json'))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'codebone.exe'))
    try:
        assert runtime.mcp_command() == {'command': str(tmp_path / 'cbone.exe'), 'args': []}
    finally:
        runtime.close()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI requires a native Windows user session')
def test_windows_provider_key_encrypted_and_reloaded(tmp_path):
    path = tmp_path / 'config.json'
    config = Config(path)
    config.set('brain_cloud_api_key', 'test-key-only-for-dpapi-test')
    assert 'test-key-only-for-dpapi-test' not in path.read_text()
    assert b'test-key-only-for-dpapi-test' not in (tmp_path / 'provider-key.dpapi').read_bytes()
    assert Config(path).get('brain_cloud_api_key') == 'test-key-only-for-dpapi-test'
    config.set('brain_cloud_api_key', '')
    assert Config(path).get('brain_cloud_api_key') == ''
    assert not (tmp_path / 'provider-key.dpapi').exists()
