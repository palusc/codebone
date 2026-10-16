"""Stage the npm distribution with its own README, without changing app docs."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def stage(destination: Path):
    destination = destination.resolve()
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError('Choose a separate distribution directory')
    # Never erase a pre-existing directory containing user files.
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'bin').mkdir()
    metadata = json.loads((ROOT / 'package.json').read_text())
    metadata.pop('scripts', None)  # development-only test script is not shipped
    (destination / 'package.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    for source, target in [('bin/cbone.js', 'bin/cbone.js'), ('LICENSE', 'LICENSE'), ('docs/npm.md', 'README.md')]:
        shutil.copy2(ROOT / source, destination / target)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    print(stage(parser.parse_args().destination))
