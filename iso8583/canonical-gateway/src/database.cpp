#include "database.hpp"
#include <climits>
#include <stdexcept>
#include <string>
#include <utility>

namespace payment_gateway {
namespace {
void sqlite_check(sqlite3* db, int status, const char* operation) {
    if (status != SQLITE_OK) throw DatabaseError(std::string(operation) + ": " +
        (db ? sqlite3_errmsg(db) : sqlite3_errstr(status)));
}
void stmt_check(sqlite3_stmt* stmt, int status, const char* op) {
    if (status != SQLITE_OK) sqlite_check(sqlite3_db_handle(stmt), status, op);
}
}
Database::Database(const std::string& filename) {
    int status=sqlite3_open_v2(filename.c_str(),&db_,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE,nullptr);
    if(status != SQLITE_OK) {
        const std::string err=db_ ? sqlite3_errmsg(db_) : sqlite3_errstr(status);
        if(db_) sqlite3_close(db_);
        db_=nullptr;
        throw DatabaseError("open database: "+err);
    }
    sqlite_check(db_,sqlite3_busy_timeout(db_,1000),"busy timeout");
}
Database::~Database() noexcept {if(db_) (void)sqlite3_close(db_);}
Statement Database::prepare(const std::string& sql) {
    sqlite3_stmt* statement=nullptr;
    const char* tail=nullptr;
    sqlite_check(db_,sqlite3_prepare_v2(db_,sql.c_str(),-1,&statement,&tail),"prepare");
    for(const char* p=tail;p && *p;++p) {
        if(*p!=' ' && *p!='\n' && *p!='\r' && *p!='\t') {
            sqlite3_finalize(statement);
            throw DatabaseError("SQL contains additional statement");
        }
    }
    if(!statement) throw DatabaseError("empty SQL statement");
    return Statement(statement);
}
void Database::execute_trusted(const std::string& sql) {
    char* error=nullptr;
    const int status=sqlite3_exec(db_,sql.c_str(),nullptr,nullptr,&error);
    if(status!=SQLITE_OK) {
        const std::string msg=error ? error : sqlite3_errmsg(db_);
        sqlite3_free(error);
        throw DatabaseError("SQL execution: "+msg);
    }
}
Transaction Database::begin_transaction() {
    execute_trusted("BEGIN IMMEDIATE");
    return Transaction(*this);
}
std::int64_t Database::last_insert_id() const {return sqlite3_last_insert_rowid(db_);}
int Database::changes() const {return sqlite3_changes(db_);}
Statement::Statement(sqlite3_stmt* stmt) noexcept:statement_(stmt){}
Statement::~Statement() noexcept {if(statement_) (void)sqlite3_finalize(statement_);}
Statement::Statement(Statement&& other) noexcept:statement_(std::exchange(other.statement_,nullptr)){}
Statement& Statement::operator=(Statement&& other) noexcept {
    if(this!=&other){if(statement_)sqlite3_finalize(statement_);statement_=std::exchange(other.statement_,nullptr);}
    return *this;
}
void Statement::bind(int index,std::int64_t value) {
    stmt_check(statement_,sqlite3_bind_int64(statement_,index,value),"bind integer");
}
void Statement::bind(int index,std::string_view value) {
    if(value.size()>INT_MAX) throw DatabaseError("SQL string too long");
    stmt_check(statement_,sqlite3_bind_text(statement_,index,value.data(),static_cast<int>(value.size()),SQLITE_TRANSIENT),"bind text");
}
void Statement::bind_null(int index) {stmt_check(statement_,sqlite3_bind_null(statement_,index),"bind NULL");}
void Statement::bind(std::string_view name,std::int64_t value) {
    const int index=sqlite3_bind_parameter_index(statement_,std::string(name).c_str());
    if(!index)throw DatabaseError("unknown SQL parameter");
    bind(index,value);
}
void Statement::bind(std::string_view name,std::string_view value) {
    const int index=sqlite3_bind_parameter_index(statement_,std::string(name).c_str());
    if(!index)throw DatabaseError("unknown SQL parameter");
    bind(index,value);
}
bool Statement::step() {
    const int rc=sqlite3_step(statement_);
    if(rc==SQLITE_ROW)return true;
    if(rc==SQLITE_DONE)return false;
    throw DatabaseError(std::string("step: ")+sqlite3_errmsg(sqlite3_db_handle(statement_)));
}
std::int64_t Statement::column_int64(int column) const {return sqlite3_column_int64(statement_,column);}
std::string Statement::column_text(int column) const {
    const auto* bytes=sqlite3_column_text(statement_,column);
    if(!bytes)return {};
    const auto length=sqlite3_column_bytes(statement_,column);
    return std::string(reinterpret_cast<const char*>(bytes),static_cast<std::size_t>(length));
}
bool Statement::column_is_null(int column) const {return sqlite3_column_type(statement_,column)==SQLITE_NULL;}
void Statement::reset(){
    const int status=sqlite3_reset(statement_);
    stmt_check(statement_,status,"reset");
    stmt_check(statement_,sqlite3_clear_bindings(statement_),"clear bindings");
}
Transaction::Transaction(Database& db):database_(&db),active_(true){}
Transaction::~Transaction() noexcept {
    if(active_ && database_) {
        try {database_->execute_trusted("ROLLBACK");} catch(...){ }
    }
}
Transaction::Transaction(Transaction&& other) noexcept:database_(std::exchange(other.database_,nullptr)),active_(std::exchange(other.active_,false)){}
Transaction& Transaction::operator=(Transaction&& other) noexcept {
    if(this!=&other){
        if(active_ && database_){try{database_->execute_trusted("ROLLBACK");}catch(...){}}
        database_=std::exchange(other.database_,nullptr);
        active_=std::exchange(other.active_,false);
    }
    return *this;
}
void Transaction::commit() {
    if(!active_ || !database_)throw DatabaseError("transaction not active");
    database_->execute_trusted("COMMIT");
    active_=false;
}
void Transaction::rollback() {
    if(!active_ || !database_)throw DatabaseError("transaction not active");
    database_->execute_trusted("ROLLBACK");
    active_=false;
}
} // namespace payment_gateway
