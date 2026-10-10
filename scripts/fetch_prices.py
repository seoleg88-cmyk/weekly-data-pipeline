"""
주간 브리핑용 시세 데이터 수집 스크립트.

11개 자산 중 야후 파이낸스(yfinance)로 받을 수 있는 9개를 받는다.
(미국 10년물/2년물 국채금리는 fetch_rates.py에서 FRED로 따로 받는다.)

핵심 설계: "1주 전", "1개월 전"을 달력 날짜가 아니라 실제 거래일 인덱스로 찾는다.
야후 파이낸스가 돌려주는 일봉 히스토리는 그 시장의 실제 휴장일(추석, 성탄절 등)이
이미 빠진 상태이므로, 뒤에서 N번째 행을 그냥 집으면 자동으로 "직전 거래일 기준
실제 1주 전/1개월 전"이 된다. 사람이 "이번주는 추석 연휴라 9/23을 써야 한다"를
수동으로 계산할 필요가 없다.

출력: JSON (지정한 경로, 기본 data/latest.json)
각 자산마다 latest/week_ago/month_ago의 날짜+종가와, 1주/1개월 변동률(%)을 포함한다.
데이터를 못 가져온 자산은 "error" 필드에 이유를 남기고 스크립트는 계속 진행한다
(한 티커 실패가 전체를 중단시키지 않도록).
"""
import json
import sys
from datetime import datetime, timezone

# yfinance는 fetch_one() 안에서 지연 임포트한다 (단위 테스트가 네트워크 패키지
# 설치 없이도 row_at/pct_change 같은 순수 로직만 돌릴 수 있도록).

# 자산명 -> 야후 파이낸스 티커
TICKERS = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOW": "^DJI",
    "USDKRW": "KRW=X",
    "WTI": "CL=F",
    "BRENT": "BZ=F",
    "GOLD": "GC=F",
    "BTC-USD": "BTC-USD",
}

# 1주 = 5 거래일 전, 1개월 = 21 거래일 전 (관례적 거래일수 근사)
WEEK_OFFSET = 5
MONTH_OFFSET = 21

# 히스토리를 넉넉히 받아야 21거래일 전 + 휴장일 버퍼가 항상 확보된다
HISTORY_PERIOD = "6mo"


def pct_change(cur, base):
    if base is None or base == 0:
        return None
    return round((cur - base) / base * 100, 4)


def row_at(df, offset):
    """최근 종가로부터 offset 거래일 전 행을 돌려준다. 데이터 부족하면 None."""
    n = len(df)
    idx = n - 1 - offset
    if idx < 0:
        return None
    row = df.iloc[idx]
    return {
        "date": df.index[idx].strftime("%Y-%m-%d"),
        "close": round(float(row["Close"]), 6),
    }


def fetch_one(name, ticker):
    import yfinance as yf  # 지연 임포트: 순수 로직 테스트는 이 줄에 닿지 않는다

    df = yf.Ticker(ticker).history(period=HISTORY_PERIOD, interval="1d", auto_adjust=False)
    if df is None or df.empty:
        return {"name": name, "ticker": ticker, "error": "no_data_returned"}

    df = df.sort_index()
    df = df[df["Close"].notna()]
    if df.empty:
        return {"name": name, "ticker": ticker, "error": "all_close_nan"}

    latest = row_at(df, 0)
    week_ago = row_at(df, WEEK_OFFSET)
    month_ago = row_at(df, MONTH_OFFSET)

    out = {
        "name": name,
        "ticker": ticker,
        "latest": latest,
        "week_ago": week_ago,
        "month_ago": month_ago,
    }
    if latest and week_ago:
        out["pct_1w"] = pct_change(latest["close"], week_ago["close"])
    if latest and month_ago:
        out["pct_1m"] = pct_change(latest["close"], month_ago["close"])
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "data/latest_prices.json"

    result = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "yfinance daily history, trading-day offset (1wk=5 trading days, 1mo=21 trading days)",
        "assets": {},
    }
    errors = []

    for name, ticker in TICKERS.items():
        try:
            data = fetch_one(name, ticker)
        except Exception as e:  # noqa: BLE001 - 한 티커 실패해도 나머지는 계속
            data = {"name": name, "ticker": ticker, "error": f"{type(e).__name__}: {e}"}
        result["assets"][name] = data
        if "error" in data:
            errors.append(f"{name}({ticker}): {data['error']}")

    result["errors"] = errors

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path} ({len(TICKERS) - len(errors)}/{len(TICKERS)} assets OK)")
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        # 일부 실패는 있어도 전체를 실패로 처리하지 않는다 (나머지 데이터는 유효하므로).
        # 전부 실패했을 때만 비정상 종료 코드를 준다.
        if len(errors) == len(TICKERS):
            sys.exit(1)


if __name__ == "__main__":
    main()
