"""Exercise the native dialog handler without loading the menu-bar app."""
import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import modules


def test_model_form_keeps_values_on_retry_and_does_not_save_on_cancel():
    tree = ast.parse((Path(__file__).parents[1] / 'src' / 'app.py').read_text())
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'add_module_dialog')
    namespace = {name: MagicMock() for name in (
        'NSApplication', 'NSAlert', 'NSView', 'NSRect', 'NSPoint', 'NSSize',
        'NSTextField', 'NSSecureTextField', 'NSFont', 'NSColor', 'rumps',
    )}
    namespace.update(__name__='src.app', __package__='src')
    exec(compile(ast.Module(body=[handler], type_ignores=[]), '<dialog>', 'exec'), namespace)
    alert = namespace['NSAlert'].alloc().init()
    values = ['My provider', 'my-model', '', 'https://example.com/v1', 'test-key']
    fields = [MagicMock() for _ in values]
    for field, value in zip(fields, values):
        field.stringValue.return_value = value
    namespace['NSTextField'].alloc().initWithFrame_.side_effect = fields[:4] * 2
    secure_field = namespace['NSSecureTextField'].alloc().initWithFrame_
    secure_field.return_value = fields[4]
    app = MagicMock()
    with patch.object(modules, 'add_module', side_effect=[ValueError('Try again'), {'id': 'test'}]) as add:
        alert.runModal.side_effect = [1000, 1000]
        namespace['add_module_dialog'](app, None)
        assert add.call_count == 2
        assert add.call_args.args[1:] == tuple(values[i] for i in (0, 1, 4, 2, 3))
        secure_field.assert_called_once()
        app._check_module.assert_called_once_with({'id': 'test'}, 'test-key')
    with patch.object(modules, 'add_module') as add:
        alert.runModal.side_effect = [1001]
        namespace['add_module_dialog'](app, None)
        add.assert_not_called()
