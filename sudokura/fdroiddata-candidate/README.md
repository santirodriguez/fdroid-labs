# Sudokura 1.4.1 F-Droid upstream-signed metadata candidate

**Status: prepared, NOT submitted, NOT validated on an official F-Droid buildserver.**

This directory is a staging representation of the intended `fdroiddata` paths:

- `metadata/org.cajapersonal.sudokura.yml`
- `metadata/org.cajapersonal.sudokura/native-paths.patch`
- `metadata/org.cajapersonal.sudokura/source-only.patch`
- `metadata/org.cajapersonal.sudokura/signer35-align.patch`

The recipe pins the exact original-signed Sudokura source revision
`b057341c84cd988cd15b3329507aaa6151449f5b`, Android versionName 1.4.1,
versionCode 2, the public GitHub Release APK filename and certificate SHA-256.
The `binary:` URL becomes usable **only after** the separately authorized
GitHub tag and release actually publish that exact APK; it is not live now.

## Source-build strategy

1. `sudo`: provision standard build dependencies (Go and DejaVu) in a clean
   F-Droid VM. The font file and its license must match the exact recorded
   SHA-256 checks; do not accept a different installed font silently.
2. F-Droid applies three GPL-compatible source/utility patches in its
   disposable checkout, never to the upstream repository.
3. `prebuild`: fetch and SHA-256 verify the three SDL **source** archives from
   upstream's committed `android/dependencies.lock.json`; extract sources,
   remove the downloads so the F-Droid source scanner can inspect the source
   trees without archive clutter.
4. `build`: fetch and verify Gradle 8.13 from the same lock; build deterministic
   assets with Go; run the checked-out project's Gradle 8.13/AGP 8.11.1
   productionRelease variant, ARM64/NDK 28.2.13676358, unsigned.
5. `postbuild`: rewrite ZIP padding in the unsigned APK to the 16-KiB
   `0xd935` extra-field representation produced by Android Build Tools 35.
   Compressed payload bytes are copied unchanged. F-Droid must then use its
   normal upstream-signed APK signature-copy verification and enforce
   `AllowedAPKSigningKeys`; this recipe contains no signing secret.

## Evidence, not automatic approval

- Source-built Android APK: [fdroid-labs run #42906634993](https://github.com/santirodriguez/fdroid-labs/actions/runs/42906634993), 28/28 payload members match the original developer-signed APK; all native compiler-path flags propagated; the F-Droid scanner and local build passed.
- Existing signed GitHub APK SHA-256: `06e06d8b8301384a37876b978d0fb18552b3601487628e7465e1cec33a3836b4`.
- Lab unsigned APK SHA-256: `5b0090e0db2c45906a93525f1d81ba95869f059bab400f25e2d856d19423f6a4`.
- Local read-only verification using the original APK and new unsigned APK:
  direct signature copy **fails** v3 content digest; normalizing ZIP padding to
  16 KiB before copying produces the **exact original signed bytes**, including
  valid RSA v3 signature and same original certificate SHA-256
  `fde951e3d2ef42e41c7186ee965944aeca549d590ad080711dd3d875f82df66d`.
  No production signing key was used.

## Still required before an official F-Droid merge request

- A **single clean, genuine F-Droid buildserver run** of THIS candidate recipe,
  not the existing prewarmed lab recipe. This will determine whether the
  actual F-Droid VM can download the SHA-pinned source/Gradle dependencies and
  obtain the exact same font/license/Go/toolchain outputs. The candidate has
  not been tested on that VM; do not label it portable-verified yet.
- Review license/source policy and scanner output on the staged SDL source
  archives, bundled FreeType, fonts, audio and icon/flag attribution.
- Confirm that F-Droid's published `apksigcopier`/`fdroid publish` uses the
  normalized unsigned output in `postbuild` and verifies the true v3 signature.
  The current metadata/patches have been structurally validated only.
- After separately approving PR #23 merge and publishing original-signed
  GitHub v1.4.1, confirm the exact public `binary:` URL and SHA-256, and then
  explicitly authorize any F-Droid/GitLab submission. Do not submit the
  current unpublished URL or attempt to sign again.

No modifications to Sudokura or its signed APK, release tag, GitLab, F-Droid,
keystore or production permissions are part of this candidate.
