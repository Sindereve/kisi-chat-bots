"""Self-check clip(): короткое не трогает, длинное режет до <=limit по границе + '…'."""
import os
import tempfile

os.environ.setdefault("DB_FILE", os.path.join(tempfile.mkdtemp(), "t.db"))


def test():
    from kiwi.bot import clip

    assert clip("Коротко и колко~") == "Коротко и колко~"          # <=limit — без изменений
    assert clip("  пробелы по краям  ") == "пробелы по краям"       # strip
    assert clip("") == ""                                          # пустой ответ -> пусто (guard)
    assert clip("   ") == ""                                        # только пробелы -> пусто

    # много коротких предложений -> знак препинания близко к концу, режем по нему
    text = "Бум! " * 200
    out = clip(text, 500)
    assert len(out) <= 500 and out.endswith("…")
    assert out[-2] == "!"                                           # рез по концу предложения

    # предложений нет -> режем по слову, не посреди
    words = " ".join("слово" for _ in range(200))
    out2 = clip(words, 500)
    assert len(out2) <= 500 and out2.endswith("…")
    assert out2[:-1].rstrip().endswith("слово")                    # целое слово, не обрывок
    print("ok")


if __name__ == "__main__":
    test()
