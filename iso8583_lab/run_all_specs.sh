#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

base_port="${BASE_PORT:-18600}"
specs=(
    specs/nibss-v1.16.json
    specs/ascii.json
    specs/binary-bitmap.json
    specs/ascii-bitmap-bcd-length.json
    specs/binary-bitmap-bcd-length.json
    specs/ascii-bitmap-binary-length.json
    specs/ebcdic.json
    specs/ebcdic-binary-bitmap.json
    specs/packed-bcd-numeric.json
)

for index in "${!specs[@]}"; do
    spec="${specs[$index]}"
    port=$((base_port + index))
    echo
    echo "################################################################"
    echo "SPEC $((index + 1))/${#specs[@]}: $spec"
    echo "PORT: $port"
    echo "################################################################"
    SPEC="$spec" PORT="$port" ./run_tests.sh
done

echo
echo "ALL ${#specs[@]} SPECIFICATIONS PASSED."
