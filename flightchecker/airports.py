"""공항/도시 이름 → IATA 코드 변환.

사용자가 "인천", "후쿠오카", "tokyo" 처럼 입력해도 ICN, FUK 같은
3글자 코드로 바꿔줍니다. 이미 코드(3글자 영문)면 그대로 사용합니다.
"""

from __future__ import annotations

# 한글/영문 별칭 → IATA 코드. 필요하면 계속 추가하면 됩니다.
_ALIASES: dict[str, str] = {
    # 한국
    "인천": "ICN", "서울": "ICN", "인천공항": "ICN",
    "김포": "GMP", "김포공항": "GMP",
    "제주": "CJU", "제주도": "CJU",
    "부산": "PUS", "김해": "PUS",
    "대구": "TAE",
    "청주": "CJJ",
    "무안": "MWX",
    # 일본
    "후쿠오카": "FUK", "fukuoka": "FUK",
    "도쿄": "NRT", "동경": "NRT", "tokyo": "NRT", "나리타": "NRT",
    "하네다": "HND", "haneda": "HND",
    "오사카": "KIX", "osaka": "KIX", "간사이": "KIX",
    "삿포로": "CTS", "sapporo": "CTS", "신치토세": "CTS",
    "나고야": "NGO", "nagoya": "NGO",
    "오키나와": "OKA", "okinawa": "OKA", "나하": "OKA",
    # 동남아/중화권
    "방콕": "BKK", "bangkok": "BKK",
    "다낭": "DAD", "danang": "DAD",
    "하노이": "HAN", "hanoi": "HAN",
    "호치민": "SGN",
    "싱가포르": "SIN", "singapore": "SIN",
    "쿠알라룸푸르": "KUL",
    "발리": "DPS", "bali": "DPS", "덴파사르": "DPS",
    "마닐라": "MNL", "manila": "MNL",
    "세부": "CEB", "cebu": "CEB",
    "타이베이": "TPE", "타이페이": "TPE", "타이완": "TPE", "대만": "TPE", "taipei": "TPE",
    "홍콩": "HKG", "hongkong": "HKG",
    "마카오": "MFM", "macau": "MFM",
    "베이징": "PEK", "북경": "PEK", "beijing": "PEK",
    "상하이": "PVG", "상해": "PVG", "shanghai": "PVG",
    "괌": "GUM", "guam": "GUM",
    "사이판": "SPN", "saipan": "SPN",
    # 미주/유럽/오세아니아 (자주 쓰는 것 위주)
    "로스앤젤레스": "LAX", "la": "LAX", "엘에이": "LAX",
    "뉴욕": "JFK", "newyork": "JFK",
    "샌프란시스코": "SFO",
    "하와이": "HNL", "호놀룰루": "HNL", "hawaii": "HNL",
    "파리": "CDG", "paris": "CDG",
    "런던": "LHR", "london": "LHR",
    "프랑크푸르트": "FRA",
    "시드니": "SYD", "sydney": "SYD",
}


def resolve_airport(value: str) -> str:
    """입력값을 IATA 코드로 변환. 변환 불가하면 ValueError.

    - 이미 3글자 영문이면 대문자로 그대로 반환 (예: 'fuk' -> 'FUK')
    - 한글/영문 별칭이면 매핑 테이블에서 변환
    """
    raw = value.strip()
    if not raw:
        raise ValueError("공항 이름이 비어 있습니다.")

    # 별칭 우선 조회 (공백 제거, 소문자 정규화)
    key = raw.replace(" ", "").lower()
    if key in _ALIASES:
        return _ALIASES[key]

    # 3글자 영문 코드면 그대로 사용
    if len(raw) == 3 and raw.isalpha() and raw.isascii():
        return raw.upper()

    raise ValueError(
        f"'{value}' 를 공항 코드로 변환할 수 없습니다. "
        "3글자 코드(예: ICN) 또는 알려진 도시 이름(예: 인천, 후쿠오카)을 입력하세요."
    )
