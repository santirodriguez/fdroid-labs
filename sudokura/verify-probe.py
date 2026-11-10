#!/usr/bin/env python3
"""Fail-closed verification of the disposable offline F-Droid experiment.

GitHub job success is never treated as proof of an independently built APK.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

APP_ID = 'org.cajapersonal.sudokura'
EXPECTED_SHA = 'b057341c84cd988cd15b3329507aaa6151449f5b'
LOCAL_REPO = 'file:///work/fdroid/mirror/sudokura.git'
ERRORS = re.compile(r'(?im)\b(?:WARNING|ERROR|CRITICAL|Traceback|Could not scan|VCS error)\b')


class VerificationError(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise VerificationError(reason)


def git_value(*args):
    p = subprocess.run(['git', *args], capture_output=True, text=True, check=False)
    require(p.returncode == 0, 'Git verification failed: ' + p.stderr.strip())
    return p.stdout.strip()


def verify_source(root):
    root = Path(root)
    mirror = root / 'mirror' / 'sudokura.git'
    checkout = root / 'build' / APP_ID
    meta = root / 'metadata' / (APP_ID + '.yml')
    require(meta.is_file(), 'Local test metadata is missing')
    require(meta.read_text(encoding='utf-8').count('Repo: ' + LOCAL_REPO) == 1,
            'Local-only source URL is not the verified mirror')
    require(mirror.is_dir(), 'Source mirror is missing')
    require(git_value('--git-dir=' + str(mirror), 'rev-parse', 'HEAD') == EXPECTED_SHA,
            'Source mirror commit mismatch')
    require((checkout / '.git').exists(), 'fdroidserver did not clone the local source')
    require(git_value('-C', str(checkout), 'rev-parse', 'HEAD') == EXPECTED_SHA,
            'F-Droid checkout commit mismatch')
    require(git_value('-C', str(checkout), 'rev-parse', '--show-toplevel') == str(checkout.resolve()),
            'F-Droid checkout is not a separate repository')
    require(git_value('-C', str(checkout), 'remote', 'get-url', 'origin') == LOCAL_REPO,
            'F-Droid source checkout has an unexpected network remote')
    provenance = root / 'build' / ('.fdroidvcs-' + APP_ID)
    require(provenance.is_file(), 'fdroidserver did not create its VCS identity')
    require(provenance.read_text(encoding='utf-8').strip() == 'git ' + LOCAL_REPO,
            'F-Droid generated VCS identity is inconsistent')
    require(git_value('-C', str(checkout), 'rev-parse', 'HEAD^{tree}') ==
            git_value('--git-dir=' + str(mirror), 'rev-parse', 'HEAD^{tree}'),
            'F-Droid source tree does not match the verified mirror')


def verify_scanner(log):
    text = Path(log).read_text(encoding='utf-8')
    require('Processing ' + APP_ID in text, 'Source scanner did not process Sudokura')
    require('scanning version 1.4.1' in text, 'Source scanner did not scan the selected version')
    require('Getting source for revision ' + EXPECTED_SHA in text,
            'Source scanner did not request the verified commit')
    require(not ERRORS.search(text), 'Scanner logged a warning, error, or traceback')
    counts = re.findall(r'(?m)^\s*(\d+) problems? found\s*$', text)
    require(counts == ['0'], 'Scanner did not explicitly report exactly zero problems')
    require(re.search(r'(?m)\bINFO: Finished\s*$', text) is not None,
            'Source scanner did not finish')


def verify_build(log):
    text = Path(log).read_text(encoding='utf-8')
    require(not ERRORS.search(text), 'Build logged a warning, error, or traceback')
    require(re.search(r'(?m)^(?:.*?\bINFO:\s*)?1 build succeeded\s*$', text) is not None,
            'F-Droid did not explicitly report exactly one successful build')
    require(re.search(r'(?m)^(?:.*?\bINFO:\s*)?\d+ builds? failed\s*$', text) is None,
            'F-Droid reported a failed build')
    require('Successfully built version 1.4.1' in text,
            'F-Droid did not report a source-bound application build')


def verify_apk(apk, aapt, receipt, notice_source):
    apk = Path(apk)
    require(apk.is_file() and apk.stat().st_size > 128,
            'Expected F-Droid test-mode unsigned APK was not produced')
    require(zipfile.is_zipfile(apk), 'APK is not a ZIP archive')
    notice_source = Path(notice_source)
    require(notice_source.is_file() and not notice_source.is_symlink(),
            'Exact Git source flag-icons MIT notice missing')
    notice = notice_source.read_bytes()
    require(b'Copyright (c) 2013 Panayiotis Lipiridis' in notice
            and b'Permission is hereby granted' in notice and b'\r' not in notice,
            'Canonical flag-icons attribution is invalid')
    with zipfile.ZipFile(apk) as z:
        require(z.testzip() is None, 'APK ZIP contents failed CRC verification')
        require('AndroidManifest.xml' in z.namelist(), 'APK has no Android manifest')
        member = 'assets/licenses/flag-icons-MIT.txt'
        require(member in z.namelist(), 'APK is missing flag-icons MIT license')
        require(z.read(member) == notice, 'APK flag-icons MIT license differs from exact Git source')
        require(not any(re.fullmatch(r'META-INF/[^/]+\.(?:SF|RSA|DSA|EC)', name, re.I)
                        for name in z.namelist()), 'Unexpected JAR signing artifacts in unsigned APK')
    aapt = Path(aapt)
    require(aapt.is_file() and os.access(aapt, os.X_OK), 'Pinned Android aapt is unavailable')
    p = subprocess.run([str(aapt), 'dump', 'badging', str(apk)],
                       capture_output=True, text=True, check=False)
    require(p.returncode == 0, 'aapt could not validate the APK: ' + p.stderr.strip())
    match = re.search(r"(?m)^package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", p.stdout)
    require(match is not None, 'No parseable package identity in aapt output')
    require(match.groups() == (APP_ID, '2', '1.4.1'), 'Unexpected package identity or version')
    sha = hashlib.sha256()
    with apk.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            sha.update(block)
    receipt = Path(receipt)
    receipt.write_text('apk_sha256=' + sha.hexdigest() + '\n'
                       'app_id=' + APP_ID + '\nversion_code=2\nversion_name=1.4.1\n'
                       'source_sha=' + EXPECTED_SHA + '\n'
                       'artifact_upload=PLANNED_GITHUB_TEST_ONLY\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('check', choices=['source', 'scanner', 'build', 'apk'])
    parser.add_argument('target')
    parser.add_argument('--aapt')
    parser.add_argument('--receipt')
    parser.add_argument('--notice-source')
    opts = parser.parse_args()
    try:
        if opts.check == 'source':
            verify_source(opts.target)
        elif opts.check == 'scanner':
            verify_scanner(opts.target)
        elif opts.check == 'build':
            verify_build(opts.target)
        else:
            require(bool(opts.aapt and opts.receipt and opts.notice_source),
                    'APK check needs --aapt, --receipt and --notice-source')
            verify_apk(opts.target, opts.aapt, opts.receipt, opts.notice_source)
    except (VerificationError, OSError, ValueError, zipfile.BadZipFile) as error:
        print('PROBE VERIFICATION FAILED: ' + str(error), file=sys.stderr)
        return 1
    print('PROBE VERIFICATION PASS: ' + opts.check)
    return 0


if __name__ == '__main__':
    sys.exit(main())
