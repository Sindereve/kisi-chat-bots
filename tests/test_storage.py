"""Self-check БД-хелперов: upsert профиля, смена режима, обрезка истории до HISTORY_LEN."""
import os
import tempfile
from types import SimpleNamespace


def test():
    # DB_FILE читается при импорте kiwi.config — выставляем env ДО импорта пакета.
    os.environ["DB_FILE"] = os.path.join(tempfile.mkdtemp(), "t.db")
    from kiwi import storage
    from kiwi.config import HISTORY_LEN

    u = SimpleNamespace(id=1, username="nick", first_name="Ки", last_name="Ви",
                        language_code="ru", is_premium=True, is_bot=False)
    storage.upsert_user(42, u)
    assert storage.get_mode(42) == "utena"  # default, upsert режим не трогает

    storage.set_mode(42, "user")
    assert storage.get_mode(42) == "user"

    storage.upsert_user(42, u)  # повторный upsert не сбрасывает режим
    assert storage.get_mode(42) == "user"

    n = HISTORY_LEN + 5
    for i in range(n):
        storage.add_turn(42, f"q{i}", f"a{i}")
    hist = storage.get_history(42)
    assert len(hist) == HISTORY_LEN                 # обрезка
    assert hist[-1] == {"role": "assistant", "content": f"a{n-1}"}  # порядок: новое в конце

    from kiwi.bot import describe_user
    assert "@nick" in describe_user(u) and "premium" in describe_user(u)
    print("ok")


if __name__ == "__main__":
    test()
