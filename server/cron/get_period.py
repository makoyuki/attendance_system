# -*- coding: utf-8 -*-
"""
get_period.py
config.py の DEFAULT_CUTOFF_DAY を読んで集計期間を計算する

使い方:
  python get_period.py          → "START END" を出力
                                   例: 2026-03-21 2026-04-20
  python get_period.py --check  → 今日が実行日なら 1、違えば 0 を出力
"""

import sys
import os
import argparse
from datetime import date

sys.path.append('/home/makoyuki/attendance')
from config import DEFAULT_CUTOFF_DAY


def get_period(cutoff: int, today: date):
    """
    締め日から集計期間（start, end）を計算する

    例: cutoff=20, today=2026-04-21
      end   = 2026-04-20  （当月締め日）
      start = 2026-03-21  （前月締め日の翌日）
    """
    # 当月の締め日
    end_date = today.replace(day=cutoff)

    # 前月の締め日翌日
    if end_date.month == 1:
        start_date = date(end_date.year - 1, 12, cutoff + 1)
    else:
        start_date = date(end_date.year, end_date.month - 1, cutoff + 1)

    return start_date, end_date


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        '--check',
        action='store_true',
        help='今日が実行日（締め日翌日）かチェック。1=実行日, 0=非実行日'
    )
    args = p.parse_args()

    today  = date.today()
    cutoff = DEFAULT_CUTOFF_DAY

    if args.check:
        # 締め日の翌日が実行日
        # ※ 月末締め(28〜31日)の場合は翌月1日を実行日とする
        if cutoff >= 28:
            # 翌月1日かどうか
            is_run_day = (today.day == 1)
        else:
            is_run_day = (today.day == cutoff + 1)

        print(1 if is_run_day else 0)
        return

    # 期間を出力
    start, end = get_period(cutoff, today)
    print(f"{start} {end}")


if __name__ == '__main__':
    main()
