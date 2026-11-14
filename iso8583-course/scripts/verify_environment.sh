#!/usr/bin/env bash
set -euo pipefail
for tool in gcc g++ cmake make ninja gdb python3 git pkg-config ncat nc curl jq xxd sqlite3; do
  command -v "$tool" >/dev/null || { echo "Missing: $tool"; exit 1; }
done
cmake -S . -B /tmp/iso8583-course-build
cmake --build /tmp/iso8583-course-build
/tmp/iso8583-course-build/course_check
python3 -c 'import iso8583; print("pyiso8583 verification PASSED")'
python3 scripts/check_python.py
echo "Environment verification PASSED"
