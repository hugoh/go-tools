#!/usr/bin/env bash
#MISE description="Verify every template/ file carries the copier-managed marker"
set -euo pipefail
cd "$(dirname "$0")/.."

MARKER="managed by hugoh/go-tools via copier"

files=("$@")
if [ "${#files[@]}" -eq 0 ]; then
  while IFS= read -r f; do
    files+=("$f")
  done < <(git ls-files template/)
fi

missing=()
for f in "${files[@]}"; do
  case "$f" in
  *_copier_conf.answers_file*) continue ;;
  esac
  [ -f "$f" ] || continue
  grep -qF "$MARKER" "$f" || missing+=("$f")
done

if [ "${#missing[@]}" -gt 0 ]; then
  printf 'Missing "%s" marker:\n' "$MARKER" >&2
  printf '  %s\n' "${missing[@]}" >&2
  exit 1
fi
