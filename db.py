"""SQLite-хранилище PENJOY-бота.

База создаётся программно при старте в /app/data/penjoy.db (требование
платформы bothost.ru: папка data переживает обновления кода). На бесплатном
тарифе данные стираются при рестарте контейнера — поэтому каждый заказ
дублируется уведомлением админу в Telegram (см. bot.py: notify_admin).
"""
import sqlite3
import time
from contextlib import contextmanager

import config as C


@contextmanager
def _db():
    conn = sqlite3.connect(str(C.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                source      TEXT DEFAULT 'unknown',
                segment     TEXT DEFAULT '',
                email       TEXT DEFAULT '',
                purchase    INTEGER DEFAULT 0,
                unsubscribed INTEGER DEFAULT 0,
                created_at  INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                issue     TEXT,
                qty       INTEGER,
                delivery  TEXT,
                name      TEXT,
                address   TEXT,
                phone     TEXT,
                total     INTEGER,
                status    TEXT DEFAULT 'new',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drip (
                user_id  INTEGER NOT NULL,
                step     INTEGER NOT NULL,
                sent_at  INTEGER NOT NULL,
                PRIMARY KEY (user_id, step)
            );
            CREATE TABLE IF NOT EXISTS stock (
                issue TEXT PRIMARY KEY,
                qty   INTEGER NOT NULL
            );
            """
        )
        # стартовые остатки — один раз
        if conn.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 0:
            for issue, qty in C.STOCK_DEFAULT.items():
                conn.execute(
                    "INSERT INTO stock (issue, qty) VALUES (?, ?)", (issue, qty)
                )


# --- пользователи -------------------------------------------------------

def upsert_user(user_id: int, username: str, first_name: str, source: str) -> None:
    with _db() as conn:
        conn.execute(
            """INSERT INTO users (user_id, username, first_name, source, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name""",
            (user_id, username, first_name, source, int(time.time())),
        )


def get_user(user_id: int):
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def set_user_field(user_id: int, field: str, value) -> None:
    if field not in ("segment", "email", "purchase", "unsubscribed"):
        raise ValueError(field)
    with _db() as conn:
        conn.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))


# --- заказы -------------------------------------------------------------

def add_order(user_id: int, issue: str, qty: int, delivery: str,
              name: str, address: str, phone: str, total: int) -> int:
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO orders
               (user_id, issue, qty, delivery, name, address, phone, total, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, issue, qty, delivery, name, address, phone, total, int(time.time())),
        )
        return cur.lastrowid


def get_order(order_id: int):
    with _db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(row) if row else None


def set_order_status(order_id: int, status: str) -> None:
    with _db() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))


def last_order(user_id: int):
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


# --- дожим --------------------------------------------------------------

def drip_due(now: int, step: int):
    """Кому пора отправить касание «день step» (ещё не отправлено, не купил)."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT u.* FROM users u
               WHERE u.purchase = 0 AND u.unsubscribed = 0
                 AND ? - u.created_at >= ?
                 AND NOT EXISTS (SELECT 1 FROM drip d
                                 WHERE d.user_id = u.user_id AND d.step = ?)""",
            (now, step * 86400, step),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_drip(user_id: int, step: int, now: int) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO drip (user_id, step, sent_at) VALUES (?, ?, ?)",
            (user_id, step, now),
        )


# --- остатки ------------------------------------------------------------

def get_stock() -> dict:
    with _db() as conn:
        rows = conn.execute("SELECT issue, qty FROM stock").fetchall()
        return {r["issue"]: r["qty"] for r in rows}


def set_stock(issue: str, qty: int) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO stock (issue, qty) VALUES (?, ?) "
            "ON CONFLICT(issue) DO UPDATE SET qty = excluded.qty",
            (issue, qty),
        )


# --- статистика / выгрузка ----------------------------------------------

def stats() -> dict:
    with _db() as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        leads = conn.execute(
            "SELECT COUNT(*) FROM users WHERE segment != ''"
        ).fetchone()[0]
        orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        paid = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE status IN ('paid', 'paid_unconfirmed')"
        ).fetchone()[0]
        revenue = conn.execute(
            "SELECT COALESCE(SUM(total), 0) FROM orders WHERE status IN ('paid', 'paid_unconfirmed')"
        ).fetchone()[0]
        return {"users": users, "leads": leads, "orders": orders,
                "paid": paid, "revenue": revenue}


def export_rows():
    """Строки для CSV: пользователи + их заказы."""
    with _db() as conn:
        users = conn.execute(
            "SELECT * FROM users ORDER BY created_at"
        ).fetchall()
        orders = conn.execute(
            "SELECT * FROM orders ORDER BY created_at"
        ).fetchall()
        return [dict(u) for u in users], [dict(o) for o in orders]
