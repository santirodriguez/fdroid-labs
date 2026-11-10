"""Fail-closed post-scan CMake flag propagation checks."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_repro', ROOT / 'native-repro.py')
NATIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NATIVE)


class NativeReproTests(unittest.TestCase):
    def test_changes_only_reviewed_source_and_anchor(self):
        original = b'cmake_minimum_required(VERSION 3.22.1)\nproject(SudokuraAndroid C)\nadd_subdirectory(dep)\n'
        with patch.object(NATIVE, 'SOURCE_BLOB', NATIVE.git_blob_sha(original)):
            result = NATIVE.patch_cmake(original).decode('utf-8')
        self.assertLess(result.index('add_compile_options'), result.index('add_subdirectory'))
        for flag in NATIVE.FLAGS:
            self.assertIn(flag, result)
        self.assertIn('set(CMAKE_EXPORT_COMPILE_COMMANDS ON)', result)
        with self.assertRaises(ValueError):
            NATIVE.patch_cmake(original)
        with self.assertRaises(ValueError):
            NATIVE.patch_cmake(result.encode('utf-8'))

    def test_recipe_and_patch_use_absolute_checkout_path(self):
        recipe = (ROOT / 'metadata' / 'org.cajapersonal.sudokura.yml').read_text(encoding='utf-8')
        command = 'python3 /work/fdroid/tools/native-repro.py apply ' + str(NATIVE.CANONICAL_CMAKE_PATH)
        self.assertTrue(NATIVE.CANONICAL_CMAKE_PATH.is_absolute())
        self.assertIn('      - ' + command + '\n', recipe)
        # The preceding build command changes directory; an absolute path is invariant.
        self.assertIn('      - cd .. && make assets\n      - ' + command + '\n', recipe)

    def test_apply_rejects_relative_path_and_modifies_only_validated_file(self):
        original = b'cmake_minimum_required(VERSION 3.22.1)\nproject(SudokuraAndroid C)\nadd_subdirectory(dep)\n'
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / 'android/app/src/main/cpp/CMakeLists.txt'
            canonical.parent.mkdir(parents=True)
            canonical.write_bytes(original)
            with patch.object(NATIVE, 'CANONICAL_CMAKE_PATH', canonical), \\
                    patch.object(NATIVE, 'SOURCE_BLOB', NATIVE.git_blob_sha(original)):
                with self.assertRaisesRegex(ValueError, 'canonical absolute'):
                    NATIVE.apply(Path('app/src/main/cpp/CMakeLists.txt'))
                NATIVE.apply(canonical)
                self.assertIn(b'add_compile_options', canonical.read_bytes())
                with self.assertRaises(ValueError):
                    NATIVE.apply(canonical)

    def test_detects_flags_in_all_four_real_native_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            native_root = Path(tmp) / '.cxx'
            commands = native_root / 'RelWithDebInfo' / 'anything' / 'arm64-v8a' / 'compile_commands.json'
            commands.parent.mkdir(parents=True)
            sources = [NATIVE.SOURCE_ROOT + '/src/app.c']
            sources.extend(NATIVE.SOURCE_ROOT + '/android/.cache/source/' + p + '/src/sample.c' for p in (
                'SDL2-2.32.10', 'SDL2_ttf-2.24.0', 'SDL2_mixer-2.8.1'))
            rows = [{'file': f, 'command': 'clang ' + ' '.join(NATIVE.FLAGS) + ' -c ' + f} for f in sources]
            commands.write_text(json.dumps(rows))
            NATIVE.verify(native_root)
            rows[-1]['command'] = 'clang -c ' + sources[-1]
            commands.write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError, 'Missing compiler flags in SDL2_mixer'):
                NATIVE.verify(native_root)
            rows = rows[:-1]
            commands.write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError, 'Missing native target compile evidence for: SDL2_mixer'):
                NATIVE.verify(native_root)

    def test_rejects_missing_compiler_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'No ARM64 native compiler command database'):
                NATIVE.verify(Path(tmp) / '.cxx')


if __name__ == '__main__':
    unittest.main()
