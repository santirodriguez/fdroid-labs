#!/usr/bin/env python3
"""Fail-closed F-Droid build-log check for the isolated non-VM test.

Local fdroid build --test does not run candidate sudo: commands: those
are reserved for F-Droid's buildserver VM. Allow ONLY that expected diagnostic
when the log confirms the exact commands were skipped, never arbitrary warnings.
"""
import argparse
from pathlib import Path
import re
import sys

KNOWN_WARNING = (
    "WARNING: org.cajapersonal.sudokura:1.4.1 "
    "runs this on the buildserver with sudo:"
)
KNOWN_COMMANDS = "['apt-get update', 'apt-get install -y golang-go fonts-dejavu-core']"
SKIPPED_CONFIRMATION = (
    "These commands were skipped because fdroid build is not running "
    "on a dedicated build server."
)
WARNING_RE = re.compile(r"(?i)(?:^|\s)WARNING\b")
ERROR_RE = re.compile(r"(?i)(?:^|\s)(?:ERROR|CRITICAL|Traceback)\b")


def check(log):
    known = 0
    for line in log.splitlines():
        if ERROR_RE.search(line):
            raise ValueError("Unexpected ERROR, CRITICAL or Traceback in build output")
        if WARNING_RE.search(line):
            if KNOWN_WARNING not in line:
                raise ValueError("Unexpected build warning: " + line.strip()[:220])
            known += 1
    if known > 1:
        raise ValueError("Duplicate known local-only sudo warning")
    if known:
        if KNOWN_COMMANDS not in log:
            raise ValueError("Local sudo warning did not identify approved commands")
        if SKIPPED_CONFIRMATION not in log:
            raise ValueError("Local sudo warning did not confirm commands were skipped")
    return known


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_log", type=Path)
    args = parser.parse_args()
    if not args.build_log.is_file() or args.build_log.is_symlink():
        print("Expected a regular F-Droid build log", file=sys.stderr)
        return 2
    try:
        known = check(args.build_log.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print("Build output verification BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    print(
        "Build output verified; known skipped-sudo warning(s): "
        + str(known) + "; other warnings/errors: NONE"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
