"""신규 기능(공항 변환, 유연한 날짜 포맷, watch 저장소) 단위 테스트.

텔레그램 라이브러리 없이 코어 로직만 검증합니다.
실행: python tests/test_features.py  또는  python -m pytest
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightchecker.airports import resolve_airport  # noqa: E402
from flightchecker.formatter import format_flexible  # noqa: E402
from flightchecker.watchstore import Watch, WatchStore  # noqa: E402


# ---- 공항 코드 변환 ----------------------------------------------------

def test_resolve_korean_names():
    assert resolve_airport("인천") == "ICN"
    assert resolve_airport("후쿠오카") == "FUK"
    assert resolve_airport(" 도쿄 ") == "NRT"


def test_resolve_passthrough_code():
    assert resolve_airport("ICN") == "ICN"
    assert resolve_airport("fuk") == "FUK"  # 소문자 코드도 대문자로


def test_resolve_english_alias():
    assert resolve_airport("bangkok") == "BKK"
    assert resolve_airport("Tokyo") == "NRT"


def test_resolve_unknown_raises():
    try:
        resolve_airport("뉴욕시청앞")
    except ValueError:
        pass
    else:
        raise AssertionError("알 수 없는 입력은 ValueError 여야 함")


# ---- 유연한 날짜 포맷 --------------------------------------------------

def test_format_flexible_marks_cheapest():
    results = [
        ("2026-06-05", "2026-06-06", 220000.0),
        ("2026-06-06", "2026-06-07", 185000.0),
        ("2026-06-07", "2026-06-08", None),
    ]
    text = format_flexible(results, "ICN", "FUK")
    assert "ICN → FUK" in text
    assert "185,000" in text
    assert "⭐" in text                  # 최저가 표시
    assert "가장 싼 날: 2026-06-06" in text
    assert "2026-06-07~2026-06-08 : -" in text  # 가격 없는 날


# ---- watch 저장소 ------------------------------------------------------

def test_watchstore_add_list_remove():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "w.json")
        store = WatchStore(path=path)

        w = Watch(chat_id=1, origin="ICN", destination="FUK",
                  departure_date="2026-06-06", return_date="2026-06-07",
                  target_price=200000)
        assert store.add(w) is True
        assert store.add(w) is False           # 중복 거부
        assert len(store.list_for(1)) == 1
        assert len(store.list_for(999)) == 0    # 다른 채팅엔 안 보임

        # 디스크에서 다시 읽어도 유지
        store2 = WatchStore(path=path)
        assert len(store2.list_for(1)) == 1

        removed = store2.remove(1, 1)
        assert removed is not None
        assert len(store2.list_for(1)) == 0


def test_watchstore_persists_price_update():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "w.json")
        store = WatchStore(path=path)
        store.add(Watch(chat_id=2, origin="ICN", destination="KIX",
                        departure_date="2026-07-01", return_date=None,
                        target_price=150000))
        w = store.all()[0]
        w.last_price = 142000
        w.notified = True
        store.save()

        reloaded = WatchStore(path=path).all()[0]
        assert reloaded.last_price == 142000
        assert reloaded.notified is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("\n모든 기능 테스트 통과 ✅")
