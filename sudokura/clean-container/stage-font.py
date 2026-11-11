#!/usr/bin/env python3
"""Stage the exact original DejaVu font and license from an official Ubuntu .deb.

For the disposable container experiment only. No package installation,
repository modification, key use, or change to the candidate's hash checks.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

# Ubuntu 24.04 "noble" package; checksum published at packages.ubuntu.com.
ARCHIVE_URL = (
    "https://archive.ubuntu.com/ubuntu/pool/main/f/fonts-dejavu/"
    "fonts-dejavu-core_2.37-8_all.deb"
)
ARCHIVE_SIZE = 835172
ARCHIVE_SHA256 = "40049660c194f3b8a2541fc7369efebb10e9f94bdac836a2f38fafedd10fa73a"

# Do NOT replace these with the Debian font or another convenient local version.
# Hashes are the exact inputs previously verified for Sudokura 1.4.1.
FONT_SHA256 = "ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280"
LICENSE_SHA256 = "63d3ba759d12804c5b31a9d5940d855c1820d1f5999e6b0872eb1c7ff045fbc9"
FONT_REL = Path("usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
LICENSE_REL = Path("usr/share/doc/fonts-dejavu-core/copyright")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_file(path, expected):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing regular original input: " + str(path))
    actual = sha256(path.read_bytes())
    if actual != expected:
        raise ValueError(
            "Original input hash mismatch for " + path.name
            + ": expected " + expected + ", got " + actual
        )


def verify_pair(font, license_file):
    verify_file(font, FONT_SHA256)
    verify_file(license_file, LICENSE_SHA256)


def fetch_pinned_archive():
    request = Request(
        ARCHIVE_URL,
        headers={"User-Agent": "Sudokura-fdroid-lab-font-verifier/1"},
    )
    with urlopen(request, timeout=45) as response:
        if response.geturl() != ARCHIVE_URL:
            raise ValueError("Unexpected redirect while downloading Ubuntu package")
        content = response.read(ARCHIVE_SIZE + 1)
    if len(content) != ARCHIVE_SIZE:
        raise ValueError("Ubuntu .deb has an unexpected size")
    actual = sha256(content)
    if actual != ARCHIVE_SHA256:
        raise ValueError("Official Ubuntu package SHA-256 mismatch: " + actual)
    return content


def stage(work):
    if not work.is_dir() or work.is_symlink():
        raise ValueError("Expected an existing fresh disposable work directory")
    if not (work / "logs" / "provenance.txt").is_file():
        raise ValueError("Immutable source/candidate staging must succeed first")
    destination = work / "verified-font"
    temporary = work / "font-package-staging"
    if destination.exists() or destination.is_symlink():
        raise ValueError("Refusing an existing verified-font directory")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("Refusing stale font staging inputs")

    temporary.mkdir(mode=0o700)
    try:
        archive = temporary / "fonts-dejavu-core_2.37-8_all.deb"
        archive.write_bytes(fetch_pinned_archive())
        verify_file(archive, ARCHIVE_SHA256)

        extraction = temporary / "extracted"
        subprocess.run(
            ["dpkg-deb", "--extract", str(archive), str(extraction)],
            capture_output=True, text=True, check=True, timeout=90,
        )
        source_font = extraction / FONT_REL
        source_license = extraction / LICENSE_REL
        # Fail closed if Ubuntu package did not contain BOTH original files.
        verify_pair(source_font, source_license)

        selected = temporary / "selected"
        selected.mkdir()
        font = selected / "DejaVuSans.ttf"
        copyright_file = selected / "copyright"
        shutil.copyfile(source_font, font)
        shutil.copyfile(source_license, copyright_file)
        verify_pair(font, copyright_file)
        font.chmod(0o444)
        copyright_file.chmod(0o444)
        selected.rename(destination)

        (work / "logs" / "verified-font.txt").write_text(
            "source_url=" + ARCHIVE_URL + "\n"
            "source_package_sha256=" + ARCHIVE_SHA256 + "\n"
            "font_sha256=" + FONT_SHA256 + "\n"
            "license_sha256=" + LICENSE_SHA256 + "\n"
            "source=Ubuntu_24.04_fonts-dejavu-core_2.37-8\n"
            "installation=NONE_READ_ONLY_CONTAINER_MOUNTS\n",
            encoding="utf-8",
        )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print("Ubuntu font AND license verified by original SHA-256 and staged read-only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    try:
        stage(args.work.absolute())
    except (
        OSError, ValueError, URLError,
        subprocess.CalledProcessError, subprocess.TimeoutExpired,
    ) as error:
        print("ORIGINAL FONT STAGING BLOCKED: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
