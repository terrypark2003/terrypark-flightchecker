"""검색 옵션 토큰 파싱 (직항, 인원 수, 좌석 등급).

명령어 인자 중 어디에 있어도 인식합니다.
예) /flight 인천 후쿠오카 2026-06-06 직항 2명 비즈니스
"""

from __future__ import annotations

# SerpApi travel_class 값: 1=이코노미, 2=프리미엄 이코노미, 3=비즈니스, 4=일등석
TRAVEL_CLASS_NAMES = {1: "이코노미", 2: "프리미엄 이코노미", 3: "비즈니스", 4: "일등석"}

_CLASS_TOKENS = {
    "이코노미": 1,
    "프리미엄": 2, "프리미엄이코노미": 2,
    "비즈니스": 3, "비즈": 3,
    "일등석": 4, "퍼스트": 4, "일등": 4,
}
_NONSTOP_TOKENS = {"직항", "직항만", "논스톱"}


def parse_search_options(args: list[str]) -> tuple[list[str], dict]:
    """옵션 토큰을 분리해 (남은 인자, 옵션 dict)를 반환.

    옵션 dict 키: non_stop(bool), adults(int), travel_class(int|None)
    """
    opts: dict = {"non_stop": False, "adults": 1, "travel_class": None}
    rest: list[str] = []
    for token in args:
        if token in _NONSTOP_TOKENS:
            opts["non_stop"] = True
        elif token.endswith("명") and token[:-1].isdigit():
            opts["adults"] = max(1, min(9, int(token[:-1])))
        elif token in _CLASS_TOKENS:
            opts["travel_class"] = _CLASS_TOKENS[token]
        else:
            rest.append(token)
    return rest, opts


def describe_options(opts: dict) -> str:
    """기본값이 아닌 옵션만 사람이 읽을 문구로. 전부 기본값이면 빈 문자열."""
    parts = []
    if opts.get("non_stop"):
        parts.append("직항만")
    if opts.get("adults", 1) > 1:
        parts.append(f"성인 {opts['adults']}명")
    travel_class = opts.get("travel_class")
    if travel_class and travel_class != 1:
        parts.append(TRAVEL_CLASS_NAMES[travel_class])
    return " · ".join(parts)
