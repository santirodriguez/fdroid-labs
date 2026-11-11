#!/usr/bin/env bash
set -Eeuo pipefail

# Run ONLY inside the non-root Docker instance configured by the manual
# GitHub workflow. This is a source build, NOT a VM-equivalent F-Droid build.
cd /work/fdroid
app=org.cajapersonal.sudokura
source_sha=b057341c84cd988cd15b3329507aaa6151449f5b
mkdir -p logs
printf 'result=INCOMPLETE\nvm_equivalence=NOT_TESTED\nsigning=NOT_RUN\nexternal_submission=NOT_RUN\n' > logs/outcome.txt

on_exit() {
  code=$?
  if (( code != 0 )); then
    printf 'result=FAILED exit=%s\n' "$code" >> logs/outcome.txt
    echo 'CLEAN CONTAINER PROBE FAILED. Diagnostic log excerpts:' >&2
    for log in logs/readmeta.log logs/lint.log logs/scanner.log logs/build.log logs/buildlog.log logs/signature_copy.log; do
      if [[ -f "$log" ]]; then
        printf '\n--- %s (last 90 lines) ---\n' "$log" >&2
        tail -n 90 "$log" >&2
      fi
    done
  fi
}
trap on_exit EXIT

[[ "$(id -u)" != 0 ]] || { echo 'Refusing root execution' >&2; exit 2; }
[[ "$HOME" == /work/fdroid/home ]] || { echo 'Unexpected HOME' >&2; exit 2; }
[[ "$ANDROID_HOME" == /opt/android-sdk ]] || { echo 'Unexpected SDK mount' >&2; exit 2; }
[[ "$GRADLE_USER_HOME" == /work/fdroid/gradle-home ]] || {
  echo 'Unexpected Gradle cache location' >&2; exit 2;
}
[[ -d mirror/sudokura.git ]] || { echo 'Fresh local source mirror absent' >&2; exit 2; }
[[ ! -e "build/$app" ]] || { echo 'Build source checkout already exists' >&2; exit 2; }
[[ ! -e gradle-home/caches ]] || { echo 'Prewarmed Gradle cache forbidden' >&2; exit 2; }
[[ ! -d "$HOME/.ssh" && ! -f "$HOME/.git-credentials" ]] || {
  echo 'Credentials present in disposable HOME' >&2; exit 2;
}
for variable in GITHUB_TOKEN GH_TOKEN CI_JOB_TOKEN GITLAB_TOKEN SSH_AUTH_SOCK; do
  if printenv "$variable" >/dev/null; then
    echo "Unexpected credential-bearing environment variable: $variable" >&2
    exit 2
  fi
done
[[ "$(git --git-dir=mirror/sudokura.git rev-parse HEAD)" == "$source_sha" ]] || {
  echo 'Wrong local mirrored source' >&2; exit 2;
}
grep -Fxq 'Repo: file:///work/fdroid/mirror/sudokura.git' "metadata/$app.yml" || {
  echo 'Refusing non-local F-Droid source checkout' >&2; exit 2;
}
if grep -Eq '^[[:space:]]*binary:' "metadata/$app.yml"; then
  echo 'Unpublished binary URL must be absent only from temporary metadata' >&2
  exit 2
fi
[[ -x "$ANDROID_HOME/build-tools/35.0.0/aapt" ]] || {
  echo 'Missing Android Build Tools 35 aapt' >&2; exit 2;
}
[[ -d "$ANDROID_HOME/ndk/28.2.13676358" ]] || {
  echo 'Missing pinned Android NDK' >&2; exit 2;
}
[[ -d "$ANDROID_HOME/platforms/android-36" ]] || {
  echo 'Missing compile SDK 36' >&2; exit 2;
}

# F-Droid applies metadata patches while scanning and building sources.
command -v patch >/dev/null 2>&1 || {
  echo 'Missing patch executable required by F-Droid metadata' >&2; exit 2;
}

