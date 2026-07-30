"""Проверка build_messages без Telegram: правильный system-prompt по режиму и обрезка истории."""
from datetime import date

from kiwi.config import HISTORY_LEN
from kiwi.persona import LOVE_USER, LOVE_UTENA, birthday_note, build_messages, summary_messages


def test_birthday():
    assert "СЕГОДНЯ" in birthday_note(date(2026, 7, 6))
    assert "через 3 дн" in birthday_note(date(2026, 7, 3))
    assert "2 дн. назад" in birthday_note(date(2026, 7, 8))
    assert birthday_note(date(2026, 7, 1)) == ""  # за 5 дней — молчок
    assert birthday_note(date(2026, 1, 1)) == ""


def test():
    hist = [{"role": "user", "content": str(i)} for i in range(HISTORY_LEN + 10)]

    m_user = build_messages("user", hist, "привет")
    assert LOVE_USER in m_user[0]["content"] and m_user[0]["role"] == "system"

    m_utena = build_messages("utena", hist, "привет")
    assert LOVE_UTENA in m_utena[0]["content"]

    # system + не более HISTORY_LEN из истории + текущее сообщение
    assert len(m_user) <= 1 + HISTORY_LEN + 1
    assert m_user[-1] == {"role": "user", "content": "привет"}

    # досье подмешивается в system-промпт, когда есть
    assert "любит взрывы" in build_messages("user", hist, "привет", "любит взрывы")[0]["content"]
    assert "любит взрывы" not in build_messages("user", hist, "привет")[0]["content"]

    # групповая подсказка про подписи участников — только при group=True
    assert "[Имя]" in build_messages("user", hist, "привет", group=True)[0]["content"]
    assert "[Имя]" not in build_messages("user", hist, "привет")[0]["content"]

    # без картинки последний ход — строка; с картинкой — мультимодальный список для vision
    assert build_messages("user", hist, "привет")[-1]["content"] == "привет"
    mm = build_messages("user", hist, "гляди", image_url="data:image/jpeg;base64,AAA")[-1]["content"]
    assert {"type": "text", "text": "гляди"} in mm
    assert mm[-1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    print("ok")


def test_summary_messages():
    sm = summary_messages("старое досье", [{"role": "user", "content": "хай"}])
    assert sm[0]["role"] == "system"
    assert "старое досье" in sm[1]["content"] and "хай" in sm[1]["content"]
    # без старого досье — только свежая история
    assert "Старое досье" not in summary_messages(None, [{"role": "user", "content": "хай"}])[1]["content"]


if __name__ == "__main__":
    test_birthday()
    test()
    test_summary_messages()
