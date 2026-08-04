"""SQLite storage for price history and last-known decisions."""
import sqlite3
from contextlib import contextmanager
import pandas as pd

DB_PATH = "dse_bot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                close REAL,
                high REAL,
                low REAL,
                volume INTEGER,
                PRIMARY KEY (symbol, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state (
                symbol TEXT PRIMARY KEY,
                last_decision TEXT,
                last_score REAL,
                last_updated TEXT
            )
        """)


def upsert_price(symbol, date, close, high, low, volume):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO price_history (symbol, date, close, high, low, volume)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
                close=excluded.close, high=excluded.high,
                low=excluded.low, volume=excluded.volume
        """, (symbol, date, close, high, low, volume))


def get_price_series(symbol, limit=260):
    """Returns a DataFrame sorted ascending by date, most recent `limit` rows."""
    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT date, close, high, low, volume FROM price_history
            WHERE symbol = ? ORDER BY date DESC LIMIT ?
        """, conn, params=(symbol, limit))
    return df.iloc[::-1].reset_index(drop=True)  # ascending order


def count_price_rows(symbol):
    with get_conn() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM price_history WHERE symbol = ?", (symbol,))
        return cur.fetchone()[0]


def get_last_decision(symbol):
    with get_conn() as conn:
        cur = conn.execute("SELECT last_decision, last_score FROM state WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        return {"decision": row[0], "score": row[1]} if row else None


def set_last_decision(symbol, decision, score, updated_at):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO state (symbol, last_decision, last_score, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                last_decision=excluded.last_decision,
                last_score=excluded.last_score,
                last_updated=excluded.last_updated
        """, (symbol, decision, score, updated_at))
