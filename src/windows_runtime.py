"""Desktop service lifecycle shared by the Windows UI and packaged smoke test."""
import json
import os
from pathlib import Path
import sys

from .config import Config, find_free_port
from .service import CodeBoneService
from .server import ServerThread


class DesktopRuntime:
    def __init__(self, config=None):
        self.config = config or Config()
        if getattr(sys, 'frozen', False):
            from .config import BASE_MODEL_PATH
            from .model_fetch import BUNDLED_MODEL
            if self.config.get('model_path') == BASE_MODEL_PATH and BUNDLED_MODEL.is_file():
                self.config.set('model_path', str(BUNDLED_MODEL))
        self.service = CodeBoneService(self.config)
        self.server = ServerThread(self.service)

    def start(self):
        self.server.start()
        if self.service.last_error:
            raise RuntimeError(self.service.last_error)
        self.service.start(auto_scan=False)

    def open_project(self, project):
        project = Path(project).expanduser().resolve()
        if not project.is_dir():
            raise ValueError(f'Project folder does not exist: {project}')
        self.service.stop()
        self.config.set('project_path', str(project))
        self.config.add_recent_project(str(project))
        self.service.start(auto_scan=False)
        self.service.rescan_all(wait=True)

    def close(self):
        self.service.cancel_scan()
        self.service.resume_scan()
        self.server.stop()
        self.service.close()
        self.service.storage.close()

    def mcp_command(self):
        if getattr(sys, 'frozen', False):
            executable = Path(sys.executable).with_name('codebone-mcp.exe')
            if not executable.is_file():
                raise FileNotFoundError(f'MCP executable is missing: {executable}')
            return {'command': str(executable), 'args': []}
        return {'command': sys.executable, 'args': ['-m', 'codebone_mcp.server'],
                'cwd': str(Path(__file__).resolve().parents[1])}

    def register_mcp(self, target: Path):
        """Explicit opt-in. Preserve other servers and reject unreadable settings."""
        data = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        if not isinstance(data, dict):
            raise ValueError('MCP configuration must be a JSON object')
        servers = data.setdefault('mcpServers', {})
        if not isinstance(servers, dict):
            raise ValueError('mcpServers must be a JSON object')
        servers['codebone'] = self.mcp_command()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = target.with_name(target.name + '.codebone-backup')
            if not backup.exists():
                backup.write_bytes(target.read_bytes())
        temp = target.with_name(target.name + '.codebone.tmp')
        temp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        os.replace(temp, target)


def smoke_test(result_path: Path, gui=False):
    """Exercise the installed binary, native UI widgets, indexing and real HTTP."""
    import tempfile
    import httpx
    from . import __version__
    from .providers import FastFallbackProvider
    os.environ['CODEBONE_NO_MCP_PATCH'] = '1'
    with tempfile.TemporaryDirectory(prefix='codebone-smoke-') as folder:
        root = Path(folder)
        project = root / 'project'
        project.mkdir()
        (project / 'billing.py').write_text('from fastapi import FastAPI\napp = FastAPI()\n@app.post("/checkout")\ndef checkout():\n    return {"paid": True}\n', encoding='utf-8')
        cfg = Config(root / 'data' / 'config.json')
        cfg.set('server_port', find_free_port(18053))
        runtime = DesktopRuntime(cfg)
        runtime.service.provider = FastFallbackProvider()
        try:
            runtime.start()
            runtime.open_project(project)
            with httpx.Client(base_url=runtime.server.url, trust_env=False) as client:
                status = client.get('/codebone/status').raise_for_status().json()
                assert status['file_count'] == 1 and not status['last_error'], status
                context = client.get('/codebone/context', params={'format': 'json', 'query': 'checkout'}).raise_for_status().json()
                assert context['match_count'] == 1, context
                assert client.get('/codebone/status', headers={'Host': 'evil.example'}).status_code == 403
                assert '<html' in client.get('/codebone/graph/ui').raise_for_status().text.lower()
            if gui:
                from .windows_app import WindowsApp
                app = WindowsApp(runtime)
                app.root.update()
                assert app.notebook.index('end') >= 4
                assert app.tray is not None
                import time
                app.notebook.select(app.settings_tab)
                app.root.update()
                app.tray.run_detached()
                for _ in range(50):
                    if app.tray.visible:
                        break
                    time.sleep(0.1)
                assert app.tray.visible, 'Win32 tray icon did not become visible'
                app.tray.stop()
                app.worker.shutdown(wait=True)
                app.root.destroy()
                from .model_fetch import BUNDLED_MODEL, is_valid
                from .providers import BuiltinProvider
                assert is_valid(BUNDLED_MODEL), 'Bundled model checksum mismatch'
                provider = BuiltinProvider(str(BUNDLED_MODEL), n_gpu_layers=0)
                try:
                    assert provider.generate('Reply with OK.', max_tokens=16).strip(), 'CPU model returned no text'
                finally:
                    provider.close()
            result_path.write_text(json.dumps({'version': __version__, 'indexed_files': 1, 'context_matches': 1, 'gui': gui, 'model': gui, 'passed': True}), encoding='utf-8')
        finally:
            runtime.close()
