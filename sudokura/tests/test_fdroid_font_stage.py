"""Offline structural and hostile-input checks for the pinned original-font patch."""
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

PATCH_PATH = Path(__file__).resolve().parents[1] / "fdroiddata-candidate" / "metadata" / "org.cajapersonal.sudokura" / "pinned-font.patch"


class FontPatchTests(unittest.TestCase):
    def load_patched_module(self, root):
        patch_lines = PATCH_PATH.read_text(encoding="utf-8").splitlines()
        source = "\n".join(line[1:] for line in patch_lines if line.startswith("+") and not line.startswith("+++")) + "\n"
        android = Path(root) / "android"
        script = android / "scripts" / "fdroid_stage_font.py"
        script.parent.mkdir(parents=True)
        script.write_text(source, encoding="utf-8")
        (android / ".cache").mkdir()
        spec = importlib.util.spec_from_file_location("sudokura_font_stage_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_original_hashes_and_fail_closed_staging(self):
        with TemporaryDirectory() as tmp:
            mod = self.load_patched_module(tmp)
            self.assertEqual(mod.ARCHIVE_SIZE, 835172)
            self.assertEqual(mod.ARCHIVE_SHA256, "40049660c194f3b8a2541fc7369efebb10e9f94bdac836a2f38fafedd10fa73a")
            self.assertEqual(mod.FONT_SHA256, "ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280")
            self.assertEqual(mod.LICENSE_SHA256, "63d3ba759d12804c5b31a9d5940d855c1820d1f5999e6b0872eb1c7ff045fbc9")
            font_bytes, license_bytes, archive_bytes = b"original font test", b"copyright test", b"deb fixture"
            def fake_extract(command, **kwargs):
                self.assertEqual(command[:2], ["dpkg-deb", "--extract"])
                output = Path(command[-1])
                font = output / mod.FONT_REL
                lic = output / mod.LICENSE_REL
                font.parent.mkdir(parents=True)
                lic.parent.mkdir(parents=True)
                font.write_bytes(font_bytes)
                lic.write_bytes(license_bytes)
            with (patch.object(mod, "ARCHIVE_SHA256", hashlib.sha256(archive_bytes).hexdigest()),
                  patch.object(mod, "FONT_SHA256", hashlib.sha256(font_bytes).hexdigest()),
                  patch.object(mod, "LICENSE_SHA256", hashlib.sha256(license_bytes).hexdigest()),
                  patch.object(mod, "fetch_archive", return_value=archive_bytes),
                  patch.object(mod.subprocess, "run", side_effect=fake_extract)):
                mod.stage()
                self.assertEqual((mod.DESTINATION / "DejaVuSans.ttf").read_bytes(), font_bytes)
                self.assertEqual((mod.DESTINATION / "copyright").read_bytes(), license_bytes)
                with self.assertRaisesRegex(ValueError, "Refusing to replace"):
                    mod.stage()

    def test_package_bytes_and_url_redirect_are_verified(self):
        with TemporaryDirectory() as tmp:
            mod = self.load_patched_module(tmp)
            class Response:
                def __init__(self, url): self.url = url
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def geturl(self): return self.url
                def read(self, count): return b"wrong bytes"
            with patch.object(mod, "urlopen", return_value=Response(mod.ARCHIVE_URL)):
                with self.assertRaisesRegex(ValueError, "size"):
                    mod.fetch_archive()
            with patch.object(mod, "urlopen", return_value=Response("https://bad.invalid/package")):
                with self.assertRaisesRegex(ValueError, "redirect"):
                    mod.fetch_archive()


if __name__ == "__main__":
    unittest.main()
