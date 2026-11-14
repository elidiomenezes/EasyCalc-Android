#!/usr/bin/env bash
set -euo pipefail
for tool in gcc g++ cmake make gdb python3 git; do
  command -v "$tool" >/dev/null || { echo "Missing: $tool"; exit 1; }
done
cmake -S . -B /tmp/iso8583-course-build
cmake --build /tmp/iso8583-course-build
/tmp/iso8583-course-build/course_check
python3 scripts/check_python.py
echo "Environment verification PASSED"
