"""대한항공 스카이패스 보너스 항공권 공제 마일리지 추정 + 마일 가치 계산.

실시간 보너스 좌석 조회는 대한항공이 API를 제공하지 않아 불가능하므로,
공개된 스카이패스 공제표(지역대 기준)를 데이터로 갖고 있다가
현금 최저가와 비교해 "1마일당 가치"를 계산해 보여줍니다.

⚠️ 공제표는 대한항공 정책에 따라 바뀔 수 있습니다. 아래 _CHART 값만
고치면 되도록 데이터를 한곳에 모아뒀습니다. (평수기 편도 기준)
공식 공제표: https://www.koreanair.com/contents/skypass/use-miles/award-ticket/redemption
"""

from __future__ import annotations

import os

# 1마일을 이 값(원) 이상으로 쓸 수 있으면 "마일 사용이 이득"으로 판단
MILE_VALUE_THRESHOLD_KRW = float(os.getenv("MILE_VALUE_KRW", "15"))

# 평수기 · 편도 공제 마일리지 (성수기는 1.5배)
# cabin: economy=이코노미, prestige=프레스티지(비즈니스), first=일등석
_CHART: dict[str, dict[str, int | None]] = {
    "domestic": {"economy": 5_000, "prestige": 8_000, "first": None},
    "japan_ne": {"economy": 15_000, "prestige": 22_500, "first": 30_000},   # 일본·중국·동북아
    "sea":      {"economy": 20_000, "prestige": 30_000, "first": 40_000},   # 동남아·괌·사이판
    "swa":      {"economy": 25_000, "prestige": 37_500, "first": 50_000},   # 서남아·중앙아
    "longhaul": {"economy": 35_000, "prestige": 62_500, "first": 80_000},   # 미주·유럽·중동·대양주
}

_ZONE_LABELS = {
    "domestic": "국내선",
    "japan_ne": "일본·중국·동북아",
    "sea": "동남아",
    "swa": "서남아시아",
    "longhaul": "미주·유럽·대양주",
}

_KOREA = {
    "ICN", "GMP", "CJU", "PUS", "TAE", "CJJ", "MWX", "KWJ", "RSU", "USN", "HIN", "YNY",
}

_ZONE_AIRPORTS: dict[str, set[str]] = {
    "japan_ne": {
        # 일본
        "NRT", "HND", "KIX", "ITM", "FUK", "CTS", "NGO", "OKA", "FSZ", "KMQ", "KOJ",
        "HIJ", "OKJ", "SDJ", "AOJ", "AXT", "KMJ", "NGS", "OIT", "TAK", "MYJ",
        # 중국·동북아 (홍콩·마카오·타이베이·몽골·극동러시아 포함)
        "PEK", "PKX", "PVG", "SHA", "TSN", "TAO", "DLC", "CAN", "SZX", "CTU", "CKG",
        "WUH", "XIY", "SJW", "YNJ", "HRB", "SHE", "CGQ", "KMG", "HGH", "NKG",
        "HKG", "MFM", "TPE", "TSA", "KHH", "ULN", "VVO",
    },
    "sea": {
        "BKK", "HKT", "CNX", "SGN", "HAN", "DAD", "CXR", "SIN", "KUL", "PEN",
        "MNL", "CEB", "CRK", "DPS", "CGK", "PNH", "REP", "VTE", "RGN", "BWN",
        "GUM", "SPN",
    },
    "swa": {
        "DEL", "BOM", "MAA", "CCU", "KTM", "CMB", "MLE", "DAC",
        "TAS", "ALA", "NUR",
    },
    "longhaul": {
        # 미주
        "JFK", "EWR", "LAX", "SFO", "SEA", "LAS", "HNL", "ORD", "DFW", "ATL",
        "BOS", "IAD", "MIA", "YVR", "YYZ", "MEX", "GRU", "EZE", "SCL", "LIM", "BOG",
        # 유럽
        "CDG", "LHR", "FRA", "AMS", "MAD", "BCN", "FCO", "MXP", "VIE", "ZRH",
        "PRG", "BUD", "IST", "LIS", "OSL", "ARN", "CPH", "HEL", "WAW",
        # 중동·아프리카
        "DXB", "AUH", "DOH", "TLV", "JED", "RUH", "CAI", "JNB", "NBO", "ADD",
        # 대양주
        "SYD", "MEL", "BNE", "AKL", "NAN",
    },
}

_CABIN_LABELS = {"economy": "이코노미", "prestige": "프레스티지", "first": "일등석"}


def _zone_of(code: str) -> str | None:
    code = code.upper()
    if code in _KOREA:
        return "domestic"
    for zone, airports in _ZONE_AIRPORTS.items():
        if code in airports:
            return zone
    return None


def _cabin_from_travel_class(travel_class: int | None) -> str:
    # SerpApi 기준: 1/None=이코노미, 2=프리미엄 이코노미(공제표엔 없어 이코노미로),
    # 3=비즈니스(프레스티지), 4=일등석
    if travel_class == 3:
        return "prestige"
    if travel_class == 4:
        return "first"
    return "economy"


def skypass_estimate(
    origin: str,
    destination: str,
    round_trip: bool,
    travel_class: int | None = None,
) -> dict | None:
    """스카이패스 예상 공제 마일리지.

    반환: {"miles": int, "cabin": str, "zone": str} 또는 None
    (한국 출발/도착이 아니거나 지역대를 모르면 None — 공제표가 한국 발착 기준)
    """
    o_zone, d_zone = _zone_of(origin), _zone_of(destination)
    if o_zone is None or d_zone is None:
        return None
    if o_zone != "domestic" and d_zone != "domestic":
        return None  # 한국 발착 아님
    zone = d_zone if o_zone == "domestic" else o_zone

    cabin = _cabin_from_travel_class(travel_class)
    one_way = _CHART[zone].get(cabin)
    if one_way is None:
        return None
    return {
        "miles": one_way * (2 if round_trip else 1),
        "cabin": _CABIN_LABELS[cabin],
        "zone": _ZONE_LABELS[zone],
    }


def mileage_note(
    origin: str,
    destination: str,
    round_trip: bool,
    cash_price: float | None,
    travel_class: int | None = None,
) -> str:
    """검색 결과에 덧붙일 마일리지 안내 문구. 해당 없으면 빈 문자열."""
    est = skypass_estimate(origin, destination, round_trip, travel_class)
    if est is None:
        return ""

    trip_label = "왕복" if round_trip else "편도"
    lines = [
        f"🎫 스카이패스 예상 공제: {trip_label} {est['miles']:,}마일"
        f" (평수기 {est['cabin']} · {est['zone']})"
    ]
    if cash_price:
        value = cash_price / est["miles"]
        if value >= MILE_VALUE_THRESHOLD_KRW:
            verdict = "✨ 마일리지 사용이 이득이에요"
        else:
            verdict = "💵 현금 구매가 나을 수 있어요"
        lines.append(
            f"   현금 최저가 기준 1마일 ≈ {value:.1f}원 → {verdict}"
            f" (기준 {MILE_VALUE_THRESHOLD_KRW:.0f}원)"
        )
    lines.append("   ※ 성수기 1.5배 · 유류할증료/세금 별도 · 보너스 좌석은 대한항공에서 확인")
    return "\n".join(lines)