{
  printf 'source_sha=%s\n' "$source_sha"
  printf 'execution=fresh_disposable_Docker_container_with_public_dependency_downloads\n'
  printf 'network=online_public_dependencies_no_credentials\n'
  printf 'gradle_user_home=%s\n' "$GRADLE_USER_HOME"
  fdroid --version
  java -version 2>&1 | head -n 3
  go version
  python3 --version
} > logs/environment.txt

run_check() {
  label="$1"
  shift
  printf '%s=RUNNING\n' "$label" >> logs/outcome.txt
  if "$@" > "logs/$label.log" 2>&1; then
    if [[ "$label" == scanner ]]; then
      printf 'scanner_command=EXIT_ZERO\n' >> logs/outcome.txt
      echo 'Scanner process exited zero; checking for reported problems'
    else
      printf '%s=PASS\n' "$label" >> logs/outcome.txt
      printf '%s PASSED\n' "$label"
    fi
  else
    rc=$?
    printf '%s=FAILED exit=%s\n' "$label" "$rc" >> logs/outcome.txt
    return "$rc"
  fi
}

# No fdroid update/publish/deploy/upload, no signer/key, no network VCS
# fetch (source checkout uses the verified local mirror).
run_check readmeta fdroid readmeta
run_check lint fdroid lint "$app"
# Re-check the exact original Ubuntu font and copyright at the canonical
# paths AFTER read-only Docker mounting. A mismatch blocks the source build;
# the previously established expected SHA-256 values are never changed.
python3 tools/repro-check.py font \
  /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
  /usr/share/doc/fonts-dejavu-core/copyright
run_check scanner fdroid scanner -v "$app:2"
if ! grep -Eq '(^|[[:space:]])0 problems? found' logs/scanner.log; then
  echo 'Scanner did not explicitly report zero problems' >&2
  exit 3
fi
if grep -Eiq '(^|[[:space:]])(WARNING|ERROR|CRITICAL|Traceback)' logs/scanner.log; then
  echo 'Scanner reported warning/error that requires review' >&2
  exit 3
fi

printf 'scanner=PASS_ZERO_PROBLEMS\n' >> logs/outcome.txt
echo 'Scanner verified zero reported problems'

# Test mode builds into tmp; it cannot publish an F-Droid app.
run_check build fdroid build --stop --test --no-refresh --no-tarball "$app:2"
apk="tmp/$app"_2.apk
[[ -s "$apk" ]] || { echo 'Expected unsigned APK missing' >&2; exit 4; }
# Local --test mode skips recipe sudo commands that are reserved for the
# official F-Droid buildserver. Accept ONLY that exact known warning when
# the build log confirms those commands were skipped, never new warnings.
run_check buildlog python3 tools/check-build-log.py logs/build.log
badging="$("$ANDROID_HOME/build-tools/35.0.0/aapt" dump badging "$apk")"
grep -Fq "package: name='$app' versionCode='2' versionName='1.4.1'" <<< "$badging" || {
  echo 'Unexpected rebuilt Android application identity' >&2; exit 4;
}

# The prior original-signed APK's 28 non-signature content hashes are
# independently retained in the immutable probe revision (not build inputs).
# Payload parity is necessary but not sufficient for upstream-signed reproduction.
run_check payload python3 tools/repro-check.py apk "$apk" logs/repro-payload.json
run_check signature_copy python3 tools/verify-signature-copy.py "$apk"

printf 'result=CLEAN_CONTAINER_SOURCE_BUILD_AND_SIGNATURE_COPY_PASS\n' >> logs/outcome.txt
printf 'binary_verification=ORIGINAL_SIGNED_APK_BYTE_IDENTICAL\n' >> logs/outcome.txt
sha256sum "$apk" | tee logs/rebuilt-unsigned-sha256.txt
echo 'CLEAN CONTAINER PASS (original-signed signature copy matched; NOT official F-Droid VM acceptance)'
