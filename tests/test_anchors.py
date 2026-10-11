"""
v2 달력 앵커 테스트 (네트워크 불필요).
실제 사례: 2026-10-11(일) 실행. 국내는 10/5(개천절 대체공휴일)·10/9(한글날) 휴장으로
지난주 거래일이 10/6~8 사흘뿐. v1은 1주 전을 9/30으로 잡아 오류가 났다.
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from anchors import compute_anchors, week_end_for, minus_one_month  # noqa: E402
from fetch_prices import summarize, usd_return  # noqa: E402
import fetch_rates  # noqa: E402

RUN = date(2026, 10, 11)


def bdays(start, end, holidays=()):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            out.append(d)
        d += timedelta(days=1)
    return out


KR_HOL = {date(2026, 9, 24), date(2026, 9, 25), date(2026, 10, 5), date(2026, 10, 9)}


class TestAnchors(unittest.TestCase):
    def test_anchor_dates(self):
        a = compute_anchors(RUN)
        self.assertEqual(a["week_start"], date(2026, 10, 5))
        self.assertEqual(a["week_end"], date(2026, 10, 9))
        self.assertEqual(a["prev_week_end"], date(2026, 10, 2))
        self.assertEqual(a["month_anchor"], date(2026, 9, 9))

    def test_friday_run_uses_previous_friday(self):
        self.assertEqual(week_end_for(date(2026, 10, 9)), date(2026, 10, 2))

    def test_month_end_clamp(self):
        self.assertEqual(minus_one_month(date(2026, 3, 31)), date(2026, 2, 28))

    def test_kospi_holiday_week(self):
        days = bdays(date(2026, 8, 1), date(2026, 10, 9), KR_HOL)
        rows = [(d, float(i)) for i, d in enumerate(days)]
        s = summarize(rows, compute_anchors(RUN))
        self.assertEqual(s["latest"]["date"], "2026-10-08")
        self.assertEqual(s["week_ago"]["date"], "2026-10-02")   # v1은 09-30이었음
        self.assertEqual(s["month_ago"]["date"], "2026-09-09")
        self.assertEqual(s["week_trading_days"], 3)
        self.assertEqual(s["lag_days"], 1)

    def test_btc_cut_at_friday(self):
        days = [date(2026, 8, 1) + timedelta(days=i) for i in range(72)]  # ~10/11까지 매일
        rows = [(d, 100.0 + i) for i, d in enumerate(days)]
        s = summarize(rows, compute_anchors(RUN))
        self.assertEqual(s["latest"]["date"], "2026-10-09")
        self.assertEqual(s["week_ago"]["date"], "2026-10-02")
        self.assertEqual(s["month_ago"]["date"], "2026-09-09")  # v1은 09-19였음

    def test_usd_return(self):
        a = compute_anchors(RUN)
        eq = [(date(2026, 10, 2), 1000.0), (date(2026, 10, 8), 1100.0)]
        fx = [(date(2026, 10, 2), 1000.0), (date(2026, 10, 8), 1100.0)]
        r = usd_return(eq, fx, a)
        self.assertAlmostEqual(r["pct_1w_usd"], 0.0)

    def test_rates_lag(self):
        rows = [{"date": d.isoformat(), "value": 4.0 + i / 100}
                for i, d in enumerate(bdays(date(2026, 8, 1), date(2026, 10, 8)))]
        s = fetch_rates.summarize(rows, compute_anchors(RUN))
        self.assertEqual(s["latest"]["date"], "2026-10-08")
        self.assertEqual(s["lag_days"], 1)


if __name__ == "__main__":
    unittest.main()
