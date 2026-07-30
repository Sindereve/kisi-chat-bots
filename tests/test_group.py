"""Гейтинг в группах: обращение к боту распознаётся по @mention или reply на его сообщение."""
from types import SimpleNamespace


def test():
    from kiwi.bot import addressed_to_bot, is_group

    ctx = SimpleNamespace(bot=SimpleNamespace(id=777, username="kiwi_bot"))

    def upd(text=None, caption=None, reply_from_id=None):
        reply = SimpleNamespace(from_user=SimpleNamespace(id=reply_from_id)) if reply_from_id else None
        return SimpleNamespace(message=SimpleNamespace(text=text, caption=caption, reply_to_message=reply))

    assert addressed_to_bot(upd(text="эй @kiwi_bot привет"), ctx)   # упоминание
    assert addressed_to_bot(upd(text="@KIWI_BOT ало"), ctx)         # регистр не важен
    assert addressed_to_bot(upd(caption="@kiwi_bot глянь"), ctx)    # упоминание в подписи к фото
    assert not addressed_to_bot(upd(text="просто болтаю"), ctx)     # мимо
    assert addressed_to_bot(upd(reply_from_id=777), ctx)            # reply на бота
    assert not addressed_to_bot(upd(reply_from_id=1), ctx)          # reply на другого
    assert not addressed_to_bot(upd(text=None), ctx)               # голос без reply — не к боту

    assert is_group(SimpleNamespace(type="supergroup"))
    assert is_group(SimpleNamespace(type="group"))
    assert not is_group(SimpleNamespace(type="private"))
    print("ok")


def test_speaker():
    from kiwi.bot import speaker

    assert speaker(SimpleNamespace(first_name="Кэн", username="ken")) == "Кэн"   # имя в приоритете
    assert speaker(SimpleNamespace(first_name=None, username="ken")) == "ken"    # fallback на username
    assert speaker(SimpleNamespace(first_name=None, username=None)) == "кто-то"  # совсем аноним
    assert speaker(None) == "кто-то"


if __name__ == "__main__":
    test()
    test_speaker()
