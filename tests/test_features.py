"""신규 기능(공항 변환, 유연한 날짜 포맷, watch 저장소) 단위 테스트.

텔레그램 라이브러리 없이 코어 로직만 검증합니다.
실행: python tests/test_features.py  또는  python -m pytest
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta  # noqa: E402

from flightchecker.airports import resolve_airport  # noqa: E402
from flightchecker.formatter import format_flexible  # noqa: E402
from flightchecker.links import google_flights_url, skyscanner_url  # noqa: E402
from flightchecker.models import FlightOffer, FlightSegment  # noqa: E402
from flightchecker.nlsearch import (  # noqa: E402
    NLParseError,
    coerce_request,
    describe_request,
    extract_json,
)
from flightchecker.options import describe_options, parse_search_options  # noqa: E402
from flightchecker.pricehistory import PriceHistory  # noqa: E402
from flightchecker.search import drop_layovers, search_multi_city, sort_offers  # noqa: E402
from flightchecker.formatter import format_multi  # noqa: E402
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


# ---- 검색 옵션 파싱 ----------------------------------------------------

def test_parse_search_options():
    rest, opts = parse_search_options(
        ["인천", "방콕", "2026-06-06", "직항", "2명", "비즈니스"]
    )
    assert rest == ["인천", "방콕", "2026-06-06"]
    assert opts == {"non_stop": True, "adults": 2, "travel_class": 3}


def test_parse_search_options_defaults():
    rest, opts = parse_search_options(["ICN", "FUK", "2026-06-06", "200000"])
    assert rest == ["ICN", "FUK", "2026-06-06", "200000"]
    assert opts == {"non_stop": False, "adults": 1, "travel_class": None}


def test_describe_options():
    assert describe_options({"non_stop": True, "adults": 2, "travel_class": 4}) \
        == "직항만 · 성인 2명 · 일등석"
    assert describe_options({"non_stop": False, "adults": 1, "travel_class": None}) == ""


# ---- 경유 제외 정책 ----------------------------------------------------

def _offer(stops: int, minutes: int, price: float = 100000) -> FlightOffer:
    """테스트용 오퍼 생성 (stops만큼 경유 구간 추가)."""
    t0 = datetime(2026, 6, 6, 9, 0)
    segments = [
        FlightSegment(
            airline="TEST", flight_number=f"T{i}",
            departure_airport="AAA", departure_time=t0,
            arrival_airport="BBB", arrival_time=t0 + timedelta(minutes=minutes),
            duration=f"{minutes}m",
        )
        for i in range(stops + 1)
    ]
    return FlightOffer(
        price=price, currency="KRW", segments=segments,
        total_duration=f"{minutes}m", duration_minutes=minutes,
    )


def test_drop_layovers_short_haul_removes_stops():
    offers = [_offer(stops=0, minutes=85), _offer(stops=1, minutes=300, price=80000)]
    kept = drop_layovers(offers)
    assert all(o.stops == 0 for o in kept)   # 단거리는 직항만
    assert len(kept) == 1


def test_drop_layovers_keeps_all_when_no_nonstop():
    offers = [_offer(stops=1, minutes=900), _offer(stops=2, minutes=1100)]
    assert drop_layovers(offers) == offers    # 직항이 없으면 경유 유지


def test_drop_layovers_keeps_all_on_longhaul():
    offers = [_offer(stops=0, minutes=13 * 60), _offer(stops=1, minutes=16 * 60)]
    assert drop_layovers(offers) == offers    # 직항도 10시간 이상이면 경유 포함


def test_sort_offers_nonstop_first_then_price():
    """직항 우선, 그 안에서 가격 오름차순."""
    offers = [
        _offer(stops=1, minutes=800, price=90000),    # 경유인데 제일 쌈
        _offer(stops=0, minutes=700, price=150000),   # 직항 비싼 편
        _offer(stops=0, minutes=700, price=120000),   # 직항 싼 편
        _offer(stops=2, minutes=900, price=80000),
    ]
    ordered = sort_offers(offers)
    assert [(o.stops == 0, o.price) for o in ordered] == [
        (True, 120000), (True, 150000), (False, 80000), (False, 90000),
    ]


# ---- 다구간 검색 -------------------------------------------------------

class _FakeMultiClient:
    """multi_city_offers 호출 인자를 기록하고 모의 응답을 돌려주는 클라이언트."""

    def __init__(self):
        self.called_with = None

    def multi_city_offers(self, legs, **kwargs):
        self.called_with = {"legs": legs, **kwargs}
        return {
            "best_flights": [
                {
                    "flights": [
                        {
                            "departure_airport": {"id": "ICN", "time": "2026-06-06 09:00"},
                            "arrival_airport": {"id": "NRT", "time": "2026-06-06 11:30"},
                            "duration": 150,
                            "airline": "Korean Air",
                            "flight_number": "KE 701",
                        }
                    ],
                    "total_duration": 150,
                    "price": 550000,
                }
            ],
            "other_flights": [],
        }


def test_search_multi_city_passes_legs_and_parses():
    legs = [
        ("ICN", "NRT", "2026-06-06"),
        ("NRT", "KIX", "2026-06-08"),
        ("KIX", "ICN", "2026-06-10"),
    ]
    fake = _FakeMultiClient()
    offers = search_multi_city(legs, non_stop=True, adults=2, client=fake)

    assert fake.called_with["legs"] == legs
    assert fake.called_with["non_stop"] is True
    assert fake.called_with["adults"] == 2
    assert len(offers) == 1
    assert offers[0].price == 550000
    assert offers[0].stops == 0


def test_format_multi_shows_route_and_total():
    legs = [
        ("ICN", "NRT", "2026-06-06"),
        ("NRT", "KIX", "2026-06-08"),
        ("KIX", "ICN", "2026-06-10"),
    ]
    offers = [_offer(stops=0, minutes=150, price=550000)]
    text = format_multi(offers, legs)
    assert "다구간 ICN → NRT → KIX → ICN" in text
    assert "구간1. ICN→NRT 2026-06-06" in text
    assert "구간3. KIX→ICN 2026-06-10" in text
    assert "550,000" in text
    assert "전체 여정 총액" in text

    empty = format_multi([], legs)
    assert "찾지 못했습니다" in empty


# ---- 가격 이력 저장소 --------------------------------------------------

def test_pricehistory_record_series_baseline():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "h.json")
        hist = PriceHistory(path=path)
        now = datetime(2026, 6, 1, 12, 0)
        dep = "2026-06-20"

        for i, price in enumerate([200000, 210000, 190000]):
            hist.record("ICN", "FUK", dep, None, price, at=now + timedelta(hours=6 * i))
        hist.record("ICN", "FUK", dep, None, None, at=now)  # None은 무시

        points = hist.series("ICN", "FUK", dep, None)
        assert len(points) == 3
        assert [p for _, p in points] == [200000, 210000, 190000]

        base = hist.baseline("ICN", "FUK", dep, None, now=now + timedelta(days=1))
        assert base == (200000 + 210000 + 190000) / 3

        # 기록 2개짜리 노선은 기준 미달 → None
        hist.record("ICN", "KIX", dep, None, 150000, at=now)
        hist.record("ICN", "KIX", dep, None, 150000, at=now)
        assert hist.baseline("ICN", "KIX", dep, None, now=now) is None

        # 디스크에서 다시 읽어도 유지
        assert len(PriceHistory(path=path).series("ICN", "FUK", dep, None)) == 3


def test_stores_create_missing_parent_dirs():
    """저장 경로의 폴더가 없어도 자동 생성 (볼륨 미마운트·경로 오타 대비)."""
    with tempfile.TemporaryDirectory() as d:
        hist = PriceHistory(path=os.path.join(d, "없는폴더", "h.json"))
        hist.record("ICN", "FUK", "2026-08-01", None, 100000,
                    at=datetime(2026, 7, 1))
        assert len(hist.series("ICN", "FUK", "2026-08-01", None)) == 1

        store = WatchStore(path=os.path.join(d, "다른폴더", "w.json"))
        assert store.add(Watch(chat_id=1, origin="ICN", destination="FUK",
                               departure_date="2026-08-01", return_date=None,
                               target_price=100000)) is True


def test_env_paths_are_stripped():
    """WATCH_DB/PRICE_DB 값 앞뒤의 탭·공백은 무시된다."""
    import importlib

    from flightchecker import pricehistory, watchstore

    old_watch, old_price = os.environ.get("WATCH_DB"), os.environ.get("PRICE_DB")
    try:
        os.environ["WATCH_DB"] = "\t/data/watches.json"
        os.environ.pop("PRICE_DB", None)
        importlib.reload(watchstore)
        importlib.reload(pricehistory)
        assert watchstore._DEFAULT_PATH == "/data/watches.json"
        assert pricehistory._default_path() == "/data/price_history.json"
    finally:
        for key, value in (("WATCH_DB", old_watch), ("PRICE_DB", old_price)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(watchstore)
        importlib.reload(pricehistory)


def test_pricehistory_prunes_departed_routes():
    with tempfile.TemporaryDirectory() as d:
        hist = PriceHistory(path=os.path.join(d, "h.json"))
        now = datetime(2026, 6, 10, 12, 0)
        hist.record("ICN", "FUK", "2026-06-01", None, 100000, at=now)  # 출발일 지남
        hist.record("ICN", "FUK", "2026-06-20", None, 100000, at=now)  # 미래
        assert hist.series("ICN", "FUK", "2026-06-01", None) == []
        assert len(hist.series("ICN", "FUK", "2026-06-20", None)) == 1


# ---- 예매 링크 ---------------------------------------------------------

def test_booking_links():
    g = google_flights_url("ICN", "FUK", "2026-06-06", "2026-06-07")
    assert g.startswith("https://www.google.com/travel/flights?q=")
    assert "ICN" in g and "FUK" in g and "2026-06-06" in g

    s = skyscanner_url("ICN", "FUK", "2026-06-06", "2026-06-07")
    assert s == "https://www.skyscanner.co.kr/transport/flights/icn/fuk/260606/260607/"
    s1 = skyscanner_url("ICN", "FUK", "2026-06-06")
    assert s1 == "https://www.skyscanner.co.kr/transport/flights/icn/fuk/260606/"


# ---- 자연어 검색 (Gemini 응답 처리) -------------------------------------

_TODAY = datetime(2026, 7, 18)


def test_extract_json_variants():
    assert extract_json('{"intent": "search"}') == {"intent": "search"}
    assert extract_json('```json\n{"intent": "flex"}\n```') == {"intent": "flex"}
    assert extract_json('설명입니다 {"intent": "watch"} 끝') == {"intent": "watch"}
    try:
        extract_json("JSON이 아닙니다")
    except NLParseError:
        pass
    else:
        raise AssertionError("JSON 없는 응답은 NLParseError 여야 함")


def test_coerce_request_valid_search():
    req = coerce_request(
        {
            "intent": "search", "origin": "icn", "destination": "KIX",
            "departure_date": "2026-08-01", "return_date": "2026-08-03",
            "adults": 2, "non_stop": True, "travel_class": 3,
        },
        today=_TODAY,
    )
    assert req["intent"] == "search"
    assert req["origin"] == "ICN" and req["destination"] == "KIX"
    assert req["adults"] == 2 and req["non_stop"] is True and req["travel_class"] == 3
    assert "ICN→KIX" in describe_request(req)


def test_coerce_request_demotes_past_date():
    req = coerce_request(
        {"intent": "search", "origin": "ICN", "destination": "KIX",
         "departure_date": "2026-01-01"},
        today=_TODAY,
    )
    assert req["intent"] == "unknown"
    assert req["clarification"]


def test_coerce_request_watch_needs_price():
    base = {"intent": "watch", "origin": "ICN", "destination": "BKK",
            "departure_date": "2026-09-01"}
    assert coerce_request(dict(base), today=_TODAY)["intent"] == "unknown"
    ok = coerce_request(dict(base, target_price=300000), today=_TODAY)
    assert ok["intent"] == "watch" and ok["target_price"] == 300000


def test_coerce_request_multi_legs():
    req = coerce_request(
        {"intent": "multi", "legs": [
            ["ICN", "NRT", "2026-08-01"],
            ["NRT", "KIX", "2026-08-03"],
            ["잘못된값", "ICN", "2026-08-05"],   # 무시됨
        ]},
        today=_TODAY,
    )
    assert req["intent"] == "multi"
    assert req["legs"] == [("ICN", "NRT", "2026-08-01"), ("NRT", "KIX", "2026-08-03")]

    too_few = coerce_request({"intent": "multi", "legs": [["ICN", "NRT", "2026-08-01"]]},
                             today=_TODAY)
    assert too_few["intent"] == "unknown"


def test_coerce_request_garbage_is_safe():
    req = coerce_request(
        {"intent": "hack", "adults": "많이", "travel_class": 9,
         "target_price": "비쌈", "origin": "인천공항"},
        today=_TODAY,
    )
    assert req["intent"] == "unknown"
    assert req["adults"] == 1 and req["travel_class"] is None
    assert req["target_price"] is None and req["origin"] is None


# ---- watch 하위 호환 ---------------------------------------------------

def test_watch_loads_old_json_without_new_fields():
    """예전 버전이 저장한 watches.json(신규 필드 없음)도 읽혀야 한다."""
    old_item = {
        "chat_id": 1, "origin": "ICN", "destination": "FUK",
        "departure_date": "2026-06-06", "return_date": None,
        "target_price": 200000.0, "currency": "KRW", "non_stop": False,
        "created_at": "2026-06-01T00:00:00", "last_price": None, "notified": False,
    }
    w = Watch(**old_item)
    assert w.adults == 1
    assert w.travel_class is None
    assert w.last_drop_alert is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("\n모든 기능 테스트 통과 ✅")
