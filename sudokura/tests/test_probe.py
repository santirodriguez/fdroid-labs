"""Offline, local-only fault injection for the GitHub-owned F-Droid test harness."""

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('verify_probe', ROOT / 'verify-probe.py')
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class ProbeChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_scanner_requires_genuine_zero_problems(self):
        good = (f'2026-11-07 INFO: Processing {VERIFY.APP_ID}\n'
                '2026-11-07 INFO: ...scanning version 1.4.0\n'
                f'2026-11-07 INFO: Getting source for revision {VERIFY.EXPECTED_SHA}\n'
                '2026-11-07 INFO: Finished\n0 problems found\n')
        VERIFY.verify_scanner(self.write('scanner.log', good))
        failures = [
            good.replace('0 problems found', '1 problems found'),
            good.replace('0 problems found', ''),
            good.replace('0 problems found', '0 problems found\n1 problems found'),
            good.replace('0 problems found', '0 problems found\nWARNING: VCS error'),
            good.replace('...scanning version 1.4.0', '...skipped version 1.4.0'),
            good.replace(VERIFY.EXPECTED_SHA, '0' * 40),
        ]
        for value in failures:
            with self.subTest(value=value[-85:]):
                with self.assertRaises(VERIFY.VerificationError):
                    VERIFY.verify_scanner(self.write('scanner.log', value))

    def test_first_false_green_scanner_log_fails(self):
        log = ('INFO: Processing org.cajapersonal.sudokura\n'
               'INFO: ...scanning version 1.4.0\n'
               f'INFO: Getting source for revision {VERIFY.EXPECTED_SHA}\n'
               'WARNING: VCS error while scanning app: Git clone failed\n'
               'INFO: Finished\n1 problems found\n')
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify_scanner(self.write('scanner.log', log))

    def test_build_must_report_real_success(self):
        good = ('INFO: Successfully built version 1.4.0 of ' + VERIFY.APP_ID + ' from ' + VERIFY.EXPECTED_SHA + '\n'
                'INFO: Finished\n1 build succeeded\n')
        VERIFY.verify_build(self.write('build.log', good))
        for bad in [
            'INFO: Finished\n1 build failed\n',
            good + 'INFO: 1 build failed\n',
            good.replace('1 build succeeded', '0 builds succeeded'),
            'ERROR: Traceback\n1 build succeeded\n',
            good.replace('Successfully built version 1.4.0', 'Failed building version 1.4.0'),
        ]:
            with self.subTest(bad=bad[-75:]):
                with self.assertRaises(VERIFY.VerificationError):
                    VERIFY.verify_build(self.write('build.log', bad))

    def test_unsigned_apk_is_required_and_package_checked(self):
        apk = self.root / 'org.cajapersonal.sudokura_1.apk'
        receipt = self.root / 'receipt.txt'
        aapt = self.root / 'aapt'
        self.write('aapt', "#!/bin/sh\necho \"package: name='org.cajapersonal.sudokura' versionCode='1' versionName='1.4.0'\"\n")
        aapt.chmod(aapt.stat().st_mode | stat.S_IEXEC)
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify_apk(apk, aapt, receipt)
        with zipfile.ZipFile(apk, 'w', compression=zipfile.ZIP_STORED) as zipped:
            zipped.writestr('AndroidManifest.xml', 'fake manifest for local fault injection')
            zipped.writestr('classes.dex', 'fake' * 100)
        VERIFY.verify_apk(apk, aapt, receipt)
        self.assertIn('version_code=1', receipt.read_text())
        self.assertIn('artifact_upload=DISABLED', receipt.read_text())
        aapt.write_text("#!/bin/sh\necho \"package: name='org.cajapersonal.sudokura' versionCode='2' versionName='1.4.0'\"\n")
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify_apk(apk, aapt, receipt)

    def test_stage_source_from_detached_local_checkout_only(self):
        origin = self.root / 'origin'
        origin.mkdir()
        def git(*args):
            return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout.strip()
        git('init', '-q', str(origin))
        git('-C', str(origin), 'config', 'user.name', 'Test Only')
        git('-C', str(origin), 'config', 'user.email', 'test@example.invalid')
        (origin / 'README.md').write_text('test source')
        git('-C', str(origin), 'add', 'README.md')
        git('-C', str(origin), 'commit', '-qm', 'initial test source')
        sha = git('-C', str(origin), 'rev-parse', 'HEAD')
        git('-C', str(origin), 'checkout', '-q', '--detach', sha)
        scratch = self.root / 'work'
        scratch.mkdir()
        template = self.write('template.yml', 'RepoType: git\nRepo: https://github.com/santirodriguez/Sudokura.git\n    commit: ' + sha + '\n')
        subprocess.run(['bash', str(ROOT / 'stage-offline-git.sh'), str(origin), str(scratch),
                        str(template), sha], check=True, capture_output=True, text=True)
        mirror = scratch / 'mirror' / 'sudokura.git'
        self.assertEqual(git('--git-dir=' + str(mirror), 'rev-parse', 'HEAD'), sha)
        self.assertIn('Repo: file:///work/fdroid/mirror/sudokura.git',
                      (scratch / 'metadata' / (VERIFY.APP_ID + '.yml')).read_text())
        self.assertIn('Repo: https://github.com/santirodriguez/Sudokura.git', template.read_text())
        # Confirm that a genuine file:// Git clone works without network access.
        checkout = scratch / 'build' / VERIFY.APP_ID
        git('clone', '-q', 'file://' + str(mirror), str(checkout))
        self.assertEqual(git('-C', str(checkout), 'rev-parse', 'HEAD'), sha)
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.run(['bash', str(ROOT / 'stage-offline-git.sh'), str(origin), str(scratch),
                            str(template), sha], check=True, capture_output=True, text=True)

    def test_stage_from_shallow_detached_checkout(self):
        def git(*args):
            return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout.strip()
        origin = self.root / 'origin'
        origin.mkdir()
        git('init', '-q', str(origin))
        git('-C', str(origin), 'config', 'user.name', 'Test Only')
        git('-C', str(origin), 'config', 'user.email', 'test@example.invalid')
        (origin / 'source.c').write_text('int test = 1;\n')
        git('-C', str(origin), 'add', '.')
        git('-C', str(origin), 'commit', '-qm', 'first')
        (origin / 'source.c').write_text('int test = 2;\n')
        git('-C', str(origin), 'commit', '-qam', 'second')
        detached = self.root / 'detached'
        git('clone', '-q', '--depth', '1', 'file://' + str(origin), str(detached))
        commit = git('-C', str(detached), 'rev-parse', 'HEAD')
        git('-C', str(detached), 'checkout', '-q', '--detach', commit)
        self.assertEqual(git('-C', str(detached), 'rev-parse', '--is-shallow-repository'), 'true')
        work = self.root / 'work'
        work.mkdir()
        template = self.write('template.yml',
                              'Repo: https://github.com/santirodriguez/Sudokura.git\n    commit: ' + commit + '\n')
        subprocess.run(['bash', str(ROOT / 'stage-offline-git.sh'), str(detached), str(work),
                        str(template), commit], capture_output=True, text=True, check=True)
        self.assertEqual(git('--git-dir=' + str(work / 'mirror' / 'sudokura.git'),
                             'rev-parse', 'HEAD'), commit)

    def test_stage_requires_exact_immutable_commit(self):
        source = self.root / 'source'
        source.mkdir()
        work = self.root / 'work'
        work.mkdir()
        metadata = self.write('template.yml', 'Repo: https://github.com/santirodriguez/Sudokura.git\n')
        proc = subprocess.run(['bash', str(ROOT / 'stage-offline-git.sh'), str(source), str(work),
                               str(metadata), '0' * 40], capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((work / 'mirror').exists())


if __name__ == '__main__':
    unittest.main()
