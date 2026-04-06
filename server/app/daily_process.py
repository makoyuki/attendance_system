import sqlite3
import csv
import os
import sys
import logging
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DAILY_DIR, LOG_DIR
from app.db import get_connection

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'daily_process.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def get_daily_data(target_date: str):
    """
    指定日の全ユーザーの最初のINと最後のOUTを取得
    target_date: 'YYYY-MM-DD'
    """
    query = """
        SELECT
            u.user_id,
            u.name,
            u.email,
            MIN(CASE WHEN al.log_type = 'IN'  THEN al.log_time END) AS first_in,
            MAX(CASE WHEN al.log_type = 'OUT' THEN al.log_time END) AS last_out
        FROM users u
        LEFT JOIN attendance_logs al
            ON u.felica_id = al.felica_id
            AND DATE(al.log_time) = ?
        GROUP BY u.user_id, u.name, u.email
        HAVING first_in IS NOT NULL OR last_out IS NOT NULL
        ORDER BY u.name
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (target_date,))
        return cur.fetchall()


def calc_work_hours(first_in, last_out):
    """勤務時間計算"""
    if not first_in or not last_out:
        return ''
    try:
        fmt = '%Y-%m-%dT%H:%M:%S.%f' if '.' in first_in else '%Y-%m-%dT%H:%M:%S'
        t_in  = datetime.strptime(first_in[:19],  '%Y-%m-%dT%H:%M:%S')
        t_out = datetime.strptime(last_out[:19], '%Y-%m-%dT%H:%M:%S')
        diff  = t_out - t_in
        hours = diff.total_seconds() / 3600
        return f"{hours:.2f}"
    except Exception:
        return ''


def format_time(dt_str):
    """datetime文字列をHH:MM形式に変換"""
    if not dt_str:
        return ''
    try:
        return datetime.strptime(dt_str[:19], '%Y-%m-%dT%H:%M:%S').strftime('%H:%M')
    except Exception:
        return ''


def create_daily_csv(target_date: str):
    """日次CSVファイル作成"""
    records = get_daily_data(target_date)

    if not records:
        logging.info(f"No records for {target_date}")
        return []

    created_files = []

    for record in records:
        user_id   = record['user_id']
        name      = record['name']
        email     = record['email']
        first_in  = record['first_in']
        last_out  = record['last_out']
        work_hours = calc_work_hours(first_in, last_out)

        # ユーザー別ディレクトリ作成
        user_dir = os.path.join(OUTPUT_DAILY_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

        csv_path = os.path.join(user_dir, f"{target_date}.csv")

        # 既存ファイルがあれば追記、なければ新規作成
        file_exists = os.path.exists(csv_path)

        with open(csv_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['日付', '氏名', '出社時刻', '退社時刻', '勤務時間'])
            writer.writerow([
                target_date,
                name,
                format_time(first_in),
                format_time(last_out),
                work_hours
            ])

        created_files.append({'user_id': user_id, 'name': name, 'email': email, 'file': csv_path})
        logging.info(f"Daily CSV created: {name} - {csv_path}")

    return created_files


def run_daily_process(target_date=None):
    """日次処理実行"""
    if target_date is None:
        # デフォルトは前日
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    logging.info(f"日次処理開始: {target_date}")
    files = create_daily_csv(target_date)
    logging.info(f"日次処理完了: {len(files)}件")

    return files


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='日次勤怠処理')
    parser.add_argument('--date', help='処理対象日 (YYYY-MM-DD)', default=None)
    args = parser.parse_args()

    run_daily_process(args.date)
