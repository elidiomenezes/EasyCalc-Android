#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${1:-$project_dir}"

if [[ ! -d "$target" ]]; then
    echo "Not a directory: $target" >&2
    exit 2
fi

target="$(cd "$target" && pwd -P)"
if [[ "$target" == "/" ]]; then
    echo "Refusing to scan the filesystem root." >&2
    exit 2
fi

echo "Purging Zone.Identifier recursively under: $target"

literal_count=0
while IFS= read -r -d '' sidecar; do
    echo "Removing sidecar: $sidecar"
    rm -- "$sidecar"
    literal_count=$((literal_count + 1))
done < <(find "$target" -type f -name '*:Zone.Identifier' -print0)

ads_status="not available"
if command -v powershell.exe >/dev/null 2>&1 && command -v cygpath >/dev/null 2>&1; then
    export ZONE_PURGE_TARGET="$(cygpath -w "$target")"
    powershell.exe -NoProfile -NonInteractive -Command \
        'Get-ChildItem -LiteralPath $env:ZONE_PURGE_TARGET -Recurse -File | Unblock-File'
    ads_status="purged recursively with PowerShell"
fi

echo "Literal :Zone.Identifier files removed: $literal_count"
echo "NTFS alternate data streams: $ads_status"
