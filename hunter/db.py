"""SQLite 连接与建表。

设计要点：
- WAL + busy_timeout，让「采集写」和「网页读」不互相卡死；
- 所有价格存 float，同时保留原文，避免「¥1.2万」这类展示丢信息；
- 商品按 item_id 全局去重：同一件商品被多个关键词命中，只抓一次详情、只存一份。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from hunter.config import PATHS

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    profile_dir TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'unknown',   -- ok | expired | risk | unknown
    last_ok_at  TEXT,
    last_error  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watches (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    keyword       TEXT NOT NULL,
    account_id    INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    sort          TEXT NOT NULL DEFAULT 'newest',
    pages         INTEGER NOT NULL DEFAULT 2,
    page_size     INTEGER NOT NULL DEFAULT 30,
    personal_only INTEGER NOT NULL DEFAULT 1,
    free_shipping INTEGER NOT NULL DEFAULT 1,
    min_price     REAL,
    max_price     REAL,
    min_score     INTEGER NOT NULL DEFAULT 60,
    interval_sec  INTEGER NOT NULL DEFAULT 300,
    enabled       INTEGER NOT NULL DEFAULT 1,
    use_llm       INTEGER NOT NULL DEFAULT 1,
    notify        INTEGER NOT NULL DEFAULT 1,
    note          TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    last_run_at   TEXT,
    next_run_at   TEXT
);

CREATE TABLE IF NOT EXISTS items (
    item_id        TEXT PRIMARY KEY,
    title          TEXT NOT NULL DEFAULT '',
    price          REAL,
    price_display  TEXT DEFAULT '',
    original_price REAL,
    area           TEXT DEFAULT '',
    seller_id      TEXT DEFAULT '',
    seller_nick    TEXT DEFAULT '',
    publish_at     TEXT,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    pics_json      TEXT DEFAULT '[]',
    tags_json      TEXT DEFAULT '[]',
    desc           TEXT DEFAULT '',
    labels_json    TEXT DEFAULT '{}',
    spec_key       TEXT DEFAULT '',
    want_cnt       INTEGER,
    browse_cnt     INTEGER,
    collect_cnt    INTEGER,
    transport_fee  REAL,
    status         TEXT DEFAULT '',
    detail_json    TEXT,
    detail_at      TEXT,
    link           TEXT DEFAULT '',
    feedback       TEXT,           -- good | bad | deal | null
    feedback_note  TEXT,
    feedback_at    TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id  TEXT NOT NULL,
    watch_id INTEGER,
    price    REAL NOT NULL,
    want_cnt INTEGER,
    seen_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_item ON snapshots(item_id, seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_snap_watch ON snapshots(watch_id, seen_at DESC);

CREATE TABLE IF NOT EXISTS scores (
    item_id        TEXT NOT NULL,
    watch_id       INTEGER NOT NULL,
    score          INTEGER NOT NULL,
    verdict        TEXT NOT NULL,
    market_median  REAL,
    market_p25     REAL,
    market_count   INTEGER DEFAULT 0,
    discount_pct   REAL,
    spec_key       TEXT DEFAULT '',
    breakdown_json TEXT DEFAULT '{}',
    flags_json     TEXT DEFAULT '[]',
    reasons_json   TEXT DEFAULT '[]',
    llm_json       TEXT,
    scored_at      TEXT NOT NULL,
    PRIMARY KEY (item_id, watch_id)
);
CREATE INDEX IF NOT EXISTS idx_scores_watch ON scores(watch_id, score DESC);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id    TEXT PRIMARY KEY,
    nick         TEXT DEFAULT '',
    city         TEXT DEFAULT '',
    reg_days     INTEGER,
    item_count   INTEGER,
    sold_count   INTEGER,
    credit_level INTEGER,
    credit_text  TEXT DEFAULT '',
    zhima        INTEGER DEFAULT 0,
    real_name    INTEGER DEFAULT 0,
    reply_ratio  REAL,
    good_ratio   REAL,
    rate_total   INTEGER,
    tags_json    TEXT DEFAULT '[]',
    raw_json     TEXT,
    fetched_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      TEXT NOT NULL,
    watch_id     INTEGER,
    price        REAL,
    score        INTEGER,
    channel      TEXT DEFAULT '',
    ok           INTEGER DEFAULT 0,
    payload_json TEXT DEFAULT '{}',
    created_at   TEXT NOT NULL,
    UNIQUE(item_id, watch_id, price)
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id    INTEGER,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    found       INTEGER DEFAULT 0,
    new_items   INTEGER DEFAULT 0,
    scored      INTEGER DEFAULT 0,
    alerted     INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'running',   -- running | ok | error | risk | login
    error       TEXT,
    stats_json  TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_runs_watch ON runs(watch_id, started_at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "notify_channels": "",          # 逗号分隔：ntfy,bark,telegram,webhook,wecom
    "ntfy_url": "",
    "bark_url": "",
    "telegram_token": "",
    "telegram_chat": "",
    "webhook_url": "",
    "wecom_url": "",
    "quiet_hours": "23:30-08:00",   # 静默时段，只收不发（日报除外）
    "llm_enabled": "1",
    "llm_base_url": "https://api.deepseek.com",
    "llm_model": "deepseek-flash",
    "llm_api_key": "",
    "llm_top_n": "8",               # 每轮最多让 LLM 复核前 N 个
    "digest_enabled": "1",
    "min_samples": "4",             # 市场统计最少样本数
}


def connect(path: str | None = None) -> sqlite3.Connection:
    PATHS.ensure()
    conn = sqlite3.connect(path or str(PATHS.db), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """v0.1 早期版本的告警表按分数去重，会导致每次分数微调都重复推送。"""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(alerts)")}
    if columns and "price" not in columns:
        conn.executescript(
            """
            ALTER TABLE alerts RENAME TO alerts_legacy;
            CREATE TABLE alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id      TEXT NOT NULL,
                watch_id     INTEGER,
                price        REAL,
                score        INTEGER,
                channel      TEXT DEFAULT '',
                ok           INTEGER DEFAULT 0,
                payload_json TEXT DEFAULT '{}',
                created_at   TEXT NOT NULL,
                UNIQUE(item_id, watch_id, price)
            );
            INSERT INTO alerts(item_id, watch_id, score, channel, ok, payload_json, created_at)
                SELECT item_id, watch_id, score, channel, ok, payload_json, created_at
                FROM alerts_legacy;
            DROP TABLE alerts_legacy;
            """
        )


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )
