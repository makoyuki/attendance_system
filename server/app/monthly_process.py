import sqlite3
import csv
import os
import sys
import logging
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_MONTHLY_DIR, LOG_DIR, DEFAULT_CUTOFF_DAY
from app.db import get_connection

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'monthly_process.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def get_target_period(cutoff_day: int, base_date: datetime = None):
    """
    締め日基準で対象期間を計算
    例: 20日締めの場合
      - 実行日が21日以降 → 当月21日〜翌月20日
      - 実行日が20日以前 → 前月21日〜当月20日
    """
    if base_date is None:
        base_date = datetime.now()

    if base_date.day > cutoff_day:
        # 締め日を過ぎている → 今月締め日の翌日〜来月締め日
        start_date = base_date.replace(day=cutoff_day + 1)
        if base_date.month == 12:
            end_date = datetime(base_date.year + 1, 1, cutoff_day)
        else:
            end_date = datetime(base_date.year, base_date.month + 1, cutoff_day)
    else:
        # 締め日以前 → 先月締め日の翌日〜今月締め日
        if base_date.month == 1:
            start_date = datetime(base_date.year - 1, 12, cutoff_day + 1)
        else:
            start_date = datetime(base_date.year, base_date.month - 1, cutoff_day + 1)
        end_date = base_date.replace(day=cutoff_day)

    return start_date.date(), end_date.date()


def get_monthly_data(user_id: int, start_date, end_date):
    """指定期間のユーザー勤怠データ取得"""
    query = """
        SELECT
