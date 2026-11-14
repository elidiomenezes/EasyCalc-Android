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
  std::cout << "Boost.Asio, SQLite3, OpenSSL and C++ verification PASSED\n";
  return 0;
}
