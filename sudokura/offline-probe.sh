#!/usr/bin/env bash
set -Eeuo pipefail

# Runs only inside the workflow's network-disabled, unprivileged container.
cd /work/fdroid
mkdir -p logs
APP_ID=org.cajapersonal.sudokura
EXPECTED_SHA=c1b3eb31e82bcc06a078bc10e10f342aa8329e25

if [[ "$(ls -1 /sys/class/net | tr '\n' ' ')" != "lo " ]]; then
  echo 'BLOCKED: the test container has an unexpected network interface' | tee logs/outcome.txt
  exit 90
fi

test -f "metadata/${APP_ID}.yml"
test -d "build/${APP_ID}/.git"
if [[ "$(git -C "build/${APP_ID}" rev-parse HEAD)" != "$EXPECTED_SHA" ]]; then
  echo 'BLOCKED: source commit mismatch' | tee logs/outcome.txt
  exit 91
fi
if [[ -n "${GITHUB_TOKEN:-}${GH_TOKEN:-}${CI_JOB_TOKEN:-}${SSH_AUTH_SOCK:-}" ]]; then
  echo 'BLOCKED: credentials or SSH agent are present' | tee logs/outcome.txt
  exit 92
fi

{
  printf 'source_sha=%s\n' "$EXPECTED_SHA"
  printf 'network_interfaces=loopback_only\n'
  printf 'execution=container_without_network\n'
  printf 'signing=NOT_RUN\n'
  printf 'remote_submission=NOT_RUN\n'
  fdroid --version || true
  java -version 2>&1 | head -n 3
  go version
  python3 --version
} > logs/environment.txt

run_check() {
  local label="$1"
  shift
  printf 'RUNNING %s\n' "$label" | tee logs/outcome.txt
  if "$@" > "logs/${label}.log" 2>&1; then
    printf '%s=PASS\n' "$label" >> logs/outcome.txt
  else
    local status=$?
    printf '%s=FAIL exit=%s\n' "$label" "$status" >> logs/outcome.txt
    echo "BLOCKED: ${label} failed; inspecting the log is required before another run"
    exit "$status"
  fi
}

# No update/deploy/publish/sign commands. Missing offline inputs cause failure.
run_check readmeta fdroid readmeta
run_check lint fdroid lint "$APP_ID"
run_check scanner fdroid scanner "$APP_ID"
run_check build fdroid build --test --no-refresh --no-tarball "${APP_ID}:1"

if find unsigned -maxdepth 1 -type f -name '*.apk' -print -quit 2>/dev/null | grep -q .; then
  find unsigned -maxdepth 1 -type f -name '*.apk' -exec sha256sum {} \; > logs/unsigned-apk-sha256.txt
fi
printf 'result=LOCAL_TEST_COMPLETED\n' >> logs/outcome.txt
