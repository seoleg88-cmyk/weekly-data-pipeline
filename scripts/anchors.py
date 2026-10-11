"""
주간 브리핑의 '비교 기준일'을 한 곳에서 정의한다 (가격·금리 공통).

v1은 "최근 종가에서 5거래일 전 = 1주 전" 방식이었는데, 휴장이 낀 주에는
1주 변동이 지난주가 아닌 기간을 섞어버렸다 (예: 2026-10 둘째 주 코스피는
10/5 대체공휴일·10/9 한글날로 3거래일뿐인데, 5거래일 전인 9/30이 기준이 되어
10/1~2 하락분까지 '지난주 -3.10%'에 섞임).

v2 정의 (모든 자산 동일):
- week_end      = 실행일 직전의 금요일 (실행일이 금요일이면 그 전 금요일)
- prev_week_end = week_end - 7일
- month_anchor  = week_end - 1개월(같은 날짜)
- latest    = week_end 이하 마지막 관측치
- week_ago  = prev_week_end 이하 마지막 관측치  → 1주 변동 = '지난주 한 주의 수익률'
- month_ago = month_anchor 이하 마지막 관측치
비트코인처럼 주말에도 거래되는 자산도 같은 기준(금요일)으로 잘라 기간을 통일한다.
"""
from datetime import date, timedelta
import calendar


def week_end_for(run_date: date) -> date:
    offset = (run_date.weekday() - 4) % 7  # Fri=4
    if offset == 0:
        offset = 7
    return run_date - timedelta(days=offset)


def minus_one_month(d: date) -> date:
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def compute_anchors(run_date: date) -> dict:
    we = week_end_for(run_date)
    return {
        "week_start": we - timedelta(days=4),
        "week_end": we,
        "prev_week_end": we - timedelta(days=7),
        "month_anchor": minus_one_month(we),
    }


def last_on_or_before(rows, target: date):
    """rows: [(date, value), ...] 오름차순. target 이하 마지막 항목, 없으면 None."""
    found = None
    for d, v in rows:
        if d <= target:
            found = (d, v)
        else:
            break
    return found


def count_in_week(rows, anchors) -> int:
    """지난주(월~금) 안에 실제로 관측치가 있는 날 수 = 거래일 수."""
    return sum(1 for d, _ in rows if anchors["prev_week_end"] < d <= anchors["week_end"])


def run_date_from_env(today: date) -> date:
    """ASOF=YYYY-MM-DD 환경변수로 실행일을 덮어쓸 수 있다 (재생성·테스트용)."""
    import os
    v = os.environ.get("ASOF")
    return date.fromisoformat(v) if v else today
