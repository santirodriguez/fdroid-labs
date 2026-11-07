#!/usr/bin/env python3
"""Stage verified Android archives and restore them after an offline F-Droid checkout.

The public Gradle/SDL archives are pinned by Sudokura's committed dependency
lock; no URL download, trust-on-first-use cache marker, or external repository
access is performed by this helper.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

EXPECTED_NAMES = frozenset({'SDL2', 'SDL2_ttf', 'SDL2_mixer', 'Gradle'})


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def load_lock(path):
    require(path.is_file() and not path.is_symlink(), 'Committed lock file is missing')
    lock = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(lock, dict) and lock.keys() == EXPECTED_NAMES,
            'Expected exactly three SDL archives and pinned Gradle')
    for name, entry in lock.items():
        require(isinstance(entry, dict), f'Invalid lock entry {name}')
        archive = entry.get('archive')
        digest = entry.get('sha256')
        require(isinstance(archive, str) and archive == Path(archive).name
                and not archive.startswith('.') and not any(c in archive for c in '/\\'),
                f'Unsafe archive filename for {name}')
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest),
                f'Invalid locked hash for {name}')
    return lock


def verify_archive(path, expected):
    require(path.is_file() and not path.is_symlink(), f'Missing verified archive: {path.name}')
    require(sha256(path) == expected, f'Locked SHA-256 mismatch: {path.name}')


def ensure_revision(android, commit):
    require(re.fullmatch(r'[0-9a-f]{40}', commit) is not None,
            'Invalid immutable Git revision')
    process = subprocess.run(['git', '-C', str(android.parent), 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, check=False)
    require(process.returncode == 0 and process.stdout.strip() == commit,
            'Android source checkout differs from verified immutable Git revision')


def stage(android, archive_dir, commit):
    ensure_revision(android, commit)
    lockfile = android / 'dependencies.lock.json'
    lock = load_lock(lockfile)
    download_dir = android / '.cache' / 'downloads'
    require(download_dir.is_dir() and not download_dir.is_symlink(),
            'Host verified download cache is missing')
    require(not archive_dir.exists(), 'Staging directory must be new')
    archive_dir.mkdir(parents=True)
    for name, entry in lock.items():
        source = download_dir / entry['archive']
        dest = archive_dir / entry['archive']
        verify_archive(source, entry['sha256'])
        shutil.copyfile(source, dest)
        verify_archive(dest, entry['sha256'])
        print(f'staged {name} sha256={entry["sha256"]}')
    shutil.copyfile(lockfile, archive_dir / 'dependencies.lock.json')
    verify_staged(lockfile, archive_dir, lock)


def verify_staged(lockfile, archive_dir, lock):
    staged_lock = archive_dir / 'dependencies.lock.json'
    require(staged_lock.is_file() and not staged_lock.is_symlink(),
            'Staged lock is missing')
    require(staged_lock.read_bytes() == lockfile.read_bytes(),
            'Staged dependency lock differs from immutable checkout')
    expected_files = {'dependencies.lock.json'} | {x['archive'] for x in lock.values()}
    require({p.name for p in archive_dir.iterdir()} == expected_files,
            'Unexpected, incomplete or modified staged input set')
    for entry in lock.values():
        verify_archive(archive_dir / entry['archive'], entry['sha256'])


def restore(android, archive_dir, commit):
    ensure_revision(android, commit)
    lockfile = android / 'dependencies.lock.json'
    lock = load_lock(lockfile)
    verify_staged(lockfile, archive_dir, lock)
    downloads = android / '.cache' / 'downloads'
    require(not downloads.is_symlink() and not downloads.parent.is_symlink(),
            'Untrusted Android cache symlink')
    downloads.mkdir(parents=True, exist_ok=True)
    for name, entry in lock.items():
        path = downloads / entry['archive']
        if path.exists() or path.is_symlink():
            verify_archive(path, entry['sha256'])
        else:
            shutil.copyfile(archive_dir / entry['archive'], path)
            verify_archive(path, entry['sha256'])
        print(f'offline {name} sha256={entry["sha256"]}')
    # Run the ORIGINAL source preparer on the actual F-Droid checkout.
    # Every download is already staged by its exact locked SHA-256.
    preparer = android / 'scripts' / 'prepare_sources.py'
    require(preparer.is_file(), 'Committed source preparer is absent')
    subprocess.run([sys.executable, str(preparer)], cwd=android, check=True)
    for name, entry in lock.items():
        group = 'gradle' if name == 'Gradle' else 'source'
        extracted = android / '.cache' / group / entry['directory']
        marker = extracted / '.sudokura-source-sha256'
        require(marker.is_file() and marker.read_text(encoding='utf-8').strip() == entry['sha256'],
                f'Verified extraction missing for {name}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['stage', 'restore'])
    ap.add_argument('android', type=Path)
    ap.add_argument('archives', type=Path)
    ap.add_argument('commit')
    args = ap.parse_args()
    if args.mode == 'stage':
        stage(args.android.resolve(), args.archives.absolute(), args.commit)
    else:
        restore(args.android.resolve(), args.archives.resolve(), args.commit)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f'OFFLINE INPUTS BLOCKED: {e}', file=sys.stderr)
        sys.exit(1)
