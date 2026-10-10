"""
미국 국채금리 / 연준 기준금리 수집 스크립트.

세인트루이스 연은 FRED에는 API 키 없이도 쓸 수 있는 공개 CSV 다운로드
엔드포인트가 있다 (https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID).
API 키가 있으면 더 유연한 JSON API(api.stlouisfed.org)를 쓸 수 있지만,
지금 단계(키 미발급)에서는 이 CSV 엔드포인트만으로 아래 4개 시리즈를 받는다.

- DGS10 : 10년 만기 국채 수익률 (daily, constant maturity)
- DGS2  : 2년 만기 국채 수익률 (daily, constant maturity)
- DFEDTARU : 연방기금 목표금리 상단
- DFEDTARL : 연방기금 목표금리 하단

한국은행 기준금리는 ECOS Open API 키가 있어야 안정적으로 받을 수 있어
이번 단계에서는 제외했다 (fetch_rates.py에 TODO로 남겨둠, README 참고).

국채 수익률도 가격 자산과 동일하게 "1주 전 = 5영업일 전, 1개월 전 = 21영업일 전"
오프셋 방식을 쓴다. 공휴일에는 값이 "."로 비어 있으므로 제거 후 인덱싱한다.
금리는 %p(퍼센트포인트) 차이로 변동폭을 계산한다 (퍼센트 변동률이 아님).
"""
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

SERIES = {
    "UST10Y": "DGS10",
    "UST2Y": "DGS2",
    "FED_TARGET_UPPER": "DFEDTARU",
    "FED_TARGET_LOWER": "DFEDTARL",
}

WEEK_OFFSET = 5
MONTH_OFFSET = 21
LOOKBACK_DAYS = 200  # 넉넉히 6개월 넘게 받아서 21영업일+공휴일 버퍼 확보


def fetch_series(series_id):
    end = datetime.utcnow().date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    params = {
        "id": series_id,
        "cosd": start.isoformat(),
        "coed": end.isoformat(),
    }
    resp = requests.get(FRED_CSV_URL, params=params, timeout=20)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []
    for row in reader:
        date_key = "DATE" if "DATE" in row else "observation_date"
        val = row.get(series_id) or row.get("value")
        if val is None or val == "." or val == "":
            continue  # 공휴일/결측
        try:
            rows.append({"date": row[date_key], "value": float(val)})
        except (ValueError, KeyError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows


def row_at(rows, offset):
    n = len(rows)
    idx = n - 1 - offset
    if idx < 0:
        return None
    return rows[idx]


def pp_change(cur, base):
    if cur is None or base is None:
        return None
    return round(cur - base, 4)


def fetch_one(name, series_id):
    rows = fetch_series(series_id)
    if not rows:
        return {"name": name, "series_id": series_id, "error": "no_data_returned"}

    latest = row_at(rows, 0)
    week_ago = row_at(rows, WEEK_OFFSET)
    month_ago = row_at(rows, MONTH_OFFSET)

    out = {
        "name": name,
        "series_id": series_id,
        "latest": latest,
        "week_ago": week_ago,
        "month_ago": month_ago,
    }
    if latest and week_ago:
        out["pp_1w"] = pp_change(latest["value"], week_ago["value"])
    if latest and month_ago:
        out["pp_1m"] = pp_change(latest["value"], month_ago["value"])
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "data/latest_rates.json"

    result = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Federal Reserve Bank of St. Louis (FRED), keyless CSV endpoint",
        "note": "한국은행 기준금리는 ECOS API 키 발급 후 phase 2에서 추가 예정",
        "series": {},
    }
    errors = []

    for name, series_id in SERIES.items():
        try:
            data = fetch_one(name, series_id)
        except Exception as e:  # noqa: BLE001
            data = {"name": name, "series_id": series_id, "error": f"{type(e).__name__}: {e}"}
        result["series"][name] = data
        if "error" in data:
            errors.append(f"{name}({series_id}): {data['error']}")

    result["errors"] = errors

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path} ({len(SERIES) - len(errors)}/{len(SERIES)} series OK)")
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        if len(errors) == len(SERIES):
            sys.exit(1)


if __name__ == "__main__":
    main()
