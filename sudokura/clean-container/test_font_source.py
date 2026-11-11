"""Offline checks for the original-font staging gate; no downloads or Android build."""
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/sudokura-fdroid-clean-container.yml"
RUN = HERE / "run-clean.sh"

spec = importlib.util.spec_from_file_location("stage_original_font", HERE / "stage-font.py")
font_stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(font_stage)


class Response:
    def __init__(self, data, url):
        self.data = data
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, length):
        return self.data[:length]


class PinnedUbuntuFontTests(unittest.TestCase):
    def test_package_identity_and_original_digest_are_immutable(self):
        self.assertEqual(font_stage.ARCHIVE_SIZE, 835172)
        self.assertEqual(
            font_stage.ARCHIVE_SHA256,
            "40049660c194f3b8a2541fc7369efebb10e9f94bdac836a2f38fafedd10fa73a",
        )
        self.assertEqual(
            font_stage.ARCHIVE_URL,
            "https://archive.ubuntu.com/ubuntu/pool/main/f/fonts-dejavu/"
            "fonts-dejavu-core_2.37-8_all.deb",
        )
        self.assertEqual(
            font_stage.FONT_SHA256,
            "ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280",
        )
        self.assertEqual(
            font_stage.LICENSE_SHA256,
            "63d3ba759d12804c5b31a9d5940d855c1820d1f5999e6b0872eb1c7ff045fbc9",
        )

    def test_dns_failover_uses_only_pinned_package(self):
        from urllib.error import URLError
        fixture = b"immutable source package test"
        digest = hashlib.sha256(fixture).hexdigest()
        response = Response(fixture, font_stage.MIRROR_URLS[1])
        with (
            patch.object(font_stage, "ARCHIVE_SIZE", len(fixture)),
            patch.object(font_stage, "ARCHIVE_SHA256", digest),
            patch.object(font_stage, "urlopen", side_effect=[URLError("DNS unavailable"), response]) as opener,
        ):
            self.assertEqual(font_stage.fetch_pinned_archive(), fixture)
            self.assertEqual(opener.call_count, 2)
        self.assertEqual(len(font_stage.MIRROR_URLS), 3)

    def test_does_not_accept_wrong_hash_from_fallback(self):
        from urllib.error import URLError
        fixture = b"untrusted package"
        response = Response(fixture, font_stage.MIRROR_URLS[1])
        with (
            patch.object(font_stage, "ARCHIVE_SIZE", len(fixture)),
            patch.object(font_stage, "urlopen", side_effect=[URLError("DNS unavailable"), response]) as opener,
        ):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                font_stage.fetch_pinned_archive()
            self.assertEqual(opener.call_count, 2)

    def test_wrong_package_bytes_or_redirect_fail_closed(self):
        bad = b"not the Ubuntu package" * 20
        with patch.object(font_stage, "urlopen", return_value=Response(bad, font_stage.ARCHIVE_URL)):
            with self.assertRaisesRegex(ValueError, "unexpected size"):
                font_stage.fetch_pinned_archive()
        same_length_wrong_hash = b"0" * font_stage.ARCHIVE_SIZE
        with patch.object(font_stage, "urlopen", return_value=Response(same_length_wrong_hash, font_stage.ARCHIVE_URL)):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                font_stage.fetch_pinned_archive()
        with patch.object(font_stage, "urlopen", return_value=Response(bad, "https://unapproved.invalid/file")):
            with self.assertRaisesRegex(ValueError, "Unexpected redirect"):
                font_stage.fetch_pinned_archive()

    def test_both_files_required_with_no_silent_substitution(self):
        with TemporaryDirectory() as temp:
            font = Path(temp) / "DejaVuSans.ttf"
            license_file = Path(temp) / "copyright"
            font.write_bytes(b"font fixture")
            license_file.write_bytes(b"copyright fixture")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                font_stage.verify_pair(font, license_file)

            with (
                patch.object(font_stage, "FONT_SHA256", hashlib.sha256(font.read_bytes()).hexdigest()),
                patch.object(font_stage, "LICENSE_SHA256", hashlib.sha256(license_file.read_bytes()).hexdigest()),
            ):
                font_stage.verify_pair(font, license_file)
                license_file.write_bytes(b"changed copyright")
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    font_stage.verify_pair(font, license_file)

    def test_manual_free_runner_pins_and_readonly_mounts(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        runner = RUN.read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_dispatch:\n", workflow)
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("github.event.repository.private == false", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        self.assertNotIn("actions/cache", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertIn("python3 lab/sudokura/clean-container/stage-font.py --work", workflow)
        self.assertLess(workflow.index("Stage exact original font"), workflow.index("Build throwaway fdroidserver"))
        for name, target in (
            ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ("copyright", "/usr/share/doc/fonts-dejavu-core/copyright"),
        ):
            self.assertIn("src=$work/verified-font/" + name + ",dst=" + target + ",readonly", workflow)
        self.assertIn("python3 tools/repro-check.py font", runner)


if __name__ == "__main__":
    unittest.main()
