#!/usr/bin/env python3
"""Fail-closed payload comparison against the previously verified b057 APK.

Only hashes are retained. No signature, font or native library from the reference
APK is used as a build input. Payload equality is NOT signature verification.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

SOURCE_SHA = 'b057341c84cd988cd15b3329507aaa6151449f5b'
SIGNED_APK_SHA256 = '06e06d8b8301384a37876b978d0fb18552b3601487628e7465e1cec33a3836b4'
PAYLOAD_SHA256 = '38fbe54ab483ce0f445e94df3ccd46cf346dd3a9dabeed1eb77d51b0f2908307'
FONT_SHA256 = 'ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280'
FONT_LICENSE_SHA256 = '63d3ba759d12804c5b31a9d5940d855c1820d1f5999e6b0872eb1c7ff045fbc9'
EXPECTED_MEMBERS = 28
SIGNATURE_FILE = re.compile(r'META-INF/(?:[^/]+\.(?:SF|RSA|DSA|EC)|MANIFEST\.MF)', re.I)
EXPECTED_FOCUS = {
    'assets/DejaVuSans.ttf': FONT_SHA256,
    'lib/arm64-v8a/libSDL2.so': '14d959272f232292e0d429e12125967b5be7f454879e97d4b5c64618260962e0',
    'lib/arm64-v8a/libSDL2_mixer.so': 'c0861cb239065e6d8778d9136d5b5720a782a2f1b67848f739a7538c10d2a743',
    'lib/arm64-v8a/libSDL2_ttf.so': '1f4f32a0953d5d61e59db773d7fb3f8d80bcaec38c0082df41e812a4cff7fa15',
    'lib/arm64-v8a/libmain.so': 'be51ea60db03827c29e627638b0e664c23d9ac1b7012e594c17b8b907f303d31',
}


def inventory(apk):
    rows = []
    with zipfile.ZipFile(apk) as archive:
        infos = archive.infolist()
        names = [entry.filename for entry in infos]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate APK entries')
        if sum(entry.file_size for entry in infos) > 64 * 1024 * 1024:
            raise ValueError('Unexpected APK expansion size')
        for entry in infos:
            name = entry.filename
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                raise ValueError('Unsafe APK entry path')
            if entry.is_dir():
                raise ValueError('Unexpected APK directory entry')
            if SIGNATURE_FILE.fullmatch(name):
                raise ValueError('Expected a source-built unsigned APK')
            content = archive.read(entry)
            rows.append([name, len(content), hashlib.sha256(content).hexdigest()])
    rows.sort()
    digest = hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()
    return rows, digest


def compare(apk):
    rows, digest = inventory(apk)
    hashes = {row[0]: row[2] for row in rows}
    return {
        'source_sha': SOURCE_SHA,
        'reference_signed_apk_sha256': SIGNED_APK_SHA256,
        'unsigned_apk_sha256': hashlib.sha256(Path(apk).read_bytes()).hexdigest(),
        'member_count': len(rows),
        'payload_sha256': digest,
        'expected_payload_sha256': PAYLOAD_SHA256,
        'payload_match': len(rows) == EXPECTED_MEMBERS and digest == PAYLOAD_SHA256,
        'focus_mismatches': {name: {'expected': sha, 'actual': hashes.get(name)}
                             for name, sha in EXPECTED_FOCUS.items() if hashes.get(name) != sha},
        'members': rows,
        'signature_verification': 'NOT_RUN_REQUIRES_SEPARATE_SIGNATURE_COPY_CHECK',
        'official_fdroid_acceptance': 'NOT_TESTED',
    }


def check_font(font, license_file):
    for path, expected in ((font, FONT_SHA256), (license_file, FONT_LICENSE_SHA256)):
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Pinned font input differs: {Path(path).name}: {actual}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    font = commands.add_parser('font')
    font.add_argument('font', type=Path)
    font.add_argument('license_file', type=Path)
    apk = commands.add_parser('apk')
    apk.add_argument('apk', type=Path)
    apk.add_argument('report', type=Path)
    args = parser.parse_args()
    if args.mode == 'font':
        check_font(args.font, args.license_file)
        print('Pinned Ubuntu font and original license: PASS')
        return 0
    report = compare(args.apk)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'members'}, indent=2))
    return 0 if report['payload_match'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print(f'Reproducibility check blocked: {error}', file=sys.stderr)
        sys.exit(2)
