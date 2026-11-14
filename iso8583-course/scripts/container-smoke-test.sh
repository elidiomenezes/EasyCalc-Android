#!/usr/bin/env bash
set -euo pipefail
for tool in gcc g++ cmake make ninja gdb python3 git pkg-config ncat nc curl jq xxd sqlite3; do
  command -v "$tool" >/dev/null || { echo "Missing: $tool" >&2; exit 1; }
done
python3 -c 'import iso8583; print("pyiso8583 OK")'
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/main.cpp" <<'CPP'
#include <boost/asio.hpp>
#include <openssl/evp.h>
#include <sqlite3.h>
#include <iostream>
int main() {
  boost::asio::io_context io;
  sqlite3* db = nullptr;
  if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 1;
  sqlite3_close(db);
  if (!EVP_sha256()) return 2;
  std::cout << "Boost.Asio + SQLite3 + OpenSSL OK\n";
}
CPP
g++ -std=c++17 -Wall -Wextra -pthread "$tmp/main.cpp" -o "$tmp/check" -lsqlite3 -lssl -lcrypto
"$tmp/check"
echo "SMOKE TEST PASSED"
