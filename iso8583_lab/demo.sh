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
server_rules="${RULES:-rules/rules.json}"
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
        read -r -p "Press Enter to launch the next scenario..."
    fi
}

run_scenario() {
    local title="$1"
    local client_rules="$2"
    local objective="$3"
    local expected="$4"
    echo
    echo "================================================================"
    echo "$title"
    echo "Objective : $objective"
    echo "Rules     : $client_rules"
    echo "Expected  : $expected"
    echo "================================================================"
    "$python_bin" client.py \
        --host "$host" \
        --port "$port" \
        --spec "$spec" \
        --rules "$client_rules" \
        --log-view both \
        --color always
}

echo "Starting the ISO 8583 demonstration server on $host:$port"
"$python_bin" -u server.py \
    --host "$host" \
    --port "$port" \
    --spec "$spec" \
    --rules "$server_rules" \
    --log-view both \
    --color always &
server_pid=$!
sleep 1

if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "Server failed to start" >&2
    exit 1
fi

run_scenario \
    "1. AUTHORIZATION APPROVED" \
    client-rules/authorization-approved.json \
    "Validate PAN, dates and captures, then approve the authorization." \
    "Two legs: 0100 followed by 0110/DE39=00."
pause_demo

run_scenario \
    "2. INVALID LOCAL DATE" \
    client-rules/authorization-invalid-date.json \
    "Reject impossible DE13=0231 through the special date registers." \
    "Two legs: 0100 followed by 0110/DE39=30."
pause_demo

run_scenario \
    "3. INVALID LUHN" \
    client-rules/authorization-invalid-luhn.json \
    "Set the special luhn register to 0 and select the invalid-PAN response." \
    "Two legs: 0100 followed by 0110/DE39=14."
pause_demo

run_scenario \
    "4. AUTHORIZATION DECLINED" \
    client-rules/authorization-declined.json \
    "Use a Luhn-valid PAN ending in 0000 to select a business decline." \
    "Two legs: 0100 followed by 0110/DE39=05."
pause_demo

run_scenario \
    "5. FINANCIAL TRANSACTION" \
    client-rules/financial.json \
    "Select the rules for MTI 0200 and build the financial response." \
    "Two legs: 0200 followed by 0210/DE39=00."
pause_demo

run_scenario \
    "6. REVERSAL REQUEST" \
    client-rules/reversal-request.json \
    "Send a 0400 reversal request and select its dedicated 0410 response template." \
    "Two legs: 0400 followed by 0410/DE39=00, both containing p and 1."
pause_demo

run_scenario \
    "6A. FINANCIAL ADVICE" \
    client-rules/financial-advice.json \
    "Send a completed financial event as advice and acknowledge it." \
    "Two legs: 0220 followed by 0230/DE39=00."
pause_demo

run_scenario \
    "7. REVERSAL ADVICE WITH TWO BITMAPS" \
    client-rules/reversal.json \
    "Send a 0420 reversal advice and select its dedicated 0430 response template." \
    "Two legs: 0420 followed by 0430/DE39=00, both containing p and 1."
pause_demo

run_scenario \
    "8. MESSAGE WITHOUT RESPONSE" \
    client-rules/network-no-response.json \
    "Demonstrate a terminal message whose client and server rules expect no response." \
    "One leg: 0800; the flow ends without an error or response."
pause_demo

run_scenario \
    "8A. ADMINISTRATIVE REQUEST" \
    client-rules/administrative-request.json \
    "Request the status of administrative parameters through DE60." \
    "Two legs: 0600 followed by 0610/DE39=00."
pause_demo

run_scenario \
    "8B. NETWORK SIGN-ON" \
    client-rules/network-sign-on.json \
    "Perform a network call-home using DE3=9D0000." \
    "Two legs: 0800 followed by 0810/DE39=00; both messages contain p and 1."
pause_demo

run_scenario \
    "9. THREE-LEG AUTHORIZATION" \
    client-rules/three-leg-authorization.json \
    "Process 0110 on the client, capture STAN/RRN, and build a final confirmation." \
    "Three legs: 0100, 0110/DE39=00, then terminal 0120; no fourth leg."

echo
echo "Demonstration completed."
