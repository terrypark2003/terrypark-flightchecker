"""노선별 가격 이력 저장소.

가격 알림 검사·수동 검색에서 확인한 최저가를 시각과 함께 기록합니다.
기존 검색 결과를 재활용하므로 API 호출이 늘지 않으며, /history 그래프와
급락 감지 기능의 데이터 소스가 됩니다.

저장 경로: PRICE_DB 환경변수 > WATCH_DB와 같은 폴더 > 패키지 옆 (순서대로)
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta

_LOCK = threading.Lock()

MAX_POINTS_PER_ROUTE = 300  # 노선당 보관 상한 (6시간 주기 기준 약 두 달치)
KEEP_PAST_DAYS = 2          # 출발일이 지난 노선은 이틀 뒤 정리


def _default_path() -> str:
    # 환경변수 값에 실수로 섞인 공백/탭은 제거 (Railway 변수 붙여넣기 실수 대비)
    price_db = os.getenv("PRICE_DB", "").strip()
    if price_db:
        return price_db
    watch_db = os.getenv("WATCH_DB", "").strip()
    if watch_db:
        # 가격 알림 파일과 같은 폴더(Railway 볼륨 등)에 저장
        return os.path.join(os.path.dirname(watch_db) or ".", "price_history.json")
    return os.path.join(os.path.dirname(__file__), "..", "price_history.json")


def route_key(origin: str, destination: str, departure_date: str, return_date: str | None) -> str:
    return f"{origin}-{destination}:{departure_date}:{return_date or '-'}"


class PriceHistory:
    def __init__(self, path: str | None = None):
        self.path = path or _default_path()
        # {route_key: [{"t": ISO시각, "p": 가격}, ...]}
        self._data: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self._data = {}
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, TypeError):
            self._data = {}

    def _save(self) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def _prune(self, now: datetime) -> None:
        """출발일이 한참 지난 노선 삭제 + 노선당 포인트 수 상한 유지."""
        cutoff = (now - timedelta(days=KEEP_PAST_DAYS)).date()
        for key in list(self._data):
            try:
                dep = datetime.strptime(key.split(":")[1], "%Y-%m-%d").date()
            except (IndexError, ValueError):
                del self._data[key]
                continue
            if dep < cutoff:
                del self._data[key]
            elif len(self._data[key]) > MAX_POINTS_PER_ROUTE:
                self._data[key] = self._data[key][-MAX_POINTS_PER_ROUTE:]

    def record(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None,
        price: float | None,
        at: datetime | None = None,
    ) -> None:
        """가격 한 건 기록. price가 None이면 무시."""
        if price is None:
            return
        now = at or datetime.now()
        key = route_key(origin, destination, departure_date, return_date)
        with _LOCK:
            self._data.setdefault(key, []).append(
                {"t": now.isoformat(timespec="seconds"), "p": float(price)}
            )
            self._prune(now)
            self._save()

    def series(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None,
    ) -> list[tuple[datetime, float]]:
        """해당 노선의 (시각, 가격) 목록을 시간 오름차순으로 반환."""
        key = route_key(origin, destination, departure_date, return_date)
        points = [
            (datetime.fromisoformat(item["t"]), float(item["p"]))
            for item in self._data.get(key, [])
        ]
        points.sort(key=lambda x: x[0])
        return points

    def baseline(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None,
        days: int = 14,
        min_points: int = 3,
        now: datetime | None = None,
    ) -> float | None:
        """최근 days일간 기록의 평균가. 급락 감지의 기준값.

        현재 가격을 record()하기 **전에** 호출해야 기준에 현재가가 섞이지 않습니다.
        기록이 min_points개 미만이면 None (판단 보류).
        """
        now = now or datetime.now()
        since = now - timedelta(days=days)
        prices = [
            p for t, p in self.series(origin, destination, departure_date, return_date)
            if t >= since
        ]
        if len(prices) < min_points:
            return None
        return sum(prices) / len(prices)
