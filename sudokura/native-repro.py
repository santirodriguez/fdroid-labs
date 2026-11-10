#!/usr/bin/env python3
"""Lab-only post-scan native path flags with compile-command verification.

Do not use this script on the maintained Sudokura source branch or in
production. The F-Droid scanner must run before the temporary CMake change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys

SOURCE_BLOB = 'a1c3334e9f35627c2a8dcde2744f6dbc11642e08'
CMAKE_ANCHOR = 'project(SudokuraAndroid C)\n'
SOURCE_ROOT = '/work/fdroid/build/org.cajapersonal.sudokura'
CANONICAL_CMAKE_PATH = Path(SOURCE_ROOT) / 'android/app/src/main/cpp/CMakeLists.txt'
ORIGINAL_ROOT = '/home/runner/work/Sudokura/Sudokura'
FLAGS = (
    f'-ffile-prefix-map={SOURCE_ROOT}={ORIGINAL_ROOT}',
    '-ffile-prefix-map=/opt/android-sdk=/usr/local/lib/android/sdk',
    '-fdebug-compilation-dir=/home/runner/work/Sudokura/Sudokura/android/app/.cxx/RelWithDebInfo/61k4uzg3/arm64-v8a',
)
CMAKE_PATCH = (
    '# Lab-only native path normalization applied after F-Droid source scanning.\n'
    'set(CMAKE_EXPORT_COMPILE_COMMANDS ON)\n'
    'add_compile_options(\n'
    + ''.join(f'  "{flag}"\n' for flag in FLAGS)
    + ')\n'
)
GROUPS = ('main', 'SDL2', 'SDL2_ttf', 'SDL2_mixer')


def git_blob_sha(data):
    header = f'blob {len(data)}\0'.encode('ascii')
    return hashlib.sha1(header + data).hexdigest()


def patch_cmake(data):
    if git_blob_sha(data) != SOURCE_BLOB:
        raise ValueError('CMake file is not the exact reviewed Sudokura b057 source blob')
    text = data.decode('utf-8')
    if text.count(CMAKE_ANCHOR) != 1:
        raise ValueError('Missing or duplicated canonical CMake project anchor')
    return text.replace(CMAKE_ANCHOR, CMAKE_ANCHOR + '\n' + CMAKE_PATCH, 1).encode('utf-8')


def apply(path):
    if path != CANONICAL_CMAKE_PATH:
        raise ValueError('Expected canonical absolute lab checkout CMake path')
    if path.is_symlink():
        raise ValueError('Canonical CMake file must not be a symlink')
    path.write_bytes(patch_cmake(path.read_bytes()))
    print('Post-scan lab-only CMake compile flags injected into canonical source')


def group_for(source):
    source = source.replace('\\', '/')
    if source.startswith(SOURCE_ROOT + '/src/') or source.startswith(SOURCE_ROOT + '/android/app/src/main/cpp/'):
        return 'main'
    for group, suffix in (('SDL2', 'SDL2-2.32.10'),
                          ('SDL2_ttf', 'SDL2_ttf-2.24.0'),
                          ('SDL2_mixer', 'SDL2_mixer-2.8.1')):
        if (SOURCE_ROOT + '/android/.cache/source/' + suffix + '/') in source:
            return group
    return None


def verify(root):
    if root.name != '.cxx':
        raise ValueError('Expected only the actual Gradle native build .cxx directory')
    paths = sorted(p for p in root.rglob('compile_commands.json')
                   if 'arm64-v8a' in p.parts)
    if not paths:
        raise ValueError('No ARM64 native compiler command database was generated')
    found = {group: 0 for group in GROUPS}
    checked = 0
    for path in paths:
        records = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(records, list):
            raise ValueError('Malformed native compile_commands.json')
        for record in records:
            group = group_for(record.get('file', ''))
            if group is None:
                continue
            arguments = record.get('arguments')
            if arguments is None:
                arguments = shlex.split(record.get('command', ''))
            if not isinstance(arguments, list):
                raise ValueError('Invalid native compilation command')
            absent = [flag for flag in FLAGS if flag not in arguments]
            if absent:
                raise ValueError(f'Missing compiler flags in {group}: {", ".join(absent)}')
            found[group] += 1
            checked += 1
    missing = [group for group, count in found.items() if not count]
    if missing:
        raise ValueError('Missing native target compile evidence for: ' + ', '.join(missing))
    print(f'Native compiler flags present in {checked} commands: ' + repr(found))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('apply', 'verify'))
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    try:
        if args.operation == 'apply':
            apply(args.path)
        else:
            verify(args.path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Native reproducibility gate FAILED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
