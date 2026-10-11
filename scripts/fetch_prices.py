"""
주간 브리핑용 시세 수집 (yfinance).

v2: 비교 기준일을 scripts/anchors.py의 달력 앵커로 통일한다.
  latest    = 지난주 금요일 이하 마지막 종가
  week_ago  = 그 전주 금요일 이하 마지막 종가   → pct_1w = 지난주 한 주의 수익률
  month_ago = 지난주 금요일 1개월 전 이하 마지막 종가
휴장일은 '이하 마지막 관측치' 규칙으로 자동 처리되고, 지난주 실제 거래일 수는
week_trading_days 로 따로 남긴다 (예: 추석·한글날 주간은 3).

core  : 브리핑 시장표 10개 자산 (기존 키 그대로 유지 — 하위 호환)
extra : Blogger·티스토리 분석용 (EWY, 필라델피아 반도체, 삼성전자, SK하이닉스, TSMC ADR)
derived: 코스피·코스닥 달러 환산 수익률 (해외 투자자 관점)
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from anchors import compute_anchors, last_on_or_before, count_in_week, run_date_from_env  # noqa: E402

CORE = {
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
EXTRA = {
    "EWY": "EWY",
    "SOX": "^SOX",
    "SAMSUNG": "005930.KS",
    "SKHYNIX": "000660.KS",
    "TSM": "TSM",
}
HISTORY_PERIOD = "6mo"


def pct_change(cur, base):
    if base is None or base == 0:
        return None
    return round((cur - base) / base * 100, 4)


def row_at(df, offset):
    """(v1 호환) 최근 종가로부터 offset 거래일 전 행."""
    n = len(df)
    idx = n - 1 - offset
    if idx < 0:
        return None
    return {"date": df.index[idx].strftime("%Y-%m-%d"), "close": round(float(df.iloc[idx]["Close"]), 6)}


def df_to_rows(df):
    """DataFrame(Close) -> [(date, close)] 오름차순. 인덱스의 거래소 현지 날짜 사용."""
    df = df.sort_index()
    df = df[df["Close"].notna()]
    return [(ts.date(), round(float(c), 6)) for ts, c in zip(df.index, df["Close"])]


def summarize(rows, anchors):
    """rows로부터 latest/week_ago/month_ago와 변동률 계산 (네트워크 없음, 테스트 대상)."""
    out = {}
    for key, target in (("latest", anchors["week_end"]),
                        ("week_ago", anchors["prev_week_end"]),
                        ("month_ago", anchors["month_anchor"])):
        hit = last_on_or_before(rows, target)
        out[key] = {"date": hit[0].isoformat(), "close": hit[1]} if hit else None
    if out["latest"] and out["week_ago"]:
        out["pct_1w"] = pct_change(out["latest"]["close"], out["week_ago"]["close"])
    if out["latest"] and out["month_ago"]:
        out["pct_1m"] = pct_change(out["latest"]["close"], out["month_ago"]["close"])
    out["week_trading_days"] = count_in_week(rows, anchors)
    if out["latest"]:
        from datetime import date
        out["lag_days"] = (anchors["week_end"] - date.fromisoformat(out["latest"]["date"])).days
    return out


def usd_return(eq_rows, fx_rows, anchors):
    """원화 지수의 달러 환산 수익률. 각 기준일의 지수 날짜 이하 마지막 USD/KRW로 환산."""
    res = {}
    pts = {}
    for key, target in (("latest", anchors["week_end"]),
                        ("week_ago", anchors["prev_week_end"]),
                        ("month_ago", anchors["month_anchor"])):
        eq = last_on_or_before(eq_rows, target)
        fx = last_on_or_before(fx_rows, eq[0]) if eq else None
        pts[key] = (eq, fx)
        res[key] = ({"index_date": eq[0].isoformat(), "fx_date": fx[0].isoformat(),
                     "usd_value": round(eq[1] / fx[1], 6)} if eq and fx else None)
    if res["latest"] and res["week_ago"]:
        res["pct_1w_usd"] = pct_change(res["latest"]["usd_value"], res["week_ago"]["usd_value"])
    if res["latest"] and res["month_ago"]:
        res["pct_1m_usd"] = pct_change(res["latest"]["usd_value"], res["month_ago"]["usd_value"])
    return res


def fetch_rows(ticker):
    import yfinance as yf  # 지연 임포트
    df = yf.Ticker(ticker).history(period=HISTORY_PERIOD, interval="1d", auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError("no_data_returned")
    rows = df_to_rows(df)
    if not rows:
        raise RuntimeError("all_close_nan")
    return rows


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "data/latest_prices.json"
    anchors = compute_anchors(run_date_from_env(datetime.now(timezone.utc).date()))

    result = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "v2 calendar anchors: latest<=week_end(Fri), week_ago<=prev Fri, month_ago<=week_end-1month",
        "anchors": {k: v.isoformat() for k, v in anchors.items()},
        "assets": {},
        "extra": {},
        "derived": {},
    }
    errors, rows_cache = [], {}

    for group, table in (("assets", CORE), ("extra", EXTRA)):
        for name, ticker in table.items():
            try:
                rows = fetch_rows(ticker)
                rows_cache[name] = rows
                data = {"name": name, "ticker": ticker, **summarize(rows, anchors)}
            except Exception as e:  # noqa: BLE001
                data = {"name": name, "ticker": ticker, "error": f"{type(e).__name__}: {e}"}
                errors.append(f"{name}({ticker}): {data['error']}")
            result[group][name] = data

    fx = rows_cache.get("USDKRW")
    for name in ("KOSPI", "KOSDAQ", "SAMSUNG", "SKHYNIX"):
        if fx and name in rows_cache:
            result["derived"][f"{name}_USD"] = usd_return(rows_cache[name], fx, anchors)

    result["errors"] = errors
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = len(CORE) + len(EXTRA)
    print(f"Wrote {out_path} ({total - len(errors)}/{total} OK) anchors={result['anchors']}")
    if errors:
        print("ERRORS:", *errors, sep="\n - ", file=sys.stderr)
        core_fail = [e for e in errors if e.split("(")[0] in CORE]
        if len(core_fail) == len(CORE):
            sys.exit(1)


if __name__ == "__main__":
    main()
