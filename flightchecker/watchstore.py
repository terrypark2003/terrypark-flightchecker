"""가격 알림(watch) 저장소.

사용자가 등록한 "이 노선이 목표가 이하로 떨어지면 알림" 항목을 JSON 파일에
저장합니다. 별도 DB 없이 가볍게 동작하도록 파일 기반으로 구현했습니다.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime

_DEFAULT_PATH = os.getenv("WATCH_DB", os.path.join(os.path.dirname(__file__), "..", "watches.json"))
_LOCK = threading.Lock()


@dataclass
class Watch:
    chat_id: int            # 알림 보낼 텔레그램 채팅
    origin: str
    destination: str
    departure_date: str
    return_date: str | None
    target_price: float
    currency: str = "KRW"
    non_stop: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    last_price: float | None = None   # 마지막으로 확인한 최저가
    notified: bool = False            # 목표가 도달 알림을 이미 보냈는지

    @property
    def key(self) -> str:
        """동일 노선/날짜/목표가를 식별하는 키 (중복 등록 방지·삭제용)."""
        return f"{self.chat_id}:{self.origin}-{self.destination}:{self.departure_date}:{self.return_date}:{self.target_price:.0f}"


class WatchStore:
    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = path
        self._watches: list[Watch] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self._watches = []
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._watches = [Watch(**item) for item in data]
        except (json.JSONDecodeError, TypeError):
            self._watches = []

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([asdict(w) for w in self._watches], f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def add(self, watch: Watch) -> bool:
        """추가. 같은 key가 이미 있으면 False (중복)."""
        with _LOCK:
            if any(w.key == watch.key for w in self._watches):
                return False
            self._watches.append(watch)
            self._save()
            return True

    def list_for(self, chat_id: int) -> list[Watch]:
        return [w for w in self._watches if w.chat_id == chat_id]

    def all(self) -> list[Watch]:
        return list(self._watches)

    def remove(self, chat_id: int, index: int) -> Watch | None:
        """해당 채팅의 index번째(1부터) 항목 삭제. 반환: 삭제된 Watch 또는 None."""
        with _LOCK:
            items = self.list_for(chat_id)
            if index < 1 or index > len(items):
                return None
            target = items[index - 1]
            self._watches = [w for w in self._watches if w is not target]
            self._save()
            return target

    def save(self) -> None:
        """all()로 받은 Watch 객체의 필드를 바꾼 뒤 디스크에 반영."""
        with _LOCK:
            self._save()
