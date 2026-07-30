"""Self-check БД-хелперов: upsert профиля, смена режима, обрезка истории до HISTORY_LEN."""
import os
import tempfile
from types import SimpleNamespace


def test():
    # Прямой запуск (python tests/test_storage.py): conftest не грузится, temp-БД ставим тут.
    # Под pytest DB_FILE уже выставлен conftest'ом до импорта kiwi.config — эта строка тогда без эффекта.
    os.environ.setdefault("DB_FILE", os.path.join(tempfile.mkdtemp(), "t.db"))
    from kiwi import storage
    from kiwi.config import HISTORY_LEN

    u = SimpleNamespace(id=1, username="nick", first_name="Ки", last_name="Ви",
                        language_code="ru", is_premium=True, is_bot=False)
    storage.upsert_user(42, u)
    assert storage.get_mode(42) == "utena"  # default, upsert режим не трогает

    storage.set_mode(42, "user")
    assert storage.get_mode(42) == "user"

    created = storage.DB.execute("SELECT created_at FROM users WHERE chat_id=42").fetchone()[0]
    assert created is not None                      # дата первого знакомства проставлена

    storage.upsert_user(42, u)  # повторный upsert не сбрасывает режим
    assert storage.get_mode(42) == "user"
    again = storage.DB.execute("SELECT created_at FROM users WHERE chat_id=42").fetchone()[0]
    assert again == created                         # created_at устойчив к повторному upsert

    n = HISTORY_LEN + 5
    for i in range(n):
        storage.add_turn(42, f"q{i}", f"a{i}")
    hist = storage.get_history(42)
    assert len(hist) == HISTORY_LEN                 # обрезка
    assert hist[-1] == {"role": "assistant", "content": f"a{n-1}"}  # порядок: новое в конце

    info = storage.user_info_text(42)
    assert f"сообщений: {n}" in info                # счётчик считает user-сообщения
    assert "@nick" in info and "знакомы с:" in info
    assert storage.count_user_messages(42) == n     # тот же счётчик, вынесен в функцию

    # досье (долгая память): пусто -> записали -> читаем
    assert storage.get_summary(42) is None
    storage.set_summary(42, "любит взрывы, зовёт по имени")
    assert storage.get_summary(42) == "любит взрывы, зовёт по имени"

    # групповой флаг: по умолчанию выкл, включаем/выключаем
    assert storage.is_enabled(-100500) is False
    storage.set_enabled(-100500, True)
    assert storage.is_enabled(-100500) is True
    storage.set_enabled(-100500, False)
    assert storage.is_enabled(-100500) is False

    storage.clear_history(42)                       # /reset стирает историю,
    assert storage.get_history(42) == []            # но профиль и режим целы
    assert storage.get_mode(42) == "user"
    assert storage.DB.execute("SELECT 1 FROM users WHERE chat_id=42").fetchone() is not None

    from kiwi.bot import describe_user
    # для логов: id и публичный @username — да; имя/premium (PII) — нет
    assert "id=1" in describe_user(u) and "@nick" in describe_user(u)
    assert "Ки" not in describe_user(u) and "premium" not in describe_user(u)
    print("ok")


if __name__ == "__main__":
    test()
