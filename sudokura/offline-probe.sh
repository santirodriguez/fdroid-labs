#!/usr/bin/env bash
set -Eeuo pipefail

# Only run from the unprivileged Docker container configured with --network none.
cd /work/fdroid
mkdir -p logs
: > logs/outcome.txt
APP_ID=org.cajapersonal.sudokura
EXPECTED_SHA=b057341c84cd988cd15b3329507aaa6151449f5b

fail() {
  local reason="$1"
  local status="${2:-1}"
  printf 'result=FAIL reason=%s\n' "$reason" >> logs/outcome.txt
  printf 'PROBE BLOCKED: %s\n' "$reason" >&2
  exit "$status"
}

network_devices="$(ls -1 /sys/class/net)"
[[ "$network_devices" == 'lo' ]] || fail 'container_has_nonloopback_network' 90
[[ -z "${GITHUB_TOKEN:-}${GH_TOKEN:-}${CI_JOB_TOKEN:-}${SSH_AUTH_SOCK:-}" ]] || \
  fail 'credentials_or_ssh_agent_present' 92
[[ -f "metadata/$APP_ID.yml" ]] || fail 'local_metadata_missing'
[[ -d mirror/sudokura.git ]] || fail 'verified_source_mirror_missing'
[[ ! -e "build/$APP_ID" ]] || fail 'unexpected_preexisting_source_checkout'
[[ "$(git --git-dir=mirror/sudokura.git rev-parse HEAD)" == "$EXPECTED_SHA" ]] || \
  fail 'local_mirror_sha_mismatch'

grep -Fxq 'Repo: file:///work/fdroid/mirror/sudokura.git' "metadata/$APP_ID.yml" || \
  fail 'metadata_source_is_not_the_local_mirror'

# The original Gradle distribution is exposed read-only from a verified archive.
gradle=/opt/gradle-8.13/bin/gradle
[[ -x "$gradle" ]] || fail 'verified_gradle_executable_missing'
[[ -r /work/verified-inputs/dependencies.lock.json ]] || fail 'verified_android_inputs_missing'
if ! gradle_output="$("$gradle" --version 2>&1)"; then
  fail 'gradle_version_command_failed'
fi
grep -Fxq 'Gradle 8.13' <<< "$gradle_output" || fail 'wrong_gradle_version'

{
  printf 'source_sha=%s\n' "$EXPECTED_SHA"
  printf 'network_interfaces=loopback_only\n'
  printf 'execution=container_without_network\n'
  printf 'signing=NOT_RUN\n'
  printf 'remote_submission=NOT_RUN\n'
  printf 'verified_gradle_version=8.13\n'
  fdroid --version || true
  java -version 2>&1 | head -n 3
  go version
  python3 --version
} > logs/environment.txt

run_check() {
  local label="$1"
  shift
  printf 'RUNNING %s\n' "$label" >> logs/outcome.txt
  if "$@" > "logs/${label}.log" 2>&1; then
    printf '%s_command=PASS\n' "$label" >> logs/outcome.txt
  else
    local rc=$?
    printf '%s_command=FAIL exit=%s\n' "$label" "$rc" >> logs/outcome.txt
    fail "${label}_command_failed" "$rc"
  fi
}

verify_check() {
  local label="$1"
  shift
  if python3 tools/verify-probe.py "$@" >> "logs/${label}.verify.log" 2>&1; then
    printf '%s_verified=PASS\n' "$label" >> logs/outcome.txt
  else
    printf '%s_verified=FAIL\n' "$label" >> logs/outcome.txt
    fail "${label}_verification_failed"
  fi
}

# Local fdroiddata-style recipe; no init, update, publish, deploy, upload or signing.
run_check readmeta fdroid readmeta
run_check lint fdroid lint "$APP_ID"
run_check scanner fdroid scanner -v "${APP_ID}:2"
verify_check scanner scanner logs/scanner.log
verify_check source source /work/fdroid

# The --stop flag forces fdroidserver 2.4.5 to return nonzero on build errors.
run_check build fdroid build --stop --test --no-refresh --no-tarball "${APP_ID}:2"
verify_check build build logs/build.log
verify_check source_after_build source /work/fdroid
verify_check apk apk "tmp/${APP_ID}_2.apk" \
  --aapt "$ANDROID_HOME/build-tools/35.0.0/aapt" \
  --receipt logs/unsigned-apk-sha256.txt \
  --notice-source "build/$APP_ID/assets/flags/LICENSE-MIT.txt"

printf 'result=REAL_OFFLINE_FDROID_TEST_PASSED\n' >> logs/outcome.txt
