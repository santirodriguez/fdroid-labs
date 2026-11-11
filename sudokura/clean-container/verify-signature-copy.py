#!/usr/bin/env python3
"""Verify a real independent unsigned F-Droid APK against the public signed APK."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SIGNED_URL = (
    "https://github.com/santirodriguez/Sudokura/releases/download/"
    "v1.4.1/Sudokura-1.4.1-Android-arm64.apk"
)
SIGNED_SHA256 = "06e06d8b8301384a37876b978d0fb18552b3601487628e7465e1cec33a3836b4"
CERT_SHA256 = "fde951e3d2ef42e41c7186ee965944aeca549d590ad080711dd3d875f82df66d"
MAX_SIGNED_BYTES = 8 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_reference(destination):
    req = Request(SIGNED_URL, headers={"User-Agent": "Sudokura-FDroid-Repro-Check/1"})
    with urlopen(req, timeout=90) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or not (
            final.hostname == "github.com" or
            (final.hostname or "").endswith(".githubusercontent.com")
        ):
            raise ValueError("Unexpected download destination")
        with destination.open("wb") as output:
            remaining = MAX_SIGNED_BYTES + 1
            while remaining:
                chunk = response.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                output.write(chunk)
                remaining -= len(chunk)
            if remaining == 0:
                raise ValueError("Unexpectedly large signed APK")
    if sha256(destination) != SIGNED_SHA256:
        raise ValueError("Published signed APK has unexpected SHA-256")


def check(unsigned_apk):
    if not unsigned_apk.is_file() or unsigned_apk.is_symlink():
        raise ValueError("Missing independent unsigned source-built APK")
    # The source-build recipe has already restored original Build Tools 35 ZIP
    # padding. First exercise F-Droid's normal verification function unchanged;
    # never inject our lab-specific alignment override into this check.
    from fdroidserver import apksigcopier, common
    sdk = Path(os.environ.get("ANDROID_HOME", ""))
    apksigner = sdk / "build-tools" / "35.0.0" / "apksigner"
    if not apksigner.is_file():
        raise ValueError("Pinned apksigner verifier missing")
    with tempfile.TemporaryDirectory(prefix="sudokura-sigcopy-") as scratch:
        signed = Path(scratch) / "reference.apk"
        reproduced = Path(scratch) / "reproduced.apk"
        download_reference(signed)

        if apksigcopier.skip_realignment:
            raise ValueError("Expected unmodified F-Droid signature copier defaults")
        # Supply only the pinned Android verifier binary to fdroidserver.
        # The signature-copy implementation and options remain unmodified.
        common.config = {"apksigner": str(apksigner)}
        result = common.verify_apks(str(signed), str(unsigned_apk), scratch)
        if result is not None:
            raise ValueError("Default fdroidserver.verify_apks rejected the APK: " + str(result))
        verified = Path(scratch) / ("sigcp_" + unsigned_apk.name)
        if not verified.is_file() or sha256(verified) != SIGNED_SHA256:
            raise ValueError("Default F-Droid verification output differed from the published APK")
        print("PASS: unmodified fdroidserver.common.verify_apks and signed SHA-256")

        # Preserve the earlier independent explicit 16-KiB copy check as an
        # additional control, not as a replacement for the standard verifier.
        apksigcopier.skip_realignment = True
        apksigcopier.do_copy(str(signed), str(unsigned_apk), str(reproduced))
        if sha256(reproduced) != SIGNED_SHA256:
            raise ValueError("Signature copy failed to reproduce original signed APK bytes")
        report = subprocess.run(
            [str(apksigner), "verify", "--verbose", "--print-certs", str(reproduced)],
            check=True, capture_output=True, text=True, timeout=90,
        )
        if CERT_SHA256 not in report.stdout.lower():
            raise ValueError("Original Android signer certificate did not match")
    print("PASS: independent APK rebuild and original signature copy are byte-identical")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify-signature-copy.py INDEPENDENT_UNSIGNED_APK")
    try:
        check(Path(sys.argv[1]))
    except (OSError, ValueError, ImportError, subprocess.CalledProcessError) as exc:
        print("SIGNATURE-COPY CHECK FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
