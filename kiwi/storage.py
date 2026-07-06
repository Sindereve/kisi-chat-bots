"""Хранилище состояния на SQLite: профили пользователей, режим влюблённости и история диалога."""
import sqlite3
from datetime import datetime, timezone

from kiwi.config import DB_FILE, HISTORY_LEN

# ponytail: single global connection; add a pool/lock only if БД станет узким местом.
# Все обращения — из event-loop потока (LLM-вызов в to_thread БД не трогает).
DB = sqlite3.connect(DB_FILE)
DB.row_factory = sqlite3.Row
DB.executescript(
    """
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT,
        first_name TEXT, last_name TEXT, language_code TEXT,
        is_premium INTEGER, is_bot INTEGER,
        mode TEXT NOT NULL DEFAULT 'utena', updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL, role TEXT NOT NULL,
        content TEXT NOT NULL, ts TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
    """
)
DB.commit()

MODE_LABEL = {"utena": "влюблена в Утену", "user": "влюблена в тебя"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_user(chat_id: int, u) -> None:
    """Записать/обновить профиль пользователя. Режим не трогаем."""
    DB.execute(
        """
        INSERT INTO users
            (chat_id, user_id, username, first_name, last_name,
             language_code, is_premium, is_bot, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            user_id=excluded.user_id, username=excluded.username,
            first_name=excluded.first_name, last_name=excluded.last_name,
            language_code=excluded.language_code, is_premium=excluded.is_premium,
            is_bot=excluded.is_bot, updated_at=excluded.updated_at
        """,
        (
            chat_id,
            getattr(u, "id", None),
            getattr(u, "username", None),
            getattr(u, "first_name", None),
            getattr(u, "last_name", None),
            getattr(u, "language_code", None),
            int(bool(getattr(u, "is_premium", None))),
            int(bool(getattr(u, "is_bot", None))),
            _now(),
        ),
    )
    DB.commit()


def get_mode(chat_id: int) -> str:
    row = DB.execute("SELECT mode FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    return row["mode"] if row else "utena"


def set_mode(chat_id: int, mode: str) -> None:
    DB.execute(
        "INSERT INTO users (chat_id, mode, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at",
        (chat_id, mode, _now()),
    )
    DB.commit()


def get_history(chat_id: int) -> list:
    rows = DB.execute(
        "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
        (chat_id, HISTORY_LEN),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def add_turn(chat_id: int, user_text: str, reply: str) -> None:
    ts = _now()
    DB.executemany(
        "INSERT INTO messages (chat_id, role, content, ts) VALUES (?, ?, ?, ?)",
        [(chat_id, "user", user_text, ts), (chat_id, "assistant", reply, ts)],
    )
    DB.commit()


def user_info_text(chat_id: int) -> str:
    """Человекочитаемая справка о пользователе из БД + текущий режим."""
    row = DB.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    if row is None:
        return "Хм, я про тебя пока ничего не знаю. Напиши мне хоть что-нибудь!"
    lines = [f"*Вот что я про тебя знаю~*", f"id: {row['user_id']}"]
    if row["username"]:
        lines.append(f"username: @{row['username']}")
    name = " ".join(filter(None, [row["first_name"], row["last_name"]]))
    if name:
        lines.append(f"имя: {name}")
    if row["language_code"]:
        lines.append(f"язык: {row['language_code']}")
    if row["is_premium"]:
        lines.append("premium: да")
    lines.append(f"сейчас я {MODE_LABEL.get(row['mode'], row['mode'])} 💘")
    return "\n".join(lines)
