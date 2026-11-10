"""Offline fault injection for exact-source APK payload comparisons."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('repro_check', ROOT / 'repro-check.py')
REPRO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPRO)


class ReproCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def apk(self, entries):
        path = self.root / 'fixture.apk'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w') as archive:
                for name, value in entries:
                    archive.writestr(name, value)
        return path

    def test_identical_payload_passes_only_payload_gate(self):
        apk = self.apk([('classes.dex', b'fixture')])
        _, expected = REPRO.inventory(apk)
        with patch.object(REPRO, 'EXPECTED_MEMBERS', 1), patch.object(REPRO, 'PAYLOAD_SHA256', expected):
            result = REPRO.compare(apk)
        self.assertTrue(result['payload_match'])
        self.assertTrue(result['signature_verification'].startswith('NOT_RUN'))

    def test_modified_payload_fails(self):
        apk = self.apk([('classes.dex', b'fixture')])
        _, expected = REPRO.inventory(apk)
        apk = self.apk([('classes.dex', b'changed')])
        with patch.object(REPRO, 'EXPECTED_MEMBERS', 1), patch.object(REPRO, 'PAYLOAD_SHA256', expected):
            self.assertFalse(REPRO.compare(apk)['payload_match'])

    def test_member_count_cannot_be_waived(self):
        apk = self.apk([('classes.dex', b'fixture')])
        _, expected = REPRO.inventory(apk)
        with patch.object(REPRO, 'PAYLOAD_SHA256', expected):
            self.assertFalse(REPRO.compare(apk)['payload_match'])

    def test_duplicate_unsafe_or_signed_entries_rejected(self):
        cases = [[('classes.dex', b'a'), ('classes.dex', b'b')],
                 [('../outside', b'a')], [('/outside', b'a')],
                 [('META-INF/TEST.RSA', b'a')], [('empty/', b'')]]
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                REPRO.inventory(self.apk(entries))

    def test_order_does_not_claim_zip_reproducibility(self):
        first = REPRO.inventory(self.apk([('a', b'1'), ('b', b'2')]))[1]
        second = REPRO.inventory(self.apk([('b', b'2'), ('a', b'1')]))[1]
        self.assertEqual(first, second)

    def test_font_and_license_both_pinned(self):
        font, license_file = self.root / 'font', self.root / 'license'
        font.write_bytes(b'font'); license_file.write_bytes(b'license')
        with patch.object(REPRO, 'FONT_SHA256', hashlib.sha256(b'font').hexdigest()), \
                patch.object(REPRO, 'FONT_LICENSE_SHA256', hashlib.sha256(b'license').hexdigest()):
            REPRO.check_font(font, license_file)
            license_file.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                REPRO.check_font(font, license_file)

    def test_new_workflow_is_manual_unsigned_and_offline(self):
        text = (ROOT.parent / '.github/workflows/sudokura-fdroid-local.yml').read_text()
        self.assertIn('  workflow_dispatch:', text)
        for forbidden in ('  push:', '  pull_request:', '  schedule:', 'secrets.', 'fdroid publish'):
            self.assertNotIn(forbidden, text)
        self.assertIn('--network none --cap-drop ALL', text)
        self.assertIn('steps.offline_probe.outcome', text)
        self.assertIn('native-repro.py', text)
        self.assertNotIn('-e CFLAGS=', text)
        self.assertIn('repro-check.py font', text)
        self.assertIn('repro-check.py apk', text)
        self.assertIn('b057341c84cd988cd15b3329507aaa6151449f5b', text)


if __name__ == '__main__':
    unittest.main()
