#!/usr/bin/env bash
# this_file: native-drivers/realuse/run_all.sh
# Run real-use targets one fl-native session each (crash isolation); logs beside results.
# Usage: native-drivers/realuse/run_all.sh OUT_DIR [ID...]   (no IDs: every manifest target)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WS="$(cd "$REPO" && while [[ ! -x verification/issue-104/fl-native.sh && "$PWD" != / ]]; do cd ..; done; pwd)"
OUT="$1"; shift
mkdir -p "$OUT"
MANIFEST="$REPO/realuse/manifest.json"
IDS=("$@")
# No IDs: every manifest target except quarantined ones (curation key "quarantine").
[[ ${#IDS[@]} -gt 0 ]] || IDS=($(python3 -c "import json,sys;print(' '.join(t['id'] for t in json.load(open(sys.argv[1]))['targets'] if not t.get('quarantine')))" "$MANIFEST"))
for id in "${IDS[@]}"; do
  export REALUSE_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  log="$OUT/$id-$REALUSE_STAMP.log"
  "$WS/verification/issue-104/fl-native.sh" --mutating --lane G1 -- \
    uv run --quiet --project "$WS/fontlab-remopy" python "$HERE/run_realuse.py" \
    --manifest "$MANIFEST" --out "$OUT" "$id" > "$log" 2>&1
  rc=$?
  echo "$id rc=$rc"
  grep -E '^[a-z0-9-]+: (passed|failed|classified)' "$log" | tail -1
  # Anything but pass/fail (refused, blocked, host down, crash, host still busy):
  # stop here; never keep queueing runs against a host in an unknown state.
  if [[ $rc -ne 0 && $rc -ne 1 ]]; then echo "run_all: stopping after $id (rc=$rc)"; exit "$rc"; fi
done
