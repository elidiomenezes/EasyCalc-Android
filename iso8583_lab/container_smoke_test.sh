#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

echo "Building the interactive ISO 8583 laboratory..."
docker compose build lab

echo "Running the complete test environment inside one container..."
docker compose run --rm --no-TTY lab ./run_all_specs.sh

echo "Running NIBSS 15-MTI TCP smoke (strict coverage gate)..."
docker compose run --rm --no-TTY lab python3 nibss_smoke_15.py

echo "CONTAINER SMOKE TEST PASSED."
