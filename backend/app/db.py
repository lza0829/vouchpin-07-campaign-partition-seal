from __future__ import annotations
import sqlite3
from app.config import DB_PATH

TABLES = '''
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  face_value REAL NOT NULL,
  min_spend REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupon_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS redeem_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_code TEXT NOT NULL UNIQUE,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  batch_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS redeem_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_day TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'day',
  campaign_code TEXT,
  status TEXT NOT NULL,
  fact_count INTEGER NOT NULL DEFAULT 0,
  total_amount REAL NOT NULL DEFAULT 0,
  sealed_at TEXT,
  note TEXT NOT NULL DEFAULT ''
);
'''

INDEXES = '''
CREATE INDEX IF NOT EXISTS idx_facts_day_campaign_status
  ON redeem_facts(business_day, campaign_code, status);
CREATE INDEX IF NOT EXISTS idx_batches_day_scope_campaign
  ON redeem_batches(business_day, scope, campaign_code);
CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_batch_per_day
  ON redeem_batches(business_day, campaign_code) WHERE scope='campaign';
CREATE UNIQUE INDEX IF NOT EXISTS uq_day_batch_per_day
  ON redeem_batches(business_day) WHERE scope='day';
'''


def connect(immediate: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Upgrade snapshots created before seal granularity existed."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(redeem_batches)").fetchall()}
    if "scope" not in cols:
        conn.execute("ALTER TABLE redeem_batches ADD COLUMN scope TEXT NOT NULL DEFAULT 'day'")
    if "campaign_code" not in cols:
        conn.execute("ALTER TABLE redeem_batches ADD COLUMN campaign_code TEXT")


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(TABLES)
        _migrate(conn)
        conn.executescript(INDEXES)
        conn.commit()
    finally:
        conn.close()
