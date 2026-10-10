"""
네트워크 없이 돌아가는 단위 테스트: "거래일 오프셋으로 1주 전/1개월 전을 찾는다"는
핵심 로직이 공휴일(추석 같은 연휴)이 끼어 있어도 올바른 날짜를 집어내는지 검증한다.

실행: python -m pytest tests/ 또는 python tests/test_offsets.py
"""
import sys
import os
import unittest

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from fetch_prices import row_at, pct_change  # noqa: E402


class TestTradingDayOffset(unittest.TestCase):
    def setUp(self):
        # 2026-08-01 ~ 2026-10-02 영업일 캘린더에서 추석 연휴(9/24, 9/25)를 제거해
        # "거래일 기준 오프셋"이 실제 한국 증시 상황과 동일하게 동작하는지 확인한다.
        dates = pd.bdate_range("2026-08-01", "2026-10-02")
        dates = dates[~dates.isin(pd.to_datetime(["2026-09-24", "2026-09-25"]))]
        self.df = pd.DataFrame({"Close": np.arange(len(dates), dtype=float)}, index=dates)

    def test_latest_is_most_recent_trading_day(self):
        latest = row_at(self.df, 0)
        self.assertEqual(latest["date"], "2026-10-02")

    def test_week_ago_skips_chuseok_holiday(self):
        # 달력으로 "1주 전"은 09-25(금, 추석 휴장)이지만, 거래일 기준으로는
        # 09-23(수)이 되어야 한다 - 이번에 사람이 수동으로 계산했던 것과 같은 값.
        week_ago = row_at(self.df, 5)
        self.assertEqual(week_ago["date"], "2026-09-23")

    def test_month_ago_is_approximately_21_trading_days_back(self):
        month_ago = row_at(self.df, 21)
        self.assertEqual(month_ago["date"], "2026-09-01")

    def test_pct_change_basic(self):
        self.assertAlmostEqual(pct_change(110, 100), 10.0)
        self.assertAlmostEqual(pct_change(90, 100), -10.0)

    def test_pct_change_handles_zero_base(self):
        self.assertIsNone(pct_change(100, 0))

    def test_row_at_returns_none_when_out_of_range(self):
        # 히스토리가 짧으면(예: 신규 상장 코인) None을 돌려줘야 한다
        short_df = self.df.iloc[-3:]
        self.assertIsNone(row_at(short_df, 21))


if __name__ == "__main__":
    unittest.main()
