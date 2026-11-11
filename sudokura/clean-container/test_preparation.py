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

    def test_revised_candidate_pin_is_coherent(self):
        self.assertEqual(stage.CANDIDATE_SHA, "6e5225bee3d4976eeaf3acff7bc56cd0d98d25b5")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(workflow.count(stage.CANDIDATE_SHA), 2)
        self.assertIn("ref: " + stage.CANDIDATE_SHA, workflow)

    def test_fdroid_patch_tool_is_available_before_scanning(self):
        dockerfile = (ROOT / "sudokura" / "Dockerfile").read_text(encoding="utf-8")
        package_list = dockerfile.split("apt-get install -y --no-install-recommends", 1)[1].split(
            "&& rm -rf", 1
        )[0]
        self.assertRegex(package_list, r"(?<![\w-])patch(?![\w-])")

        script = RUN.read_text(encoding="utf-8")
        self.assertIn("command -v patch >/dev/null 2>&1", script)
        self.assertIn("Missing patch executable required by F-Droid metadata", script)
        self.assertLess(script.index("command -v patch"), script.index("run_check readmeta"))
        self.assertIn("0 problems? found' logs/scanner.log", script)

    def test_real_candidate_build_without_signing(self):
        content = RUN.read_text(encoding="utf-8")
        self.assertIn("fdroid readmeta", content)
        self.assertIn("fdroid lint", content)
        self.assertIn('fdroid scanner -v "$app:2"', content)
        self.assertIn("fdroid build --stop --test --no-refresh --no-tarball", content)
        self.assertIn("tools/repro-check.py apk", content)
        self.assertIn("scanner_command=EXIT_ZERO", content)
        self.assertIn("scanner=PASS_ZERO_PROBLEMS", content)
        self.assertLess(content.index("Scanner did not explicitly report zero problems"),
                        content.index("scanner=PASS_ZERO_PROBLEMS"))
        for forbidden in ("fdroid publish ", "fdroid update ", "fdroid deploy ",
                          "apksigner sign", "git push "):
            self.assertNotIn(forbidden, content)
        result = subprocess.run(
            ["bash", "-n", str(RUN)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
