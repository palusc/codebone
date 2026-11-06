import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from src import updater

SCRIPT = Path(__file__).parents[1] / 'bin/update.py'


def test_cli_updater_checks_installed_version_and_preserves_full_bundle():
    info = {'update_available': True, 'latest_version': '2.0c',
            'download_url': 'https://github.com/x/codebone-update.zip',
            'checksum_url': 'https://github.com/x/codebone-update.zip.sha256'}
    with patch.object(updater, '_bundle_version', return_value='2.0b'), \
         patch.object(updater, 'current_bundle', return_value=Path('/Applications/codebone.app')), \
         patch.object(updater, 'check_for_updates', return_value=info) as check, \
         patch.object(updater, 'download_and_install_update') as install:
        main = runpy.run_path(str(SCRIPT))['main']
        main()
        check.assert_called_once_with(current_version='2.0b')
        assert install.call_args.args == ('https://github.com/x/codebone.zip',)
        assert install.call_args.kwargs['checksum_url'] == 'https://github.com/x/codebone.zip.sha256'
        assert install.call_args.kwargs['expected_version'] == '2.0c'
        install.reset_mock()
        info.update(update_available=False, error='No connection')
        with pytest.raises(RuntimeError, match='No connection'):
            main()
        install.assert_not_called()
        info.pop('error')
        main()
        install.assert_not_called()
