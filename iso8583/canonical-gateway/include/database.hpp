#pragma once

#include <sqlite3.h>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>

namespace payment_gateway {

class DatabaseError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class Statement;
class Transaction;

// A connection belongs to one gateway worker. Do not share it across threads.
// Implement the TODOs in database.cpp; never interpolate untrusted values into SQL.
class Database {
public:
    explicit Database(const std::string& filename);
    ~Database() noexcept;
    Database(const Database&) = delete;
    Database& operator=(const Database&) = delete;
    Database(Database&&) = delete;
    Database& operator=(Database&&) = delete;

    Statement prepare(const std::string& sql);
    void execute_trusted(const std::string& sql); // Schema/BEGIN/COMMIT only
    Transaction begin_transaction();
    std::int64_t last_insert_id() const;
    int changes() const;

private:
    friend class Statement;
    friend class Transaction;
    sqlite3* db_ = nullptr;
};

// Owns exactly one prepared statement. Statement must not outlive Database.
class Statement {
public:
    ~Statement() noexcept;
    Statement(const Statement&) = delete;
    Statement& operator=(const Statement&) = delete;
    Statement(Statement&& other) noexcept;
    Statement& operator=(Statement&& other) noexcept;

    void bind(int index, std::int64_t value);
    void bind(int index, std::string_view value);
    void bind_null(int index);
    // Optional: bind by named placeholder (e.g. ":stan") using
    // sqlite3_bind_parameter_index(); reject unknown names.
    void bind(std::string_view name, std::int64_t value);
    void bind(std::string_view name, std::string_view value);

    bool step(); // true = SQLITE_ROW; false = SQLITE_DONE; otherwise throw
    std::int64_t column_int64(int column) const;
    std::string column_text(int column) const;
    bool column_is_null(int column) const;
    void reset();

private:
    friend class Database;
    explicit Statement(sqlite3_stmt* statement) noexcept;
    sqlite3_stmt* statement_ = nullptr;
};

// Rolls back automatically unless committed. Transaction must not outlive Database.
class Transaction {
public:
    ~Transaction() noexcept;
    Transaction(const Transaction&) = delete;
    Transaction& operator=(const Transaction&) = delete;
    Transaction(Transaction&& other) noexcept;
    Transaction& operator=(Transaction&& other) noexcept;

    void commit();
    void rollback();

private:
    friend class Database;
    explicit Transaction(Database& database);
    Database* database_ = nullptr;
    bool active_ = false;
};

} // namespace payment_gateway
