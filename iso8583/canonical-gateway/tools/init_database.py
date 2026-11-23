#!/usr/bin/env python3
"""Create or verify an empty Day 4 SQLite database using the supplied schema.

Uses Python's standard-library sqlite3 module solely for provisioning/testing;
students implement the C++17 SQLite C API wrapper themselves.
"""
import argparse
from pathlib import Path
import sqlite3
import sys

SCHEMA = Path(__file__).resolve().parents[1] / 'schema.sql'


def initialize(path: Path, reset: bool = False):
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if reset and path.exists():
        for suffix in ('', '-wal', '-shm'):
            candidate = Path(str(path) + suffix)
            if candidate.exists():
                candidate.unlink()
    with sqlite3.connect(str(path), timeout=5) as db:
        db.execute('PRAGMA busy_timeout=5000')
        mode = db.execute('PRAGMA journal_mode=WAL').fetchone()[0]
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript(SCHEMA.read_text(encoding='utf-8'))
        expected = {'id', 'stan', 'rrn', 'transaction_date', 'cardholder_ref',
                    'merchant_ref', 'operation', 'amount_minor', 'currency',
                    'status', 'outcome_code', 'created_at', 'completed_at'}
        actual = {row[1] for row in db.execute('PRAGMA table_info(transactions)')}
        if not expected <= actual:
            raise RuntimeError('Schema mismatch; missing: ' + repr(sorted(expected - actual)))
        count = db.execute('SELECT count(*) FROM transactions').fetchone()[0]
        db.commit()
    print(f'DATABASE_READY path={path} wal={mode} rows={count}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True, type=Path, help='Destination SQLite file')
    p.add_argument('--reset', action='store_true', help='Destroy/recreate a test DB. DESTRUCTIVE.')
    args = p.parse_args()
    try:
        initialize(args.db, args.reset)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f'DATABASE_INIT_FAILED: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
