"""Offline tests: public original signer must never be silently substituted."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "verify-signature-copy.py"


class SignatureCopyTests(unittest.TestCase):
    def test_original_public_reference_is_pinned(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("v1.4.1/Sudokura-1.4.1-Android-arm64.apk", source)
        self.assertIn("06e06d8b8301384a37876b978d0fb18552b3601487628e7465e1cec33a3836b4", source)
        self.assertIn("fde951e3d2ef42e41c7186ee965944aeca549d590ad080711dd3d875f82df66d", source)
        self.assertIn("common.verify_apks(str(signed), str(unsigned_apk), scratch)", source)
        self.assertIn("common.config = {\"apksigner\": str(apksigner)}", source)
        self.assertIn("apksigcopier.skip_realignment = True", source)
        self.assertIn("if apksigcopier.skip_realignment:", source)
        self.assertLess(
            source.index("common.verify_apks("),
            source.index("apksigcopier.skip_realignment = True"),
        )
        self.assertIn("apksigcopier.do_copy", source)
        self.assertIn("apksigner", source)
        self.assertIn("if sha256(reproduced) != SIGNED_SHA256", source)
        for forbidden in ("apksigner sign", "fdroid publish", "git push", "GITHUB_TOKEN"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
