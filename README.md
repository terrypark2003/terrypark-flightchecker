# terrypark-flightchecker ✈️

SerpApi(Google Flights) 기반 항공권 검색기. **지금은 CLI로**, **나중엔 텔레그램 봇으로** 같은 검색 로직을 그대로 쓸 수 있도록 코어 로직을 분리해 설계했습니다.

예) 6월 6일 출발 · 6월 7일 귀국, 인천(ICN) → 후쿠오카(FUK) 왕복:

```bash
python cli.py ICN FUK 2026-06-06 --return 2026-06-07
```

```
🔎 ICN → FUK (왕복) 2026-06-06 ~ 2026-06-07

1. 💰 185,000 KRW
  ICN → FUK  06/06 09:00 ~ 06/06 10:25  (1h25m, 직항)
        ✈ Asiana Airlines
...
```

## 구조

```
flightchecker/          ← 코어 패키지 (CLI·봇 공통)
  serpapi_client.py     ← SerpApi google_flights API 호출
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

## SerpApi 키 발급 (무료)

1. https://serpapi.com 접속 → **Sign Up** (이메일 또는 구글 계정, 카드 불필요)
2. 가입/로그인 후 대시보드의 **Your Private API Key** 복사
3. `.env` 의 `SERPAPI_KEY` 에 붙여넣기

> 무료 등급은 **월 100회 검색**까지 가능합니다. 실제 구글 항공권 가격을 그대로 가져옵니다.

## 사용법 (CLI)

```bash
# 왕복
python cli.py ICN FUK 2026-06-06 -r 2026-06-07

# 편도, 직항만, 성인 2명
python cli.py ICN FUK 2026-06-06 --non-stop --adults 2

# 옵션
#   -r/--return  귀국일(왕복)   --currency 통화(기본 KRW)
#   --non-stop   직항만         --adults   인원
#   --limit      표시 건수
```

## 텔레그램 봇으로 검색

`.env` 에 `TELEGRAM_BOT_TOKEN` 추가 후 (봇 토큰은 텔레그램 [@BotFather](https://t.me/BotFather) 에서 `/newbot` 으로 발급):

```bash
pip install -r requirements.txt   # python-telegram-bot 포함
python bot.py
```

봇이 켜지면 텔레그램 채팅창에서:

```
/flight ICN FUK 2026-06-06 2026-06-07   # 왕복
/flight ICN FUK 2026-06-06              # 편도
/help                                    # 사용법
```

- 입력창의 `/` 메뉴에 명령어가 자동 등록됩니다.
- 날짜 형식(YYYY-MM-DD)이 틀리면 안내 메시지를 보냅니다.
- 검색 로직은 CLI와 동일한 `flightchecker.search_flights()` 를 그대로 사용합니다.

## 봇 24시간 켜두기

PC를 꺼도 봇이 살아있게 클라우드에 올립니다. 두 가지 방법:

### A. 완전 무료 — Oracle Cloud Always Free (평생 무료)
평생 무료 VM에 올려 24시간 운영합니다. 설치 스크립트가 systemd 등록까지
자동으로 해줘서, 봇이 꺼지거나 서버가 재부팅돼도 자동 재시작됩니다.
→ 자세한 단계: [`deploy/ORACLE_CLOUD.md`](deploy/ORACLE_CLOUD.md)

```bash
# 서버(Ubuntu)에서:
git clone https://github.com/terrypark2003/terrypark-flightchecker.git
cd terrypark-flightchecker && git checkout claude/epic-gauss-Eodjx
cp .env.example .env && nano .env   # 키 입력
bash deploy/setup_server.sh
```

### B. 간편 — Railway (무료 크레딧 후 소액)
[railway.app](https://railway.app) 가입 → Deploy from GitHub repo → 이 저장소,
브랜치 `claude/epic-gauss-Eodjx` 선택 → **Variables** 에 `SERPAPI_KEY`,
`TELEGRAM_BOT_TOKEN` 입력. `Procfile`/`railway.json` 으로 자동 실행됩니다.

> 같은 봇 토큰을 PC와 클라우드에서 동시에 실행하면 충돌합니다.
> 클라우드에 올린 뒤에는 로컬 `python bot.py` 는 꺼두세요.

배포용 파일:
- `Procfile` — 실행 명령(`worker: python bot.py`)
- `railway.json` — 빌드/재시작 정책
- `runtime.txt` — Python 버전 고정
- `deploy/` — Oracle Cloud용 systemd 서비스 + 설치 스크립트

## 테스트

API 키 없이도 파싱·포매팅 로직을 검증합니다 (모의 응답 사용):

```bash
python tests/test_formatter.py
# 또는
python -m pytest
```

## 참고

- 왕복 검색 시 SerpApi 1차 응답은 **가는편 여정 + 왕복 총액**을 줍니다. 오는편 상세 시간표는 `departure_token`으로 2차 조회가 필요하며, 현재는 가는편 여정과 총 가격 기준으로 보여줍니다.

## 자주 쓰는 공항 코드

| 코드 | 공항 |
|------|------|
| ICN  | 인천 |
| GMP  | 김포 |
| FUK  | 후쿠오카 |
| NRT/HND | 도쿄(나리타/하네다) |
| KIX  | 오사카(간사이) |
| CJU  | 제주 |
