#!/usr/bin/env bash
set -euo pipefail

cd /app

step() { printf '\n========== %s ==========\n' "$1"; }

step "1/7 Development tools and command-line utilities"
for tool in gcc g++ cmake make ninja gdb git python3 pkg-config ncat nc curl jq xxd sqlite3 openssl; do
  command -v "$tool" >/dev/null || { echo "MISSING TOOL: $tool" >&2; exit 1; }
  printf '[OK] %s: %s\n' "$tool" "$(command -v "$tool")"
done
gcc --version | head -n 1
g++ --version | head -n 1
cmake --version | head -n 1
python3 --version

step "2/7 Python runtime and installed dependencies"
python3 -m pip check
python3 - <<'PY'
import importlib.metadata
import iso8583
assert importlib.metadata.version("pyiso8583") == "4.0.1", "Wrong pyiso8583 version"
print("[OK] pyiso8583 4.0.1:", iso8583.__file__)
PY

step "3/7 Native library metadata (OpenSSL and SQLite3)"
pkg-config --exists openssl sqlite3
printf '[OK] OpenSSL: %s\n' "$(pkg-config --modversion openssl)"
printf '[OK] SQLite3: %s\n' "$(pkg-config --modversion sqlite3)"

step "4/7 Compile, link and execute C11/C++17 using CMake, Ninja and Make"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/CMakeLists.txt" <<'CMAKE'
cmake_minimum_required(VERSION 3.16)
project(iso8583_environment_check LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Threads REQUIRED)
find_package(Boost REQUIRED COMPONENTS system)
find_package(OpenSSL REQUIRED)
find_package(SQLite3 REQUIRED)
add_executable(c_check main.c)
add_executable(cpp_check main.cpp)
target_include_directories(cpp_check PRIVATE ${Boost_INCLUDE_DIRS})
target_link_libraries(cpp_check PRIVATE Threads::Threads Boost::system OpenSSL::SSL OpenSSL::Crypto SQLite::SQLite3)
CMAKE

cat > "$tmp/main.c" <<'C'
#include <stdio.h>
int main(void) {
  puts("[OK] GCC C11 binary executed");
  return 0;
}
C

cat > "$tmp/main.cpp" <<'CPP'
#include <boost/asio.hpp>
#include <boost/system/error_code.hpp>
#include <openssl/evp.h>
#include <openssl/ssl.h>
#include <sqlite3.h>
#include <iostream>

int main() {
  boost::asio::io_context io;
  boost::system::error_code ec;
  auto address = boost::asio::ip::make_address("127.0.0.1", ec);
  if (ec || !address.is_v4()) return 1;

  sqlite3 *db = nullptr;
  if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 2;
  int sql_rc = sqlite3_exec(db, "CREATE TABLE test (x INTEGER); INSERT INTO test VALUES (8583);", nullptr, nullptr, nullptr);
  sqlite3_close(db);
  if (sql_rc != SQLITE_OK) return 3;

  if (EVP_sha256() == nullptr) return 4;
  SSL_CTX *tls = SSL_CTX_new(TLS_method());
  if (tls == nullptr) return 5;
  SSL_CTX_free(tls);

  std::cout << "[OK] Boost.Asio + Boost.System + SQLite3 + OpenSSL (SSL/Crypto) linked and executed\n";
  return 0;
}
CPP

cmake -S "$tmp" -B "$tmp/build-ninja" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$tmp/build-ninja" --parallel 2
"$tmp/build-ninja/c_check"
"$tmp/build-ninja/cpp_check"

# Verify the Make backend independently, rather than merely checking that make exists.
cmake -S "$tmp" -B "$tmp/build-make" -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build "$tmp/build-make" --parallel 2
"$tmp/build-make/c_check"
"$tmp/build-make/cpp_check"

step "5/7 Python simulator unit tests"
python3 -m unittest -v test_iso8583_lab

step "6/7 Persistent TCP and frame policy"
python3 -m unittest -v test_frame_policy

step "7/7 15-MTI TCP flow smoke"
python3 nibss_smoke_15.py

echo
echo "========== COMPLETE ENVIRONMENT AND SIMULATOR SMOKE TEST PASSED =========="
