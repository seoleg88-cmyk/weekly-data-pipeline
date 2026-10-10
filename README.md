# weekly-data-pipeline

주간 증시 브리핑에 들어가는 11개 자산 중 9개(시세)와 미국 국채/연준 금리 4개 시리즈를
매주 자동으로 받아서 레포에 JSON으로 커밋해두는 파이프라인. 데일리 시황 파이프라인과
같은 생각으로 만들었습니다: "숫자는 검색이 아니라 코드/API로 받는다."

## 왜 만들었나

지난 주간 브리핑은 코스피·코스닥·S&P500 같은 시세까지 WebSearch로 찾았는데, 이 과정에서
실제로 오류가 한 번 나왔습니다(같은 기사 수치가 다른 날짜에 중복 노출되는 문제). 또
"1주 전", "1개월 전"을 추석 연휴 같은 휴장일까지 감안해서 사람이 수동으로 날짜를 골라야
했습니다. 이 레포는 그 두 가지를 코드로 없앱니다.

## 구성

```
scripts/fetch_prices.py   yfinance로 9개 자산(코스피/코스닥/S&P500/나스닥/다우/
                           원달러/WTI/Brent/금/비트코인) 수집
scripts/fetch_rates.py    FRED 공개 CSV(키 불필요)로 美 10년물/2년물 국채금리,
                           연준 기준금리 상단/하단 수집
tests/test_offsets.py     네트워크 없이 도는 단위 테스트. "거래일 오프셋" 로직이
                           추석 같은 연휴를 자동으로 건너뛰는지 검증
.github/workflows/weekly-fetch.yml   매주 일요일 19:00 UTC(월요일 04:00 KST)에
                           위 스크립트를 돌리고 data/*.json을 레포에 커밋
data/                      결과 JSON이 쌓이는 곳
```

## 핵심 아이디어: "1주 전 / 1개월 전"을 날짜 계산이 아니라 거래일 인덱싱으로

야후 파이낸스가 주는 일봉 히스토리에는 그 시장의 실제 휴장일(추석, 성탄절, 명절 등)이
이미 빠져 있습니다. 그래서 "최근 종가로부터 5번째 전 행 = 1주 전", "21번째 전 행 =
1개월 전"으로 그냥 인덱싱하면, 휴장일이 며칠 끼어 있어도 자동으로 맞는 거래일을
찾아줍니다. 지난 브리핑에서 "추석 연휴라 9/23을 써야 한다"고 사람이 직접 계산했던 걸
`tests/test_offsets.py`가 똑같은 상황(9/24, 9/25 휴장)을 가짜 데이터로 만들어서
검증합니다 — 결과는 정확히 9/23이 나옵니다.

## 지금 안 되는 것 (phase 2)

- **한국은행 기준금리**: ECOS Open API 키가 있어야 안정적으로 받습니다. 키 없이도
  받을 수 있는 범위(시세 9개 + 美 금리 4개)부터 먼저 만들었습니다. 키를 발급받으면
  `scripts/fetch_rates.py`에 `fetch_bok_rate()` 같은 함수를 하나 더 추가하면 됩니다.
  (ECOS: https://ecos.bok.or.kr/api/ 에서 간단한 가입 후 즉시 발급)
- **FOMC/금통위 일정, 美 국채입찰 일정, 거래소 휴장일**: 공식 페이지 주소가 고정돼
  있어서(연준 FOMC 캘린더, 재무부 입찰 일정, KRX 휴장일 공시) 검색보다 훨씬
  안정적으로 가져올 수 있지만, 페이지 구조가 바뀌면 깨질 수 있어 이번 단계에는
  넣지 않았습니다. 필요하면 다음 단계로 추가 가능합니다.
- **경제지표 컨센서스, 기업 실적 컨센서스, "이번주 이슈" 서술**: 이 부분은 여전히
  WebSearch/WebFetch로 승인된 출처(공식기관 → Reuters/Bloomberg/AP 등 → 연합뉴스 등)를
  교차검증하는 방식을 유지합니다.

## 설치 (한 번만)

1. 이 폴더 전체를 GitHub에 올립니다. **빈 레포를 하나 만든 뒤**(Public 추천 — 민감한
   내용이 없고, 주간 브리핑 작성 시 토큰 없이 그냥 읽어올 수 있어서 편합니다):
   ```bash
   cd weekly-data-pipeline
   git init
   git add .
   git commit -m "init: weekly data pipeline"
   git branch -M main
   git remote add origin https://github.com/<본인계정>/<레포이름>.git
   git push -u origin main
   ```
2. **별도 토큰이나 키 설정이 필요 없습니다.** GitHub Actions가 기본으로 제공하는
   `GITHUB_TOKEN`으로 같은 레포에 커밋/푸시할 수 있게 워크플로에 이미
   `permissions: contents: write`를 넣어뒀습니다.
3. 레포 Settings → Actions → General → Workflow permissions에서 "Read and write
   permissions"가 선택돼 있는지 한 번만 확인하세요(조직 기본값이 read-only인 경우가
   있습니다). 안 되어 있으면 push 단계가 403으로 실패합니다.
4. Actions 탭에서 "Weekly market data fetch" 워크플로를 한 번 수동 실행
   (workflow_dispatch)해서 정상적으로 `data/latest_prices.json`,
   `data/latest_rates.json`이 커밋되는지 확인하세요.

## 주간 브리핑 작성 시 이 데이터를 쓰는 법

레포가 Public이면 아래 raw URL을 WebFetch로 그냥 읽으면 됩니다(토큰 불필요):

```
https://raw.githubusercontent.com/<계정>/<레포이름>/main/data/latest_prices.json
https://raw.githubusercontent.com/<계정>/<레포이름>/main/data/latest_rates.json
```

주간 브리핑 스케줄 작업(scheduled task)의 프롬프트에 "시세·금리는 위 두 URL에서
먼저 읽고, 거기 없는 값(한국은행 기준금리, 경제지표 캘린더, 기업실적, 이슈 분석)만
WebSearch로 보완하라"는 지시를 넣어두면, 검색 의존도가 11개 자산 전부에서 2개
(한국 쪽 금리 하나, 그리고 phase 2 전까지의 캘린더류)로 줄어듭니다.

## 로컬 테스트

```bash
pip install -r requirements.txt
python -m unittest tests/test_offsets.py -v   # 네트워크 불필요, 로직 검증
python scripts/fetch_prices.py                 # 네트워크 필요, 실제 수집
python scripts/fetch_rates.py
```

> 참고: 이 레포 코드는 Claude Cowork의 클라우드 작업공간(샌드박스) 안에서 작성됐고,
> 그 샌드박스는 조직 네트워크 정책상 pypi.org·fred.stlouisfed.org 같은 일반 호스트로의
> 직접 접속이 막혀 있어 실제 네트워크 호출까지는 그 환경에서 확인하지 못했습니다.
> 오프셋 계산 로직(추석 연휴 처리 등)은 네트워크 없이 도는 단위 테스트로 검증했고,
> 실제 수집은 GitHub Actions(완전한 인터넷 접근)에서 처음 돌릴 때 확인해야 합니다.
