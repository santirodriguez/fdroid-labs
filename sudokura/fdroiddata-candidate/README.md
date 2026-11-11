# Sudokura 1.4.1: unsubmitted F-Droid source-build candidate

**Not submitted to F-Droid; not validated in an official buildserver VM.**
This directory mirrors the future `fdroiddata/metadata/` paths for review.
Use the existing published original-signed APK, not a new release or signing key.

## Exact inputs

- Git source commit: `b057341c84cd988cd15b3329507aaa6151449f5b` (same tree as published tag `v1.4.1`).
- Android ID `org.cajapersonal.sudokura`, version `1.4.1`, code `2`; ARM64 production-only.
- Public signed APK: [Sudokura-1.4.1-Android-arm64.apk](https://github.com/santirodriguez/Sudokura/releases/download/v1.4.1/Sudokura-1.4.1-Android-arm64.apk), SHA-256 `06e06d8b8301384a37876b978d0fb18552b3601487628e7465e1cec33a3836b4`.
- Original signer certificate: `fde951e3d2ef42e41c7186ee965944aeca549d590ad080711dd3d875f82df66d`.

The candidate includes four disposable source patches: `native-paths.patch`,
`source-only.patch`, `signer35-align.patch`, and `pinned-font.patch`.
`sudo` installs Go but **does not substitute Debian's different DejaVu font**.
Before scanning, the new font helper downloads Ubuntu Noble's exact public
`fonts-dejavu-core_2.37-8_all.deb`, verifies its complete SHA-256, extracts
only the original font and license into `android/.cache/fdroid-font/`, and
checks both original file hashes. No system package/file is overwritten.
The source and Gradle archives are separately verified from the upstream lock.

During the build, native path normalization and exact Gradle/NDK versions
preserve the 28 APK payload files. The postbuild patch restores Android Build
Tools 35 ZIP padding, after which F-Droid must copy and verify the original
APK v2/v3 signatures and `AllowedAPKSigningKeys`. F-Droid may skip a version
if this verification fails; no alternate signing identity is authorized.

## Proof and remaining gates

The earlier [clean Docker run #42966953651](https://github.com/santirodriguez/fdroid-labs/actions/runs/42966953651)
passed fdroid readmeta/lint/scanner (zero problems), built from source, and
matched all 28 original APK payload members. This established **neither**
official VM parity nor signature-copy reproducibility.

A new manual-only public GitHub Actions run on the candidate branch must
exercise its updated source-only recipe, font staging, full local source
build and **actual original-signature copy**, comparing the completed APK
byte-for-byte with the public release and verifying the original certificate.
A passing Docker run remains a proxy, not an official F-Droid VM/CI pass.
An official fdroiddata Merge Request requires separate maintainer approval.
No original binary/keystore changes or app-store contact are performed here.
