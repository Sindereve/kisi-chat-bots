"""Self-check скользящего окна rate limit: пропуск в пределах лимита, блок сверх, сброс по времени."""


def test():
    from kiwi.ratelimit import allow

    # limit=3 за window=10с, время задаём вручную
    assert allow(1, 100.0, 3, 10) is True   # 1-е
    assert allow(1, 100.5, 3, 10) is True   # 2-е
    assert allow(1, 101.0, 3, 10) is True   # 3-е
    assert allow(1, 101.5, 3, 10) is False  # 4-е в окне -> блок (и не занимает слот)

    assert allow(1, 112.0, 3, 10) is True   # старые обращения выпали из окна -> снова можно
    assert allow(2, 101.5, 3, 10) is True   # другой чат независим
    print("ok")


def test_sweep():
    import kiwi.ratelimit as rl

    rl._hits.clear()
    for i in range(rl._SWEEP_AT + 1):        # набиваем чуть больше порога уборки
        rl.allow(i, 100.0, 3, 10)
    assert len(rl._hits) == rl._SWEEP_AT + 1

    rl.allow(999_999, 200.0, 3, 10)          # окно (10с) давно прошло -> остывшие ключи выметаются
    assert 0 not in rl._hits                  # остывший ключ выметен
    assert 999_999 in rl._hits               # свежий остаётся
    assert len(rl._hits) < rl._SWEEP_AT + 1  # уборка сократила словарь
    rl._hits.clear()


if __name__ == "__main__":
    test()
    test_sweep()
