#!/usr/bin/env bash
set -euo pipefail

step() { printf '\n========== %s ==========\n' "$1"; }
fail() { echo "FAILED at line $1: $2" >&2; }
trap 'fail "$LINENO" "$BASH_COMMAND"' ERR

step "1/5 Checking development tools"
for tool in gcc g++ cmake make ninja gdb python3 git pkg-config ncat nc curl jq xxd sqlite3; do
  path="$(command -v "$tool")" || { echo "MISSING: $tool" >&2; exit 1; }
  printf '  [OK] %-12s %s\n' "$tool" "$path"
done
echo
g++ --version | head -n 1
cmake --version | head -n 1
python3 --version

step "2/5 Checking Python ISO 8583 package"
python3 -u -c 'import iso8583; print("  [OK] pyiso8583 imported from", iso8583.__file__)'

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
step "3/5 Generating C++ test source"
cat > "$tmp/main.cpp" <<'CPP'
#include <boost/asio.hpp>
#include <openssl/evp.h>
#include <sqlite3.h>
#include <iostream>
int main() {
  boost::asio::io_context io;
  std::cout << "  [OK] Boost.Asio io_context created\n";
  sqlite3* db = nullptr;
  if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 1;
  std::cout << "  [OK] SQLite3 in-memory database opened\n";
  sqlite3_close(db);
  if (!EVP_sha256()) return 2;
  std::cout << "  [OK] OpenSSL SHA-256 available\n";
  return 0;
}
CPP
cat "$tmp/main.cpp"

step "4/5 Compiling and linking C++17 executable"
cmd=(g++ -std=c++17 -Wall -Wextra -pthread "$tmp/main.cpp" -o "$tmp/check" -lsqlite3 -lssl -lcrypto)
printf '  $ '; printf '%q ' "${cmd[@]}"; printf '\n'
"${cmd[@]}"
echo "  [OK] Compilation and linking completed"

step "5/5 Executing compiled program"
"$tmp/check"
echo
echo "========== SMOKE TEST PASSED =========="
