"""Offline regression checks for strict local F-Droid build-log classification."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fdroid_build_log_checker", HERE / "check-build-log.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

KNOWN_LOCAL_WARNING = (
    "2026-11-11 05:15:28,613 WARNING: "
    "org.cajapersonal.sudokura:1.4.1 runs this on the buildserver with sudo:\n"
    "\t['apt-get update', 'apt-get install -y golang-go make']\n"
    "These commands were skipped because fdroid build is not running "
    "on a dedicated build server.\n"
)


class BuildLogChecks(unittest.TestCase):
    def test_known_skipped_sudo_is_nonfatal(self):
        self.assertEqual(checker.check(
            "2026-11-11 INFO: Building version 1.4.1\n"
            + KNOWN_LOCAL_WARNING +
            "2026-11-11 INFO: Succeeded\n"
        ), 1)

    def test_clean_build_log_without_warning_is_nonfatal(self):
        self.assertEqual(checker.check("2026 INFO: Build succeeded\n"), 0)

    def test_unknown_warning_is_rejected_even_with_known_warning(self):
        with self.assertRaisesRegex(ValueError, "Unexpected build warning"):
            checker.check(KNOWN_LOCAL_WARNING + "WARNING: unsigned artifact mismatch\n")

    def test_real_error_is_rejected(self):
        for bad in ("ERROR: compile error\n", "CRITICAL: invalid package\n",
                    "Traceback (most recent call last):\n"):
            with self.subTest(message=bad):
                with self.assertRaisesRegex(ValueError, "Unexpected ERROR"):
                    checker.check(KNOWN_LOCAL_WARNING + bad)

    def test_missing_skip_confirmation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "did not confirm"):
            checker.check(KNOWN_LOCAL_WARNING.replace(
                checker.SKIPPED_CONFIRMATION, "No skip confirmation available"
            ))

    def test_different_sudo_commands_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "approved commands"):
            checker.check(KNOWN_LOCAL_WARNING.replace(
                checker.KNOWN_COMMANDS, "['sudo install something else']"
            ))

    def test_missing_make_install_warning_is_rejected(self):
        legacy = KNOWN_LOCAL_WARNING.replace(
            checker.KNOWN_COMMANDS,
            "['apt-get update', 'apt-get install -y golang-go']",
        )
        with self.assertRaisesRegex(ValueError, "approved commands"):
            checker.check(legacy)

    def test_legacy_font_install_warning_is_rejected(self):
        legacy = KNOWN_LOCAL_WARNING.replace(
            checker.KNOWN_COMMANDS,
            "['apt-get update', 'apt-get install -y golang-go fonts-dejavu-core']",
        )
        with self.assertRaisesRegex(ValueError, "approved commands"):
            checker.check(legacy)

    def test_repeated_known_warning_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            checker.check(KNOWN_LOCAL_WARNING + KNOWN_LOCAL_WARNING)


if __name__ == "__main__":
    unittest.main()
