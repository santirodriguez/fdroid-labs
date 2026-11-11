#!/usr/bin/env python3
"""Stage the immutable F-Droid candidate for one disposable container-only build.

The sole metadata deviations are the local source mirror and temporary removal
of the NOT-YET-PUBLISHED upstream binary URL. Never alter upstream metadata.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

APP = "org.cajapersonal.sudokura"
SOURCE_SHA = "b057341c84cd988cd15b3329507aaa6151449f5b"
SOURCE_TREE = "a0bcecc4bf67a4d3f36c40172dca45dda2e74884"
CANDIDATE_SHA = "6e5225bee3d4976eeaf3acff7bc56cd0d98d25b5"
SIGNER_SHA = "fde951e3d2ef42e41c7186ee965944aeca549d590ad080711dd3d875f82df66d"
BINARY_LINE = (
    "    binary: https://github.com/santirodriguez/Sudokura/releases/download/"
    "v1.4.1/Sudokura-1.4.1-Android-arm64.apk\n"
)
PATCHES = ("native-paths.patch", "signer35-align.patch", "source-only.patch")


def git_value(repo, *args):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def omit_unpublished_binary(metadata):
    """Make precisely one explicit TEST-ONLY deviation from the candidate."""
    if metadata.count(BINARY_LINE) != 1:
        raise ValueError("Expected exactly one pinned, unpublished binary URL")
    if metadata.count("AllowedAPKSigningKeys: " + SIGNER_SHA) != 1:
        raise ValueError("Original signer fingerprint is missing or ambiguous")
    if metadata.count("commit: " + SOURCE_SHA) != 1:
        raise ValueError("Exact source commit is missing or ambiguous")
    if metadata.count("    versionCode: 2") != 1:
        raise ValueError("Expected v1.4.1/code2 build")
    if metadata.count("Repo: file:///work/fdroid/mirror/sudokura.git") != 1:
        raise ValueError("Untrusted or missing disposable source mirror")
    if metadata.count("    patch:\n") != 1:
        raise ValueError("Candidate patch list was modified")
    return metadata.replace(BINARY_LINE, "", 1)


def prepare(lab, candidate, source, work):
    if work.exists() or work.is_symlink():
        raise ValueError("Fresh temporary work directory required")
    if git_value(source, "rev-parse", "HEAD") != SOURCE_SHA:
        raise ValueError("Sudokura source commit mismatch")
    if git_value(source, "rev-parse", "HEAD^{tree}") != SOURCE_TREE:
        raise ValueError("Sudokura source tree mismatch")
    if git_value(candidate, "rev-parse", "HEAD") != CANDIDATE_SHA:
        raise ValueError("Unreviewed F-Droid candidate revision")
    if (source / "android" / ".cache").exists():
        raise ValueError("Sudokura source checkout already contains generated caches")

    candidate_root = candidate / "sudokura" / "fdroiddata-candidate" / "metadata"
    meta_path = candidate_root / (APP + ".yml")
    patch_dir = candidate_root / APP
    ref_tool = candidate / "sudokura" / "repro-check.py"
    stage_tool = lab / "sudokura" / "stage-offline-git.sh"
    run_tool = lab / "sudokura" / "clean-container" / "run-clean.sh"
    build_log_tool = lab / "sudokura" / "clean-container" / "check-build-log.py"
    for file in [meta_path, ref_tool, stage_tool, run_tool, build_log_tool] + [
        patch_dir / name for name in PATCHES
    ]:
        if not file.is_file() or file.is_symlink():
            raise ValueError("Missing or nonregular pinned input: " + str(file))

    work.mkdir(parents=True)
    (work / "home").mkdir()
    (work / "gradle-home").mkdir()
    (work / "tools").mkdir()
    (work / "config").mkdir()
    (work / "logs").mkdir()

    # The proven helper mirrors an exact source checkout locally and replaces
    # only Repo: in a disposable metadata file, never the candidate in Git.
    subprocess.run(
        ["bash", str(stage_tool), str(source), str(work), str(meta_path), SOURCE_SHA],
        check=True,
    )
    local_meta = work / "metadata" / (APP + ".yml")
    original_local = local_meta.read_text(encoding="utf-8")
    local_meta.write_text(omit_unpublished_binary(original_local), encoding="utf-8")
    output_patches = work / "metadata" / APP
    output_patches.mkdir()
    for name in PATCHES:
        shutil.copyfile(patch_dir / name, output_patches / name)
    shutil.copyfile(ref_tool, work / "tools" / "repro-check.py")
    shutil.copyfile(run_tool, work / "tools" / "run-clean.sh")
    shutil.copyfile(build_log_tool, work / "tools" / "check-build-log.py")

    (work / "config.yml").write_text(
        "sdk_path: /opt/android-sdk\n"
        "ndk_paths:\n"
        "  '28.2.13676358': /opt/android-sdk/ndk/28.2.13676358\n",
        encoding="utf-8",
    )
    (work / "config" / "categories.yml").write_text(
        "Games:\n  name: Games\n  description: Games and puzzles\n",
        encoding="utf-8",
    )
    (work / "logs" / "provenance.txt").write_text(
        "source_sha=" + SOURCE_SHA + "\n"
        "source_tree=" + SOURCE_TREE + "\n"
        "candidate_sha=" + CANDIDATE_SHA + "\n"
        "candidate_metadata_sha256=" + sha256(meta_path) + "\n"
        "local_metadata_sha256=" + sha256(local_meta) + "\n"
        "original_signer_certificate_sha256=" + SIGNER_SHA + "\n"
        "binary_url=TEST_ONLY_OMITTED_UNPUBLISHED\n"
        "vm_equivalence=NOT_TESTED\n"
        "apk_signing=NOT_RUN\n"
        "third_party_submission=NOT_RUN\n",
        encoding="utf-8",
    )
    print("Staged exact-source local Git mirror and three candidate patches")
    print("Original signer fingerprint preserved; unpublished binary URL disabled only in scratch")


def main():
    parser = argparse.ArgumentParser()
    for name in ("lab", "candidate", "source", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(
            args.lab.resolve(), args.candidate.resolve(),
            args.source.resolve(), args.work.absolute()
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("CLEAN CONTAINER STAGING BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
