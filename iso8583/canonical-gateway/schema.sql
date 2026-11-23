CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    stan TEXT NOT NULL,
    rrn TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    cardholder_ref TEXT,
    merchant_ref TEXT,
    operation TEXT NOT NULL,
    amount_minor INTEGER,
    currency TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    outcome_code TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_transactions_correlation
    ON transactions(stan, rrn, transaction_date);

PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS authorized_merchants (
    merchant_ref TEXT PRIMARY KEY NOT NULL
);
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000001');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000002');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000003');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000004');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000005');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000006');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000007');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000008');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000009');
INSERT OR IGNORE INTO authorized_merchants(merchant_ref) VALUES('MERCHANT0000010');
