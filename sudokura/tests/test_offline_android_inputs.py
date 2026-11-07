"""Local, no-network fault injection for locked Android source staging."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('offline_android_inputs', ROOT / 'offline-android-inputs.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class OfflineAndroidInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.src = self.base / 'src'
        self.android = self.src / 'android'
        self.downloads = self.android / '.cache' / 'downloads'
        self.downloads.mkdir(parents=True)
        (self.android / 'scripts').mkdir(parents=True)
        self.archives = self.base / 'staged'
        self.lock = {}
        for name in ('SDL2', 'SDL2_ttf', 'SDL2_mixer', 'Gradle'):
            archive = f'{name}-test.zip'
            data = f'archive bytes: {name}\n'.encode('utf-8')
            (self.downloads / archive).write_bytes(data)
            self.lock[name] = dict(archive=archive, sha256=hashlib.sha256(data).hexdigest(),
                                   directory=f'{name}-source', version='test')
        (self.android / 'dependencies.lock.json').write_text(json.dumps(self.lock), encoding='utf-8')
        (self.android / 'scripts' / 'prepare_sources.py').write_text(
            'import hashlib, json\nfrom pathlib import Path\n'
            'a=Path(__file__).resolve().parents[1]\n'
            'd=json.loads((a/"dependencies.lock.json").read_text())\n'
            'for name,e in d.items():\n'
            ' p=a/".cache"/"downloads"/e["archive"]\n'
            ' assert hashlib.sha256(p.read_bytes()).hexdigest()==e["sha256"]\n'
            ' root=a/".cache"/("gradle" if name=="Gradle" else "source")/e["directory"]\n'
            ' root.mkdir(parents=True,exist_ok=True)\n'
            ' (root/".sudokura-source-sha256").write_text(e["sha256"]+"\\n")\n',
            encoding='utf-8')
        subprocess.run(['git', 'init', '-q', str(self.src)], check=True)
        subprocess.run(['git', '-C', str(self.src), 'config', 'user.name', 'Fixture'], check=True)
        subprocess.run(['git', '-C', str(self.src), 'config', 'user.email', 'fixture@example.invalid'], check=True)
        subprocess.run(['git', '-C', str(self.src), 'add', 'android/dependencies.lock.json',
                        'android/scripts/prepare_sources.py'], check=True)
        subprocess.run(['git', '-C', str(self.src), 'commit', '-qm', 'fixture'], check=True)
        self.commit = subprocess.check_output(['git', '-C', str(self.src), 'rev-parse', 'HEAD'], text=True).strip()

    def stage(self):
        MOD.stage(self.android, self.archives, self.commit)

    def test_stage_and_repeated_offline_restore(self):
        self.stage()
        self.assertEqual(len(list(self.archives.iterdir())), 5)
        for path in self.downloads.iterdir():
            path.unlink()
        MOD.restore(self.android, self.archives, self.commit)
        MOD.restore(self.android, self.archives, self.commit)
        for entry in self.lock.values():
            self.assertTrue((self.downloads / entry['archive']).is_file())

    def test_missing_download_blocks_staging(self):
        (self.downloads / self.lock['SDL2']['archive']).unlink()
        with self.assertRaises(ValueError):
            self.stage()

    def test_corrupt_download_blocks_staging(self):
        (self.downloads / self.lock['Gradle']['archive']).write_text('tampered')
        with self.assertRaises(ValueError):
            self.stage()

    def test_tampered_staged_archive_blocks_restoration(self):
        self.stage()
        (self.archives / self.lock['SDL2_ttf']['archive']).write_text('tampered')
        with self.assertRaises(ValueError):
            MOD.restore(self.android, self.archives, self.commit)

    def test_tampered_external_lock_blocks_restoration(self):
        self.stage()
        (self.archives / 'dependencies.lock.json').write_text('malicious: yes')
        with self.assertRaises(ValueError):
            MOD.restore(self.android, self.archives, self.commit)

    def test_wrong_commit_blocks_staging_and_restore(self):
        with self.assertRaises(ValueError):
            MOD.stage(self.android, self.archives, '0' * 40)
        self.stage()
        with self.assertRaises(ValueError):
            MOD.restore(self.android, self.archives, '0' * 40)

    def test_unknown_archive_or_missing_archive_blocks_restoration(self):
        self.stage()
        (self.archives / 'extra.bin').write_text('extra')
        with self.assertRaises(ValueError):
            MOD.restore(self.android, self.archives, self.commit)
        (self.archives / 'extra.bin').unlink()
        (self.archives / self.lock['SDL2_mixer']['archive']).unlink()
        with self.assertRaises(ValueError):
            MOD.restore(self.android, self.archives, self.commit)

    def test_archive_symlink_is_not_trusted(self):
        self.stage()
        archived = self.archives / self.lock['Gradle']['archive']
        archived.unlink()
        archived.symlink_to(self.downloads / self.lock['Gradle']['archive'])
        with self.assertRaises(ValueError):
            MOD.restore(self.android, self.archives, self.commit)


if __name__ == '__main__':
    unittest.main()
