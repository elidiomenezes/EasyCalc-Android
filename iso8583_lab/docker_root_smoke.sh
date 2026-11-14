#!/usr/bin/env bash
set -uo pipefail
cd /app
failed=0
run() {
  echo "=== $1 ==="
  shift
  "$@" || failed=1
}
run "Unit tests" python3 -m unittest -v test_iso8583_lab
run "TCP frame policy" python3 -m unittest -v test_frame_policy
run "15 MTI TCP smoke (configured flows + no-rule behavior)" python3 nibss_smoke_15.py
if (( failed )); then
  echo "SMOKE TEST FAILED: inspect failures and coverage gaps above"
  exit 1
fi
echo "SMOKE TEST PASSED"
