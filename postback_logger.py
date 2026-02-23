"""
Логирование попыток отправки постбеков в SQLite.
Файл БД: postbacks.db (в каталоге проекта на сервере).
"""
import sqlite3
from datetime import datetime

from config import POSTBACKS_DB_PATH


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(POSTBACKS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицу логов при первом запуске."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS postback_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                success INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                click_id TEXT,
                offer_id TEXT,
                pid TEXT,
                goal TEXT,
                status INTEGER,
                error_message TEXT
            )
        """)
        conn.commit()


def log_postback(
    *,
    success: bool,
    user_id: int,
    username: str | None,
    first_name: str | None,
    click_id: str | None = None,
    offer_id: str | None = None,
    pid: str | None = None,
    goal: str | None = None,
    status: int | None = None,
    error_message: str | None = None,
) -> None:
    """
    Записывает попытку отправки постбека.
    """
    init_db()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO postback_logs (
                created_at, success, user_id, username, first_name,
                click_id, offer_id, pid, goal, status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat() + "Z",
                1 if success else 0,
                user_id,
                username or None,
                first_name or None,
                click_id or None,
                offer_id or None,
                pid or None,
                goal or None,
                status,
                error_message or None,
            ),
        )
        conn.commit()
