"""SQLite 存储层。

并发安全设计（对应验收项"并发写入不产生数据错误"）：
1. WAL 模式：读写不互相阻塞，写者间由 SQLite 单写者锁串行化；
2. 每次操作使用独立短连接（用完即关），避免多线程共享连接对象；
3. 写操作包裹在事务中（context manager 自动 BEGIN/COMMIT），
   INSERT 失败自动回滚，id 由 AUTOINCREMENT 在事务内生成，天然唯一。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "ledger.db"

_init_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    amount   REAL    NOT NULL CHECK (amount > 0),
    type     TEXT    NOT NULL CHECK (type IN ('收入', '支出')),
    category TEXT    NOT NULL,
    date     TEXT    NOT NULL  -- ISO YYYY-MM-DD，可直接做字符串区间比较
);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);
"""


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = str(db_path) if db_path else str(DEFAULT_DB)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: str | Path | None = None) -> None:
    """建表（幂等）。测试用独立临时库时会显式传入 db_path。"""
    global _initialized
    with _init_lock:
        conn = _connect(db_path)
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def insert_record(amount: float, rtype: str, category: str, rdate: str,
                  db_path: str | Path | None = None) -> int:
    conn = _connect(db_path)
    try:
        with conn:  # 事务：失败自动回滚
            cur = conn.execute(
                "INSERT INTO records(amount, type, category, date) VALUES (?,?,?,?)",
                (amount, rtype, category, rdate),
            )
        return cur.lastrowid
    finally:
        conn.close()


def query_records(rtype: str | None = None, category: str | None = None,
                  start: str | None = None, end: str | None = None,
                  page: int = 1, page_size: int = 20,
                  db_path: str | Path | None = None) -> tuple[int, list[dict]]:
    """筛选 + 分页查询，返回 (total, records)。"""
    where, params = [], []
    if rtype:
        where.append("type = ?")
        params.append(rtype)
    if category:
        where.append("category = ?")
        params.append(category)
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    conn = _connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM records" + clause, params).fetchone()[0]
        rows = conn.execute(
            "SELECT id, amount, type, category, date FROM records"
            + clause + " ORDER BY date, id LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
        return total, [
            {"id": r[0], "amount": r[1], "type": r[2], "category": r[3], "date": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


def summary(start: str | None = None, end: str | None = None,
            db_path: str | Path | None = None) -> dict:
    """区间汇总：收入合计 / 支出合计 / 结余。"""
    where, params = [], []
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT type, COALESCE(SUM(amount), 0) FROM records" + clause + " GROUP BY type",
            params,
        ).fetchall()
    finally:
        conn.close()

    income = sum(v for t, v in rows if t == "收入")
    expense = sum(v for t, v in rows if t == "支出")
    return {"income": income, "expense": expense, "balance": income - expense}
