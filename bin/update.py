"""Run the desktop app's existing verified updater from the terminal."""
import sys

from src.updater import (
    _bundle_version,
    check_for_updates,
    current_bundle,
    download_and_install_update,
)


def main():
    app = current_bundle()
    version = _bundle_version(app)
    if not version:
        raise RuntimeError('Install codebone.app in /Applications first.')
    print(f'Checking for updates (installed: {version})...', flush=True)
    info = check_for_updates(current_version=version)
    if info.get('error'):
        raise RuntimeError(info['error'])
    if not info['update_available']:
        print(f'codebone {version} is up to date.')
        return
    if not info.get('download_url') or not info.get('checksum_url'):
        raise RuntimeError('The release has no verified macOS update package.')
    # Cached models can link into the app bundle, so keep the full bundle's model.
    download_and_install_update(
        info['download_url'].replace('-update.zip', '.zip'),
        target_app_path=str(app),
        expected_version=info['latest_version'],
        checksum_url=info['checksum_url'].replace('-update.zip', '.zip'),
        progress_callback=lambda message: print(message, flush=True),
    )
    print(f"Installed codebone {info['latest_version']}. Quit and reopen the app to use it.")


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Update failed: {exc}', file=sys.stderr)
        sys.exit(1)
