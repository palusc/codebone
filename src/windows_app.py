"""Native Windows desktop UI: Tk settings and a Win32 notification-area icon.

All widgets belong to the main thread. Tray callbacks and workers communicate
through a queue; scanning, downloads and provider calls never block Tk's loop.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import queue
import sys
import threading
import webbrowser

from . import __version__
from .config import BASE_MODEL_PATH, Config
from .platform_paths import resource_dir
from .windows_runtime import DesktopRuntime

logger = logging.getLogger('codebone.windows')


class WindowsApp:
    def __init__(self, runtime):
        import tkinter as tk
        from tkinter import ttk
        import pystray
        from PIL import Image
        self.tk, self.ttk = tk, ttk
        self.runtime, self.config, self.service = runtime, runtime.config, runtime.service
        self.events = queue.Queue()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='codebone-desktop')
        self.closed = False
        self.busy = False
        self.root = tk.Tk()
        self.root.title(f'codebone {__version__}')
        self.root.geometry('780x620')
        self.root.minsize(680, 540)
        self.root.protocol('WM_DELETE_WINDOW', self.hide)
        self.status = tk.StringVar(value='Ready')
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=12, pady=12)
        self.projects_tab = self.tab('Projects')
        self.settings_tab = self.tab('Settings')
        self.scans_tab = self.tab('Saved scans')
        self.mcp_tab = self.tab('Coding agents')
        self.about_tab = self.tab('About')
        self.build_projects()
        self.build_settings()
        self.build_scans()
        self.build_mcp()
        self.build_about()
        ttk.Label(self.root, textvariable=self.status, wraplength=740).pack(fill='x', padx=14, pady=(0, 10))
        image = Image.open(resource_dir() / 'resources' / 'bone_active.png').convert('RGBA')
        self.tray = pystray.Icon('codebone', image, f'codebone {__version__}', pystray.Menu(
            pystray.MenuItem('Open codebone', lambda: self.events.put(('show', None)), default=True),
            pystray.MenuItem('Open graph', lambda: self.events.put(('graph', None))),
            pystray.MenuItem('Scan project', lambda: self.events.put(('scan', None))),
            pystray.MenuItem('Pause / resume scan', lambda: self.events.put(('pause', None))),
            pystray.MenuItem('Settings', lambda: self.events.put(('settings', None))),
            pystray.MenuItem('Quit', lambda: self.events.put(('quit', None))),
        ))
        self.root.after(100, self.poll)

    def tab(self, title):
        frame = self.ttk.Frame(self.notebook, padding=14)
        self.notebook.add(frame, text=title)
        return frame

    def button(self, parent, text, command):
        button = self.ttk.Button(parent, text=text, command=command)
        button.pack(side='left', padx=(0, 8), pady=6)
        return button

    def submit(self, label, fn):
        if self.busy:
            self.status.set('Another operation is running. Cancel the scan or wait for it to finish.')
            return
        self.busy = True
        self.status.set(label)
        def work():
            try:
                result = fn()
                self.events.put(('done', (label, result)))
            except Exception as exc:
                logger.exception('%s failed', label)
                self.events.put(('error', str(exc)))
        self.worker.submit(work)

    def build_projects(self):
        from tkinter import ttk
        ttk.Label(self.projects_tab, text='Projects stay on your computer. Select one to watch and scan.').pack(anchor='w')
        self.projects = self.tk.Listbox(self.projects_tab, height=12, exportselection=False)
        self.projects.pack(fill='both', expand=True, pady=10)
        self.refresh_projects()
        row = ttk.Frame(self.projects_tab); row.pack(fill='x')
        self.button(row, 'Add folder…', self.add_folder)
        self.button(row, 'Add GitHub repo…', self.add_github)
        self.button(row, 'Activate', self.activate_project)
        self.button(row, 'Remove', self.remove_project)
        row = ttk.Frame(self.projects_tab); row.pack(fill='x')
        self.button(row, 'Scan', self.scan)
        self.button(row, 'Scan workspace', lambda: self.submit('Scanning workspace', self.service.scan_all_projects))
        self.button(row, 'Pause / resume', self.pause)
        self.button(row, 'Cancel', self.service.cancel_scan)
        self.button(row, 'Open graph', self.open_graph)
        self.auto_scan = self.tk.BooleanVar(value=True)
        ttk.Checkbutton(self.projects_tab, text='Watch active project and scan changes automatically', variable=self.auto_scan, command=self.toggle_watch).pack(anchor='w', pady=6)
        self.projects.bind('<<ListboxSelect>>', lambda e: self.selection_changed())

    def refresh_projects(self):
        self.projects.delete(0, 'end')
        for path in self.config.project_paths:
            self.projects.insert('end', str(path))
        if self.config.project_path:
            for i, path in enumerate(self.config.project_paths):
                if path == self.config.project_path:
                    self.projects.selection_set(i)

    def selected_project(self):
        selected = self.projects.curselection()
        return Path(self.projects.get(selected[0])) if selected else self.config.project_path

    def selection_changed(self):
        path = self.selected_project()
        if path:
            self.auto_scan.set(self.config.is_auto_scan_enabled(path))

    def toggle_watch(self):
        path = self.selected_project()
        if path:
            self.config.set_auto_scan_enabled(path, self.auto_scan.get())

    def add_folder(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, title='Select project folder')
        if path:
            self.submit('Scanning project', lambda: self.runtime.open_project(path))

    def add_github(self):
        from tkinter import simpledialog
        repo = simpledialog.askstring('GitHub project', 'Repository URL or owner/repository (Git for Windows recommended):', parent=self.root)
        if repo:
            def add():
                from .github import clone_github_repo
                self.runtime.open_project(clone_github_repo(repo))
            self.submit('Cloning and scanning repository', add)

    def activate_project(self):
        path = self.selected_project()
        if path:
            self.submit('Activating project', lambda: self.runtime.open_project(path))

    def remove_project(self):
        from tkinter import messagebox
        path = self.selected_project()
        if path and messagebox.askyesno('Remove project', 'Remove from workspace? Project files are kept.', parent=self.root):
            def remove():
                if path == self.config.project_path:
                    self.service.stop()
                    self.config.set('project_path', None)
                self.config.remove_project_path(str(path))
            self.submit('Removing project', remove)

    def scan(self):
        path = self.selected_project()
        if path:
            self.submit('Scanning project', lambda: self.runtime.open_project(path))
        else:
            self.add_folder()

    def pause(self):
        paused = self.service.toggle_pause_scan()
        self.status.set('Scan paused' if paused else 'Scan resumed')

    def open_graph(self):
        webbrowser.open(self.runtime.server.url + '/codebone/graph/ui')

    def entry(self, parent, label, value='', secret=False):
        row = self.ttk.Frame(parent); row.pack(fill='x', pady=5)
        self.ttk.Label(row, text=label, width=22).pack(side='left')
        var = self.tk.StringVar(value=value)
        self.ttk.Entry(row, textvariable=var, show='•' if secret else '').pack(side='left', fill='x', expand=True)
        return var

    def build_settings(self):
        ttk = self.ttk
        ttk.Label(self.settings_tab, text='Map agent', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(self.settings_tab, text='Built-in uses CPU on Windows. Cloud providers send source to your chosen provider.', wraplength=690).pack(anchor='w', pady=6)
        self.provider = self.tk.StringVar(value=self.config.get('brain_provider', 'builtin'))
        ttk.Combobox(self.settings_tab, textvariable=self.provider, state='readonly', values=('builtin', 'fallback', 'local_url', 'cloud')).pack(fill='x')
        self.model_path = self.entry(self.settings_tab, 'GGUF model', self.config.get('model_path', BASE_MODEL_PATH))
        row = ttk.Frame(self.settings_tab); row.pack(fill='x')
        self.button(row, 'Choose model…', self.choose_model)
        self.button(row, 'Download built-in model', self.download_model)
        self.local_url = self.entry(self.settings_tab, 'Local model URL', self.config.get('brain_local_url'))
        self.vendor = self.tk.StringVar(value=self.config.get('brain_cloud_vendor', 'openai'))
        ttk.Label(self.settings_tab, text='Cloud provider').pack(anchor='w', pady=(8, 0))
        ttk.Combobox(self.settings_tab, textvariable=self.vendor, values=('openai', 'anthropic', 'openrouter'), state='readonly').pack(fill='x')
        self.cloud_model = self.entry(self.settings_tab, 'Cloud model', self.config.get('brain_cloud_model'))
        self.api_key = self.entry(self.settings_tab, 'Replace API key', secret=True)
        ttk.Label(self.settings_tab, text='Leave blank to keep the stored key. Windows encrypts it for your user account.').pack(anchor='w')
        row = ttk.Frame(self.settings_tab); row.pack(fill='x', pady=8)
        self.button(row, 'Save settings', self.save_settings)
        self.button(row, 'Test map agent', lambda: self.submit('Testing map agent', self.test_provider))
        self.button(row, 'Clear stored API key', self.clear_key)

    def choose_model(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('GGUF models', '*.gguf')])
        if path:
            self.model_path.set(path)

    def download_model(self):
        from tkinter import messagebox
        if messagebox.askyesno('Download model', 'Download the built-in model (about 490 MB)? It is verified with the pinned SHA-256 checksum.', parent=self.root):
            def download():
                from .model_fetch import install
                install(Path(BASE_MODEL_PATH), lambda pct: self.events.put(('status', f'Downloading model: {pct}%')))
                self.config.set('model_path', BASE_MODEL_PATH)
                self.service.reload_provider()
            self.submit('Downloading model', download)

    def save_settings(self):
        settings = {'brain_provider': self.provider.get(), 'model_path': self.model_path.get(),
                    'brain_local_url': self.local_url.get(), 'brain_cloud_vendor': self.vendor.get(),
                    'brain_cloud_model': self.cloud_model.get()}
        key = self.api_key.get()
        def save():
            if settings['brain_provider'] == 'local_url':
                from urllib.parse import urlsplit
                if urlsplit(settings['brain_local_url']).scheme not in ('http', 'https'):
                    raise ValueError('Local model URL must use http:// or https://')
            if key:
                self.config.set('brain_cloud_api_key', key)
            for name, value in settings.items():
                self.config.set(name, value)
            self.service.reload_provider()
        self.submit('Saving settings', save)
        self.api_key.set('')

    def test_provider(self):
        provider = self.service.provider
        if self.config.get('brain_provider') == 'fallback':
            return 'Heuristic scanner is available; no language model is selected.'
        if not provider.available:
            raise RuntimeError('Map agent unavailable. Check the model file, URL or credentials.')
        answer = provider.generate('Reply with OK.', max_tokens=16)
        if not answer.strip():
            raise RuntimeError('Map agent returned no answer. Check logs and provider settings.')
        return 'Map agent answered successfully.'

    def clear_key(self):
        from tkinter import messagebox
        if messagebox.askyesno('Clear API key', 'Remove the stored map-agent API key?', parent=self.root):
            def clear():
                self.config.set('brain_cloud_api_key', '')
                self.service.reload_provider()
            self.submit('Removing API key', clear)

    def build_scans(self):
        self.scans = self.tk.Listbox(self.scans_tab, exportselection=False)
        self.scans.pack(fill='both', expand=True)
        row = self.ttk.Frame(self.scans_tab); row.pack(fill='x')
        self.button(row, 'Refresh', self.refresh_scans)
        self.button(row, 'Export…', self.export_scan)
        self.button(row, 'Import…', self.import_scan)
        self.refresh_scans()

    def refresh_scans(self):
        self.scan_items = self.service.scans.list_scans()
        self.scans.delete(0, 'end')
        for scan in self.scan_items:
            self.scans.insert('end', f"{scan.get('project_name', scan['id'])} — {scan.get('file_count', '?')} files")

    def export_scan(self):
        from tkinter import filedialog
        selected = self.scans.curselection()
        if selected:
            scan_id = self.scan_items[selected[0]]['id']
            dest = filedialog.asksaveasfilename(parent=self.root, defaultextension='.sqlite3')
            if dest:
                self.submit('Exporting scan', lambda: self.service.scans.export_scan(scan_id, Path(dest)))

    def import_scan(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('Saved scan', '*.sqlite3')])
        if path:
            self.submit('Importing scan', lambda: self.service.scans.import_scan(Path(path)))

    def build_mcp(self):
        ttk = self.ttk
        ttk.Label(self.mcp_tab, text='Connect your coding agent', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(self.mcp_tab, text='The app must be running. The bundled MCP executable discovers its current local port. Register only the clients you use.', wraplength=690).pack(anchor='w', pady=10)
        self.mcp_text = self.tk.Text(self.mcp_tab, height=11, wrap='word')
        self.mcp_text.pack(fill='both', expand=True)
        self.mcp_text.insert('1.0', json.dumps({'mcpServers': {'codebone': self.runtime.mcp_command()}}, indent=2))
        self.mcp_text.configure(state='disabled')
        row = ttk.Frame(self.mcp_tab); row.pack(fill='x')
        self.button(row, 'Copy configuration', self.copy_mcp)
        self.button(row, 'Register Cursor', lambda: self.register_mcp(Path.home() / '.cursor' / 'mcp.json'))
        claude_dir = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming')) / 'Claude'
        self.button(row, 'Register Claude Desktop', lambda: self.register_mcp(claude_dir / 'claude_desktop_config.json'))
        ttk.Label(self.mcp_tab, text='For Codex or other clients, add the displayed command and args in their MCP settings. Existing JSON configuration is backed up before registration.', wraplength=690).pack(anchor='w', pady=8)

    def copy_mcp(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.mcp_text.get('1.0', 'end').strip())
        self.status.set('MCP configuration copied')

    def register_mcp(self, path):
        from tkinter import messagebox
        if messagebox.askyesno('Connect coding agent', f'Add codebone to {path}? Restart the client afterwards.', parent=self.root):
            self.submit('Registering MCP bridge', lambda: self.runtime.register_mcp(path))

    def build_about(self):
        ttk = self.ttk
        ttk.Label(self.about_tab, text=f'codebone {__version__}', font=('Segoe UI', 22, 'bold')).pack(anchor='w', pady=12)
        ttk.Label(self.about_tab, text='Local architecture graph for coding agents.\nWindows x64 desktop app with CPU model support.\nClosing this window keeps codebone in the system tray.\nUse Quit to stop the local service.', wraplength=680).pack(anchor='w', pady=10)
        row = ttk.Frame(self.about_tab); row.pack(fill='x')
        self.button(row, 'Check for updates', self.check_updates)
        self.button(row, 'Open logs', self.open_logs)
        self.button(row, 'Report an issue', lambda: webbrowser.open('https://github.com/palusc/codebone/issues/new'))
        self.button(row, 'Quit codebone', self.quit)
        ttk.Label(self.about_tab, text='To uninstall an installed copy, use Windows Settings → Apps. Portable copies can be removed after quitting. Project folders are never deleted. Local data is kept in %LOCALAPPDATA%\\codebone.', wraplength=690).pack(anchor='w', pady=18)

    def open_logs(self):
        from .logging_setup import LOG_DIR
        os.startfile(str(LOG_DIR))

    def check_updates(self):
        from .updater import check_for_updates
        def check():
            result = check_for_updates()
            if result.get('error'):
                raise RuntimeError(result['error'])
            self.events.put(('update', result))
        self.submit('Checking for updates', check)

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def poll(self):
        from tkinter import messagebox
        if self.closed:
            return
        try:
            while True:
                event, data = self.events.get_nowait()
                if event == 'quit':
                    self.quit(); return
                if event == 'show': self.show()
                elif event == 'graph': self.open_graph()
                elif event == 'scan': self.scan()
                elif event == 'pause': self.pause()
                elif event == 'settings':
                    self.show(); self.notebook.select(self.settings_tab)
                elif event == 'status': self.status.set(data)
                elif event == 'error':
                    self.busy = False
                    self.status.set('Operation failed')
                    messagebox.showerror('codebone', data, parent=self.root)
                elif event == 'done':
                    self.busy = False
                    label, result = data
                    self.status.set(result if isinstance(result, str) else label + ' — done')
                    self.refresh_projects(); self.refresh_scans()
                elif event == 'update':
                    if data['update_available']:
                        if messagebox.askyesno('Update available', f"codebone {data['latest_version']} is available. Open the release download page?", parent=self.root):
                            webbrowser.open(data['html_url'])
                    else:
                        messagebox.showinfo('codebone', 'You are using the current release.', parent=self.root)
        except queue.Empty:
            pass
        progress = self.service.scan_progress
        if progress:
            self.status.set(f"{'Paused' if progress.get('paused') else 'Scanning'}: {progress.get('current', 0)}/{progress.get('total', 0)} files — {progress.get('pct', 0)}% — {progress.get('eta_str', '')}")
        self.root.after(150, self.poll)

    def quit(self):
        if self.closed:
            return
        self.closed = True
        self.tray.stop()
        self.service.cancel_scan()
        self.service.resume_scan()
        self.worker.shutdown(wait=False, cancel_futures=True)
        # Closing must finish after the active worker has released its database.
        self.root.withdraw()
        def close():
            self.worker.shutdown(wait=True)
            self.runtime.close()
            self.events.put(('closed', None))
        threading.Thread(target=close, daemon=True).start()
        def finish():
            try:
                event, _ = self.events.get_nowait()
                if event == 'closed':
                    self.root.destroy(); return
            except queue.Empty:
                pass
            self.root.after(100, finish)
        finish()

    def run(self):
        self.tray.run_detached()
        self.root.mainloop()


def acquire_instance_lock():
    """Prevent two desktop instances from sharing the same SQLite/config files."""
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, 'Local\\codebone-desktop')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)
        return None
    return handle


def main():
    parser = argparse.ArgumentParser(description='codebone Windows desktop')
    parser.add_argument('--smoke-test', type=Path)
    args = parser.parse_args()
    if args.smoke_test:
        from .windows_runtime import smoke_test
        try:
            smoke_test(args.smoke_test, gui=True)
        except Exception:
            import traceback
            args.smoke_test.write_text(json.dumps({'passed': False, 'error': traceback.format_exc()}), encoding='utf-8')
            raise
        return
    if sys.platform != 'win32':
        raise SystemExit('Use main.py for the macOS app; this entry point requires Windows.')
    lock = acquire_instance_lock()
    if lock is None:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, 'codebone is already running. Open it from the system tray.', 'codebone', 0)
        return
    from .logging_setup import configure_logging
    configure_logging()
    runtime = None
    try:
        runtime = DesktopRuntime()
        runtime.start()
        app = WindowsApp(runtime)
        if runtime.config.is_configured:
            app.submit('Scanning project', runtime.service.rescan_all)
        app.run()
    except Exception as exc:
        logger.exception('Desktop startup failed')
        if runtime:
            runtime.close()
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'codebone could not start', 0x10)
        raise
