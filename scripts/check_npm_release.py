"""Allow release retries only when an existing npm version has identical contents."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.error
import urllib.request


def already_published(package_dir: Path) -> bool:
    package = json.loads((package_dir / 'package.json').read_text(encoding='utf-8'))
    name, version = package['name'], package['version']
    if name != 'xcbone':
        raise ValueError('Unexpected npm package name')
    try:
        with urllib.request.urlopen(f'https://registry.npmjs.org/{name}/{version}', timeout=30) as response:
            published = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    # The registry's canonical tarball stays on the official HTTPS destination.
    url = f'https://registry.npmjs.org/{name}/-/{name}-{version}.tgz'
    with urllib.request.urlopen(url, timeout=30) as response:
        archive = response.read(1_000_001)
    if len(archive) > 1_000_000:
        raise ValueError('Unexpectedly large npm distribution')
    integrity = 'sha512-' + base64.b64encode(hashlib.sha512(archive).digest()).decode('ascii')
    if integrity != published['dist']['integrity']:
        raise ValueError('Registry tarball integrity mismatch')
    expected = {'package.json', 'README.md', 'LICENSE', 'bin/cbone.js'}
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        members = [m for m in tar.getmembers() if not m.isdir()]
        if {m.name for m in members} != {'package/' + p for p in expected}:
            raise ValueError('Existing npm version has unexpected files')
        for member in members:
            if not member.isfile() or member.size > 100_000:
                raise ValueError('Unexpected npm tar entry')
            contents = tar.extractfile(member).read()
            filename = member.name.removeprefix('package/')
            local = (package_dir / filename).read_bytes()
            same = json.loads(contents) == json.loads(local) if filename == 'package.json' else contents == local
            if not same:
                raise ValueError(f'{name}@{version} already exists with different {filename}; choose a new version')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('package_dir', type=Path)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    present = already_published(args.package_dir)
    print('Identical npm version is already published' if present else 'npm version is not yet published')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as output:
            output.write(f'already_published={str(present).lower()}\n')
