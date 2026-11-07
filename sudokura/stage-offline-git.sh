#!/usr/bin/env bash
set -Eeuo pipefail

# Prepare a Git-only, offline F-Droid source mirror from a verified checkout.
# No F-Droid VCS state files are synthesized: fdroidserver creates its own.
if (( $# != 4 )); then
  echo 'usage: stage-offline-git.sh SOURCE_CHECKOUT WORKDIR METADATA_TEMPLATE SOURCE_SHA' >&2
  exit 2
fi

source_root="$(realpath "$1")"
work="$(realpath "$2")"
template="$(realpath "$3")"
source_sha="$4"
app_id=org.cajapersonal.sudokura
mirror="$work/mirror/sudokura.git"

[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid source SHA' >&2; exit 3; }
[[ "$(git -C "$source_root" rev-parse HEAD)" == "$source_sha" ]] || {
  echo 'Source checkout does not match the immutable commit' >&2; exit 4;
}
[[ ! -e "$mirror" ]] || { echo 'Mirror already exists; fresh staging required' >&2; exit 5; }
[[ ! -e "$work/build/$app_id" ]] || { echo 'An app checkout already exists' >&2; exit 6; }

mkdir -p "$work/mirror" "$work/metadata" "$work/build" "$work/logs"
git init -q --bare "$mirror"
# The original checkout can have detached HEAD and be shallow. Fetch the exact
# verified local object into an explicit, deterministic reference.
git --git-dir="$mirror" fetch -q --no-tags --update-shallow "$source_root" \
  "$source_sha:refs/heads/locked-source"
git --git-dir="$mirror" symbolic-ref HEAD refs/heads/locked-source
[[ "$(git --git-dir="$mirror" rev-parse HEAD)" == "$source_sha" ]] || {
  echo 'Source mirror differs from the verified commit' >&2; exit 7;
}
[[ "$(git --git-dir="$mirror" rev-parse HEAD^{tree})" == \
   "$(git -C "$source_root" rev-parse HEAD^{tree})" ]] || {
  echo 'Source tree differs from the verified checkout' >&2; exit 8;
}

# Only the disposable test metadata is redirected to the file-backed mirror.
# The version-controlled candidate continues to identify public GitHub source.
python3 - "$template" "$work/metadata/$app_id.yml" "$source_sha" <<'PY'
import pathlib
import sys

template, output, commit = map(pathlib.Path, sys.argv[1:])
source = template.read_text(encoding='utf-8')
repo = 'Repo: https://github.com/santirodriguez/Sudokura.git'
record = f'commit: {commit}'
if source.count(repo) != 1 or source.count(record) != 1:
    raise SystemExit('Metadata source or commit was not the verified expected value')
local_repo = 'Repo: file:///work/fdroid/mirror/sudokura.git'
output.write_text(source.replace(repo, local_repo), encoding='utf-8')
PY

test -s "$work/metadata/$app_id.yml"
printf 'upstream_sha=%s\nupstream_tree=%s\nsource_type=verified_local_git_mirror\nmetadata_mode=local_only_file_repo\n' \
  "$source_sha" "$(git --git-dir="$mirror" rev-parse HEAD^{tree})" \
  > "$work/logs/source-provenance.txt"
