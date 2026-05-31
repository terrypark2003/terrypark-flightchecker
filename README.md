# terrypark-flightchecker ✈️

Amadeus API 기반 항공권 검색기. **지금은 CLI로**, **나중엔 텔레그램 봇으로** 같은 검색 로직을 그대로 쓸 수 있도록 코어 로직을 분리해 설계했습니다.

예) 6월 6일 출발 · 6월 7일 귀국, 인천(ICN) → 후쿠오카(FUK) 왕복:

```bash
python cli.py ICN FUK 2026-06-06 --return 2026-06-07
```

```
🔎 ICN → FUK (왕복) 2026-06-06 ~ 2026-06-07

1. 💰 185,000 KRW
  [가는편] ICN → FUK  06/06 09:00 ~ 06/06 10:25  (1h25m, 직항)
        ✈ ASIANA AIRLINES
  [오는편] FUK → ICN  06/07 18:00 ~ 06/07 19:30  (1h30m, 직항)
        ✈ ASIANA AIRLINES
...
```

## 구조

```
flightchecker/          ← 코어 패키지 (CLI·봇 공통)
  amadeus_client.py     ← Amadeus OAuth2 + 항공권 검색 API 호출
  models.py             ← 응답 JSON → 다루기 쉬운 dataclass
  search.py             ← search_flights() : 어디서든 쓰는 검색 진입점
  formatter.py          ← 결과 → 사람이 읽는 텍스트 (CLI·텔레그램 공용)
cli.py                  ← 커맨드라인 인터페이스 (지금 사용)
bot.py                  ← 텔레그램 봇 골격 (미래 확장)
tests/                  ← API 키 없이 검증되는 단위 테스트
```

핵심은 검색 로직이 `flightchecker.search.search_flights()` 한 곳에 모여 있다는 점입니다. CLI와 봇은 이 함수를 호출만 합니다.

```python
from flightchecker import search_flights
offers = search_flights("ICN", "FUK", "2026-06-06", "2026-06-07")
```

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env   # 그리고 발급받은 키 입력
```

## Amadeus API 키 발급 (무료)

1. https://developers.amadeus.com 가입
2. **My Self-Service Workspace → Create New App**
3. 발급된 **API Key / API Secret** 을 `.env` 의 `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` 에 입력

> `test` 환경은 무료지만 실제와 다른 테스트용 데이터가 일부 섞여 있습니다.
> 실데이터가 필요하면 `AMADEUS_ENV=production` (별도 승인 필요).

## 사용법 (CLI)

```bash
# 왕복
python cli.py ICN FUK 2026-06-06 -r 2026-06-07

# 편도, 직항만, 성인 2명
python cli.py ICN FUK 2026-06-06 --non-stop --adults 2

# 옵션
#   -r/--return  귀국일(왕복)   --currency 통화(기본 KRW)
#   --non-stop   직항만         --adults   인원
#   --max        후보 수        --limit    표시 건수
```

## 텔레그램 봇으로 확장

`.env` 에 `TELEGRAM_BOT_TOKEN` (BotFather 발급) 추가 후:

```bash
pip install python-telegram-bot
python bot.py
```

채팅에서:

```
/flight ICN FUK 2026-06-06 2026-06-07
```

## 테스트

API 키 없이도 파싱·포매팅 로직을 검증합니다 (모의 응답 사용):

```bash
python tests/test_formatter.py
# 또는
python -m pytest
```

## 자주 쓰는 공항 코드

| 코드 | 공항 |
|------|------|
| ICN  | 인천 |
| GMP  | 김포 |
| FUK  | 후쿠오카 |
| NRT/HND | 도쿄(나리타/하네다) |
| KIX  | 오사카(간사이) |
| CJU  | 제주 |
