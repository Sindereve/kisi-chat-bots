"""Простой rate limit: скользящее окно на in-memory времянках. Ключ — что угодно hashable
(chat_id в личке, (chat_id, user_id) в группе)."""
from collections import defaultdict, deque
from typing import Hashable

# ponytail: in-memory, сбрасывается при рестарте; вынести в БД/Redis только если понадобится persist.
_hits: dict[Hashable, deque] = defaultdict(deque)


_SWEEP_AT = 1000  # ключей в памяти, после которых выкидываем остывшие


def allow(chat_id: Hashable, now: float, limit: int, window: float) -> bool:
    """True, если за последние `window` секунд у ключа было < `limit` обращений. Пишет текущее."""
    if len(_hits) > _SWEEP_AT:  # ponytail: редкая O(n)-уборка, LRU только если чатов станут десятки тысяч
        for k in [k for k, q in _hits.items() if not q or now - q[-1] >= window]:
            del _hits[k]
    q = _hits[chat_id]
    while q and now - q[0] >= window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True
