"""Validate the staged, unsubmitted official F-Droid metadata candidate offline."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

import yaml

CANDIDATE = Path(__file__).resolve().parents[1] / 'fdroiddata-candidate'
METADATA = CANDIDATE / 'metadata' / 'org.cajapersonal.sudokura.yml'
PATCH_DIR = CANDIDATE / 'metadata' / 'org.cajapersonal.sudokura'
APP_ID = 'org.cajapersonal.sudokura'
SOURCE_SHA = 'b057341c84cd988cd15b3329507aaa6151449f5b'
CERT_SHA = 'fde951e3d2ef42e41c7186ee965944aeca549d590ad080711dd3d875f82df66d'


class FdroiddataCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = yaml.safe_load(METADATA.read_text(encoding='utf-8'))
        cls.build = cls.metadata['Builds'][0]

    def test_public_developer_brand_and_project_websites(self):
        self.assertEqual(self.metadata['AuthorName'], 'Caja Personal')
        self.assertEqual(self.metadata['AuthorWebSite'], 'https://cajapersonal.org/')
        self.assertEqual(self.metadata['WebSite'], 'https://sudokura.cajapersonal.org/')
        self.assertEqual(self.metadata['AutoName'], 'Sudokura')
        self.assertEqual(self.metadata['Categories'], ['Puzzle Game'])
        self.assertEqual(
            self.metadata['Changelog'],
            'https://github.com/santirodriguez/Sudokura/blob/HEAD/CHANGELOG.md'
        )

    def test_source_binary_and_original_signer_identity(self):
        self.assertEqual(self.metadata['AllowedAPKSigningKeys'], CERT_SHA)
        self.assertEqual(self.metadata['Repo'], 'https://github.com/santirodriguez/Sudokura.git')
        self.assertEqual(self.build['commit'], SOURCE_SHA)
        self.assertEqual((self.build['versionName'], self.build['versionCode']), ('1.4.1', 2))
        self.assertTrue(self.build['binary'].endswith('/v1.4.1/Sudokura-1.4.1-Android-arm64.apk'))
        self.assertEqual(self.metadata['UpdateCheckMode'], 'None')
        self.assertEqual(self.metadata['AutoUpdateMode'], 'None')

    def test_no_undisclosed_lab_working_paths(self):
        text = METADATA.read_text(encoding='utf-8')
        self.assertEqual(self.build['subdir'], 'android')
        self.assertNotIn('gradle', self.build)  # Uses checked-out, checksum-pinned Gradle 8.13.
        self.assertEqual(self.build['patch'], ['native-paths.patch', 'signer35-align.patch', 'source-only.patch', 'pinned-font.patch'])
        for name in self.build['patch']:
            self.assertTrue((PATCH_DIR / name).is_file())
        for forbidden in ('/work/fdroid', '/work/verified-inputs', 'mirror/sudokura.git', 'docker run'):
            self.assertNotIn(forbidden, text)
        self.assertIn('prepare_sources.py --source-only', self.build['prebuild'][0])
        self.assertIn('prepare_sources.py --gradle-only', self.build['build'][0])
        self.assertEqual(self.build['sudo'], ['echo \'deb https://deb.debian.org/debian bookworm main\' > /etc/apt/sources.list.d/bookworm.list','apt-get update','apt-get install -y golang-go make','apt-get install -y -t bookworm openjdk-17-jdk-headless','update-java-alternatives -s java-1.17.0-openjdk-amd64'])
        self.assertEqual(self.build['prebuild'][-1], 'python3 scripts/fdroid_stage_font.py')
        self.assertIn('.cache/fdroid-font/DejaVuSans.ttf', self.build['build'][1])
        self.assertIn('.cache/fdroid-font/copyright', self.build['build'][2])
        self.assertIn('-PsudokuraFont=../.cache/fdroid-font/DejaVuSans.ttf', self.build['build'][-1])
        self.assertIn('-PsudokuraFontLicense=../.cache/fdroid-font/copyright', self.build['build'][-1])
        self.assertEqual(self.build['build'][-4], 'make -C .. assets')
        self.assertEqual(self.build['build'][-3], 'export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64')
        self.assertEqual(self.build['build'][-2], 'test -x "$JAVA_HOME/bin/javac"')
        self.assertIn('bash .cache/gradle/gradle-8.13/bin/gradle -p . --no-daemon', self.build['build'][-1])
        self.assertNotIn('gradlew', self.build['build'][-1])
        self.assertNotIn('cd android', self.build['build'][-1])
        self.assertIn('$$OUT$$', self.build['postbuild'][0])

    def test_fdroid_build_commands_preserve_android_working_directory(self):
        # F-Droid executes successive build commands in the same shell.
        # A plain "cd .. && make assets" would break the following relative Gradle path.
        asset_command, gradle_command = self.build['build'][-4], self.build['build'][-1]
        self.assertEqual(asset_command, 'make -C .. assets')
        self.assertTrue(gradle_command.startswith(
            'bash .cache/gradle/gradle-8.13/bin/gradle -p . --no-daemon '
        ))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            android = root / 'android'
            gradle = android / '.cache/gradle/gradle-8.13/bin/gradle'
            gradle.parent.mkdir(parents=True)
            (root / 'Makefile').write_text('assets:\n\t@touch assets.marker\n', encoding='utf-8')
            gradle.write_text(
                '#!/usr/bin/env bash\n'
                'set -euo pipefail\n'
                '[[ -f ../assets.marker ]]\n'
                '[[ "$PWD" == "$EXPECTED_ANDROID_CWD" ]]\n',
                encoding='utf-8',
            )
            env = dict(os.environ, EXPECTED_ANDROID_CWD=str(android))
            result = subprocess.run(
                ['bash', '-e', '-o', 'pipefail', '-c',
                 asset_command + '\n' + gradle_command],
                cwd=android, env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'assets.marker').is_file())

    def test_native_flags_and_source_scanner_order(self):
        native = (PATCH_DIR / 'native-paths.patch').read_text(encoding='utf-8')
        sources = (PATCH_DIR / 'source-only.patch').read_text(encoding='utf-8')
        self.assertIn('-ffile-prefix-map=${SUDOKURA_ROOT}', native)
        self.assertIn('-ffile-prefix-map=$ENV{ANDROID_HOME}', native)
        self.assertIn('set(CMAKE_EXPORT_COMPILE_COMMANDS ON)', native)
        self.assertIn('subset = ["SDL2", "SDL2_ttf", "SDL2_mixer"]', sources)
        self.assertIn('subset = ["Gradle"]', sources)

    def test_scanner_removes_only_known_unused_third_party_files(self):
        # Exact logs from the no-cache F-Droid 2.4.5 scanner: nine hits.
        # These paths are outside the source targets used by Android CMake.
        expected = [
            'android/.cache/source/SDL2-2.32.10/Xcode/SDL/pkg-support/resources/SDL_DS_Store',
            'android/.cache/source/SDL2_ttf-2.24.0/Xcode/macOS/SDL2.framework/Versions/A/SDL2',
            'android/.cache/source/SDL2_ttf-2.24.0/Xcode/iOS/SDL2.framework/SDL2',
            'android/.cache/source/SDL2_ttf-2.24.0/Xcode/tvOS/SDL2.framework/SDL2',
            'android/.cache/source/SDL2_ttf-2.24.0/external/harfbuzz/src/wasm/rust/harfbuzz-wasm/Cargo.toml',
            'android/.cache/source/SDL2_ttf-2.24.0/external/harfbuzz/src/wasm/sample/rust/hello-wasm/Cargo.toml',
            'android/.cache/source/SDL2_mixer-2.8.1/Xcode/macOS/SDL2.framework/Versions/A/SDL2',
            'android/.cache/source/SDL2_mixer-2.8.1/Xcode/iOS/SDL2.framework/SDL2',
            'android/.cache/source/SDL2_mixer-2.8.1/Xcode/tvOS/SDL2.framework/SDL2',
        ]
        self.assertEqual(self.build['scandelete'], expected)
        self.assertNotIn('scanignore', self.build)
        self.assertEqual(len(expected), len(set(expected)))
        for path in expected:
            self.assertTrue(path.startswith('android/.cache/source/'))
            self.assertNotIn('android/app/', path)
            self.assertNotIn('/freetype/', path)
        self.assertTrue(all(path.endswith(('SDL_DS_Store', '/SDL2', 'Cargo.toml')) for path in expected))

    def test_16k_padding_patch_rebuilds_unsigned_zip_without_payload_change(self):
        patch = (PATCH_DIR / 'signer35-align.patch').read_text(encoding='utf-8')
        data = patch.splitlines(keepends=True)
        first = next(i for i, line in enumerate(data) if line.startswith('@@ ')) + 1
        source = ''.join(line[1:] for line in data[first:] if line.startswith('+'))
        self.assertIn('def rebuild(', source)
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / 'fdroid_align_16k.py'
            script.write_text(source, encoding='utf-8')
            apk = Path(temp) / 'unsigned.apk'
            with zipfile.ZipFile(apk, 'w') as z:
                z.writestr('lib/arm64-v8a/libmain.so', b'A' * 128, compress_type=zipfile.ZIP_STORED)
                z.writestr('assets/readme.txt', b'B' * 128, compress_type=zipfile.ZIP_DEFLATED)
            result = subprocess.run(['python3', str(script), str(apk)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(apk) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(z.read('lib/arm64-v8a/libmain.so'), b'A' * 128)
                self.assertEqual(z.read('assets/readme.txt'), b'B' * 128)
                info = z.getinfo('lib/arm64-v8a/libmain.so')
                with apk.open('rb') as stream:
                    stream.seek(info.header_offset + 26)
                    filename_len = int.from_bytes(stream.read(2), 'little')
                    extra_len = int.from_bytes(stream.read(2), 'little')
                self.assertEqual((info.header_offset + 30 + filename_len + extra_len) % 16384, 0)


if __name__ == '__main__':
    unittest.main()
