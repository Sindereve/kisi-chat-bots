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
        mode TEXT NOT NULL DEFAULT 'utena', created_at TEXT, updated_at TEXT,
        summary TEXT, enabled INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL, role TEXT NOT NULL,
        content TEXT NOT NULL, ts TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
    """
)
# ponytail: миграции старых БД — по колонке за раз, без фреймворка
for _col, _decl in (
    ("created_at", "TEXT"),
    ("summary", "TEXT"),
    ("enabled", "INTEGER NOT NULL DEFAULT 0"),
):
    try:
        DB.execute(f"ALTER TABLE users ADD COLUMN {_col} {_decl}")
    except sqlite3.OperationalError:
        pass  # колонка уже есть
DB.commit()

MODE_LABEL = {"utena": "влюблена в Утену", "user": "влюблена в тебя"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date(iso: str | None) -> str | None:
    """ISO-строку -> ДД.ММ.ГГГГ. None/битую строку -> None."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return None


def upsert_user(chat_id: int, u) -> None:
    """Записать/обновить профиль пользователя. Режим не трогаем."""
    DB.execute(
        """
        INSERT INTO users
            (chat_id, user_id, username, first_name, last_name,
             language_code, is_premium, is_bot, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            _now(),  # created_at: в DO UPDATE не трогаем -> дата первого знакомства
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


def get_history(chat_id: int, limit: int = HISTORY_LEN) -> list:
    rows = DB.execute(
        "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def count_user_messages(chat_id: int) -> int:
    return DB.execute(
        "SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='user'", (chat_id,)
    ).fetchone()[0]


def get_summary(chat_id: int) -> str | None:
    """Досье о собеседнике (долгая память) или None, если ещё не собрано."""
    row = DB.execute("SELECT summary FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    return row["summary"] if row else None


def set_summary(chat_id: int, summary: str) -> None:
    DB.execute(
        "INSERT INTO users (chat_id, summary, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET summary=excluded.summary, updated_at=excluded.updated_at",
        (chat_id, summary, _now()),
    )
    DB.commit()


def is_enabled(chat_id: int) -> bool:
    """Разрешён ли бот в этом чате (для групп: включён админом). Личку не спрашиваем — см. хендлеры."""
    row = DB.execute("SELECT enabled FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    return bool(row and row["enabled"])


def set_enabled(chat_id: int, on: bool) -> None:
    DB.execute(
        "INSERT INTO users (chat_id, enabled, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at",
        (chat_id, int(on), _now()),
    )
    DB.commit()


def add_turn(chat_id: int, user_text: str, reply: str) -> None:
    ts = _now()
    DB.executemany(
        "INSERT INTO messages (chat_id, role, content, ts) VALUES (?, ?, ?, ?)",
        [(chat_id, "user", user_text, ts), (chat_id, "assistant", reply, ts)],
    )
    DB.commit()


def clear_history(chat_id: int) -> None:
    """Стереть историю диалога. Профиль и режим не трогаем."""
    DB.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    DB.commit()


def user_info_text(chat_id: int) -> str:
    """Человекочитаемая справка о пользователе из БД + текущий режим."""
    row = DB.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    if row is None:
        return "Хм, я про тебя пока ничего не знаю. Напиши мне хоть что-нибудь!"
    msgs = count_user_messages(chat_id)

    lines = ["*Вот что я про тебя знаю~* 💣", ""]
    name = " ".join(filter(None, [row["first_name"], row["last_name"]]))
    handle = f"@{row['username']}" if row["username"] else ""
    if name or handle:
        lines.append(f"👤 {' '.join(filter(None, [name, handle]))}")
    lines.append(f"🆔 id: {row['user_id']}")
    if row["language_code"]:
        lines.append(f"🌐 язык: {row['language_code']}")
    if row["is_premium"]:
        lines.append("⭐ premium: да")
    if row["is_bot"]:
        lines.append("🤖 бот: да")
    lines.append(f"💬 сообщений: {msgs}")
    since = _date(row["created_at"])
    if since:
        lines.append(f"📅 знакомы с: {since}")
    seen = _date(row["updated_at"])
    if seen:
        lines.append(f"🕒 виделись: {seen}")

    lines += ["", f"сейчас я {MODE_LABEL.get(row['mode'], row['mode'])} 💘"]
    return "\n".join(lines)
