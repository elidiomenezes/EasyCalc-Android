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
rules="${RULES:-rules/rules.json}"
server_pid=""

cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

run_case() {
    local label="$1"
    local client_rules="$2"
    local objective="$3"
    local expected="$4"
    echo
    echo "===== $label ====="
    echo "Objective : $objective"
    echo "Rules     : $client_rules"
    echo "Expected  : $expected"
    "$python_bin" client.py \
        --host "$host" \
        --port "$port" \
        --spec "$spec" \
        --rules "$client_rules" \
        --log-view both \
        --color always
}

echo "===== UNIT TESTS ====="
echo "Objective : Validate encoding, binary bitmap, rule selection, registers, Luhn, sed templates, no-response behavior, and escaped raw rendering."
echo "Expected  : 24 tests ending in OK."
"$python_bin" -m unittest -v

echo
echo "===== STARTING SERVER ON $host:$port ====="
"$python_bin" -u server.py \
    --host "$host" \
    --port "$port" \
    --spec "$spec" \
    --rules "$rules" \
    --log-view both \
    --color always &
server_pid=$!
sleep 1

if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "Server failed to start" >&2
    exit 1
fi

run_case \
    "AUTHORIZATION APPROVED" \
    client-rules/authorization-approved.json \
    "Validate a Luhn-valid PAN, capture pan4 and STAN, and select the approval template." \
    "Response MTI 0110, DE39=00, and DE44 containing PAN4=1111,STAN=100001."
run_case \
    "INVALID LOCAL DATE" \
    client-rules/authorization-invalid-date.json \
    "Resolve the dynamic clocks, reject impossible DE13=0231, and select the format-error response." \
    "Response MTI 0110 and DE39=30."
run_case \
    "INVALID LUHN" \
    client-rules/authorization-invalid-luhn.json \
    "Verify that the special luhn register becomes 0 and selects the invalid-PAN rule." \
    "Response MTI 0110 and DE39=14."
run_case \
    "AUTHORIZATION DECLINED" \
    client-rules/authorization-declined.json \
    "Use a Luhn-valid PAN ending in 0000 and select the business decline rule." \
    "Response MTI 0110 and DE39=05."
run_case \
    "FINANCIAL TRANSACTION" \
    client-rules/financial.json \
    "Select the rule file for MTI 0200 and build its default financial response." \
    "Response MTI 0210 and DE39=00."
run_case \
    "FINANCIAL ADVICE" \
    client-rules/financial-advice.json \
    "Send MTI 0220 and acknowledge the completed financial event." \
    "Response MTI 0230, DE39=00, and the original STAN is echoed."
run_case \
    "REVERSAL REQUEST" \
    client-rules/reversal-request.json \
    "Exercise the request form of a reversal and its dedicated response template." \
    "Response MTI 0410, DE39=00, and DE90 is copied; request and response use two bitmaps."
run_case \
    "REVERSAL WITH TWO BITMAPS" \
    client-rules/reversal.json \
    "Exercise the advice form of a reversal, use DE90 to force two bitmaps, and build its dedicated 0430 response." \
    "Request and response contain p and 1; response MTI 0430, DE39=00, and DE90 is copied."

run_case \
    "ADMINISTRATIVE REQUEST" \
    client-rules/administrative-request.json \
    "Exchange an administrative parameter-status request using MTI 0600." \
    "Response MTI 0610, DE39=00, and DE60 is echoed."
run_case \
    "NETWORK SIGN-ON" \
    client-rules/network-sign-on.json \
    "Perform network sign-on with DE70=001, forcing a secondary bitmap." \
    "Response MTI 0810, DE39=00, and DE70=001; request and response use two bitmaps."

run_case \
    "MTI CONFIGURED WITHOUT RESPONSE" \
    client-rules/network-no-response.json \
    "Send one terminal message whose client action expects no response and whose server default is null." \
    "One leg only; both engines finish without treating the missing response as an error."
run_case \
    "THREE-LEG AUTHORIZATION" \
    client-rules/three-leg-authorization.json \
    "Send 0100, process 0110 with client rules, capture STAN/RRN, and send final 0120 confirmation." \
    "Leg 1=0100, leg 2=0110/DE39=00, leg 3=0120 using the captured STAN and RRN; no fourth leg."

echo
echo "===== ALL TESTS COMPLETED ====="
