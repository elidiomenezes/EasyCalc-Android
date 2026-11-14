#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

if [[ -n "${PYTHON_BIN:-}" ]]; then
    python_bin="$PYTHON_BIN"
elif [[ -x .venv/Scripts/python.exe ]]; then
    python_bin=.venv/Scripts/python.exe
elif [[ -x .venv/bin/python ]]; then
    python_bin=.venv/bin/python
else
    python_bin=python3
fi

host="${HOST:-127.0.0.1}"
port="${PORT:-18583}"
spec="${SPEC:-specs/nibss-v1.16.json}"
server_pid=""

cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

pause_demo() {
    if [[ "${DEMO_AUTO:-0}" != "1" ]]; then
        echo
        read -r -p "Press Enter for the next MTI pair..."
    fi
}

run_pair() {
    local pair="$1"
    local purpose="$2"
    local client_rules="$3"
    echo
    echo "================================================================"
    echo "$pair — $purpose"
    echo "================================================================"
    "$python_bin" client.py \
        --host "$host" \
        --port "$port" \
        --spec "$spec" \
        --rules "$client_rules" \
        --log-view both \
        --color always
}

"$python_bin" -u server.py \
    --host "$host" \
    --port "$port" \
    --spec "$spec" \
    --rules rules/rules.json \
    --log-view both \
    --color always &
server_pid=$!
sleep 1

run_pair "0100 / 0110" "Authorization request and response" \
    client-rules/authorization-approved.json
pause_demo
run_pair "0220 / 0230" "Financial advice and acknowledgement" \
    client-rules/financial-advice.json
pause_demo
run_pair "0420 / 0430" "Reversal advice and response" \
    client-rules/reversal.json
pause_demo
run_pair "0600 / 0610" "Administrative request and response" \
    client-rules/administrative-request.json
pause_demo
run_pair "0800 / 0810" "Network sign-on and response" \
    client-rules/network-sign-on.json

echo
echo "All five MTI pairs completed."
