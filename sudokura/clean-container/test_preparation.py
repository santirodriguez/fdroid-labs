"""Offline structural checks for the proposed, unexecuted F-Droid container probe."""
import importlib.util
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "sudokura-fdroid-clean-container.yml"
RUN = HERE / "run-clean.sh"

spec = importlib.util.spec_from_file_location("candidate_stage", HERE / "stage.py")
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class ContainerCandidateTests(unittest.TestCase):
    def test_binary_exclusion_is_only_the_intended_local_deviation(self):
        candidate = (
            "Repo: file:///work/fdroid/mirror/sudokura.git\n"
            "AllowedAPKSigningKeys: " + stage.SIGNER_SHA + "\n"
            "Builds:\n  - versionName: 1.4.1\n"
            "    versionCode: 2\n"
            "    commit: " + stage.SOURCE_SHA + "\n"
            "    patch:\n      - native-paths.patch\n"
            + stage.BINARY_LINE
        )
        changed = stage.omit_unpublished_binary(candidate)
        self.assertEqual(changed, candidate.replace(stage.BINARY_LINE, "", 1))
        self.assertIn("AllowedAPKSigningKeys: " + stage.SIGNER_SHA, changed)
        with self.assertRaises(ValueError):
            stage.omit_unpublished_binary(changed)
        with self.assertRaises(ValueError):
            stage.omit_unpublished_binary(candidate + stage.BINARY_LINE)
        with self.assertRaises(ValueError):
            stage.omit_unpublished_binary(
                candidate.replace("file:///work/fdroid/mirror/sudokura.git",
                                  "https://github.com/santirodriguez/Sudokura.git")
            )

    def test_manual_standard_runner_and_source_pin(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_dispatch:\n", content)
        self.assertEqual(len(re.findall(r"(?m)^    runs-on: ubuntu-24\.04$", content)), 1)
        self.assertNotRegex(content, r"(?m)^  (push|pull_request|schedule):")
        self.assertIn("github.event.repository.private == false", content)
        self.assertIn("permissions:\n  contents: read", content)
        self.assertIn("timeout-minutes: 55", content)
        self.assertIn(stage.CANDIDATE_SHA, content)
        self.assertIn(stage.SOURCE_SHA, content)
        self.assertEqual(content.count("persist-credentials: false"), 3)
        self.assertIn("--network bridge", content)
        self.assertIn("--cap-drop ALL --security-opt no-new-privileges", content)
        self.assertIn("--user ", content)
        self.assertIn("--no-cache", content)
        self.assertIn("sdkmanager", content)
        for forbidden in (
            "actions/upload-artifact", "actions/cache", "runs-on: ubuntu-latest-xl",
            "git push", "gh release", "fdroid publish", "fdroid deploy",
            "secrets.", "workflow_call:", "workflow_run:",
        ):
            self.assertNotIn(forbidden, content)

    def test_real_candidate_build_without_signing(self):
        content = RUN.read_text(encoding="utf-8")
        self.assertIn("fdroid readmeta", content)
        self.assertIn("fdroid lint", content)
        self.assertIn('fdroid scanner -v "$app:2"', content)
        self.assertIn("fdroid build --stop --test --no-refresh --no-tarball", content)
        self.assertIn("tools/repro-check.py apk", content)
        for forbidden in ("fdroid publish ", "fdroid update ", "fdroid deploy ",
                          "apksigner sign", "git push "):
            self.assertNotIn(forbidden, content)
        result = subprocess.run(
            ["bash", "-n", str(RUN)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
