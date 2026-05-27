#!/usr/bin/env python3
"""
notifier.py  -  勤怠通知の共通ロジック
app/admin.py および cron/send_notification.py から共有して使用
"""
import io
import csv
import sqlite3
import calendar
from datetime import date, timedelta, datetime
from typing import List, Dict, Tuple

from config import DB_PATH, DEFAULT_CUTOFF_DAY
from processor import process, fetch_logs, _hm, Session
from mailer import send_csv_report


# ─────────────────────────────────────────
# DB ユーティリティ
# ─────────────────────────────────────────

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_notification_settings():
    db = _get_db()
    row = db.execute('SELECT * FROM notification_settings WHERE id=1').fetchone()
    db.close()
    return dict(row) if row else None


def get_all_users() -> List[dict]:
    db = _get_db()
    rows = db.execute(
        'SELECT felica_id, name, email FROM users WHERE is_active=1 ORDER BY name'
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_users_with_email() -> List[dict]:
    db = _get_db()
    rows = db.execute(
        "SELECT felica_id, name, email FROM users "
        "WHERE email IS NOT NULL AND email != '' AND is_active=1 ORDER BY name"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────
# セッション取得
# ─────────────────────────────────────────

def _get_sessions(felica_id: str, start: date, end: date) -> Dict[date, List]:
    """felica_id の sessions_by_date を返す"""
    conn = _get_db()
    logs = fetch_logs(conn, felica_id, start, end)
    conn.close()
    return process(logs, felica_id)


# ─────────────────────────────────────────
# 異常検知
# ─────────────────────────────────────────

def detect_anomalies(sessions_by_date: Dict[date, List]) -> List[str]:
    """
    sessions_by_date から異常を検知してメッセージリストを返す

    検知内容:
      - 退室打刻なし
      - 日付をまたいで強制退室（out_time が 00:00）
      - 12時間超の長時間勤務
      - 30分未満の短時間打刻
    """
    messages = []
    for d in sorted(sessions_by_date.keys()):
        for s in sessions_by_date[d]:
            # 退室打刻なし
            if s.in_time and not s.out_time:
                messages.append(
                    f'{d.strftime("%Y/%m/%d")} : 退室打刻なし'
                )
                continue

            if s.in_time and s.out_time:
                mins = _calc_duration_min(s.in_time, s.out_time)

                # 24:00 強制OUT（out_time が 00:00）
                if s.out_time.hour == 0 and s.out_time.minute == 0:
                    messages.append(
                        f'{d.strftime("%Y/%m/%d")} : '
                        f'退室打刻漏れの可能性（日付をまたいで強制退室）'
                    )
                # 12時間超
                elif mins > 720:
                    messages.append(
                        f'{d.strftime("%Y/%m/%d")} : '
                        f'長時間勤務（{mins // 60}時間{mins % 60}分）要確認'
                    )
                # 30分未満（0は除く）
                elif 0 < mins < 30:
                    messages.append(
                        f'{d.strftime("%Y/%m/%d")} : '
                        f'短時間打刻（{mins}分）要確認'
                    )
    return messages


# ─────────────────────────────────────────
# CSV 生成
# ─────────────────────────────────────────

def _calc_duration_min(in_t, out_t) -> int:
    """in_time / out_time が datetime でも time でも対応"""
    try:
        return max(0, int((out_t - in_t).total_seconds() / 60))
    except TypeError:
        d = date.today()
        dt_in  = datetime.combine(d, in_t)
        dt_out = datetime.combine(d, out_t)
        return max(0, int((dt_out - dt_in).total_seconds() / 60))


def _sessions_to_csv(
    sessions_by_date: Dict[date, List],
    start: date,
    end: date,
) -> str:
    """sessions_by_date → CSV文字列（CSV生成と異常検知で共用するため分離）"""
    max_sessions = max(
        (len(v) for v in sessions_by_date.values()),
        default=1,
    )
    max_sessions = max(max_sessions, 1)

    header = ['日付']
    for i in range(1, max_sessions + 1):
        header += [f'IN{i}', f'OUT{i}']
    header += ['合計(h:m)', '合計(分)']

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)

    current = start
    while current <= end:
        sessions = sessions_by_date.get(current, [])
        row = [current.strftime('%Y/%m/%d')]
        total_min = 0

        for s in sessions:
            in_str  = s.in_time.strftime('%H:%M')  if s.in_time  else ''
            out_str = s.out_time.strftime('%H:%M') if s.out_time else ''
            row.extend([in_str, out_str])
            if s.in_time and s.out_time:
                total_min += _calc_duration_min(s.in_time, s.out_time)

        while len(row) < 1 + max_sessions * 2:
            row.append('')

        row.append(_hm(total_min))
        row.append(str(total_min))
        writer.writerow(row)
        current += timedelta(days=1)

    return output.getvalue()


def build_user_csv(felica_id: str, name: str, start: date, end: date) -> str:
    """1ユーザー分の CSV 文字列を生成"""
    sessions_by_date = _get_sessions(felica_id, start, end)
    return _sessions_to_csv(sessions_by_date, start, end)


def build_combined_csv(start: date, end: date) -> str:
    """全ユーザー分を結合した CSV 文字列を生成"""
    users = get_all_users()
    output = io.StringIO()
    writer = csv.writer(output)

    for user in users:
        writer.writerow([f'■ {user["name"]}'])
        user_csv = build_user_csv(user['felica_id'], user['name'], start, end)
        for line in csv.reader(io.StringIO(user_csv)):
            writer.writerow(line)
        writer.writerow([])

    return output.getvalue()


# ─────────────────────────────────────────
# メール本文生成
# ─────────────────────────────────────────

def _build_individual_body(
    name: str,
    start: date,
    end: date,
    period_label: str,
    anomalies: List[str],
) -> str:
    """個別送付用メール本文を生成（異常がある場合は冒頭に警告）"""

    if anomalies:
        # 異常あり → 冒頭に警告
        body  = f'{name} さん\n\n'
        body += '=' * 44 + '\n'
        body += '⚠️  打刻異常が検出されました\n'
        body += '=' * 44 + '\n'
        for a in anomalies:
            body += f'  ・{a}\n'
        body += '=' * 44 + '\n'
        body += '\n上記の日付について、打刻内容をご確認ください。\n'
        body += '不明な点は管理者までご連絡ください。\n'
        body += '\n' + '-' * 44 + '\n'
        body += f'{period_label}の勤怠レポートをお送りします。\n'
        body += f'期間: {start} 〜 {end}\n'
    else:
        # 異常なし → 通常の本文
        body  = f'{name} さん\n\n'
        body += f'{period_label}の勤怠レポートをお送りします。\n'
        body += f'期間: {start} 〜 {end}\n\n'
        body += '異常は検出されませんでした。\n'

    body += '\n※ 詳細は添付のCSVファイルをご確認ください。\n'
    return body


# ─────────────────────────────────────────
# 送信関数
# ─────────────────────────────────────────

def send_admin_report(
    start: date,
    end: date,
    period_label: str,
    recipients: List[str],
) -> bool:
    """管理者宛に全ユーザー分まとめた CSV を送付"""
    try:
        csv_content = build_combined_csv(start, end)
        filename = (
            f'attendance_{start.strftime("%Y%m%d")}_{end.strftime("%Y%m%d")}.csv'
        )
        subject = f'【勤怠レポート】{period_label}（{start}〜{end}）'
        body    = f'{period_label}の勤怠レポートをお送りします。\n期間: {start} 〜 {end}'
        send_csv_report(recipients, subject, body, csv_content, filename)
        print(f'[管理者宛] 送付完了 → {recipients}')
        return True
    except Exception as e:
        print(f'[ERROR] 管理者宛送付失敗: {e}')
        return False


def send_individual_reports(
    start: date,
    end: date,
    period_label: str,
) -> Tuple[int, int]:
    """各ユーザーに個別 CSV を送付（異常情報をメール本文に含む）
    Returns: (success_count, fail_count)
    """
    users = get_users_with_email()
    if not users:
        print('[個別送付] メールアドレス登録ユーザーなし')
        return 0, 0

    success, fail = 0, 0
    for user in users:
        try:
            # セッション取得（CSV生成・異常検知で共用）
            sessions_by_date = _get_sessions(user['felica_id'], start, end)

            # CSV生成
            csv_content = _sessions_to_csv(sessions_by_date, start, end)

            # 異常検知
            anomalies = detect_anomalies(sessions_by_date)

            # 件名（異常あり/なしで変える）
            if anomalies:
                subject = (
                    f'【勤怠レポート ⚠️打刻確認あり】{user["name"]}さんの'
                    f'{period_label}（{start}〜{end}）'
                )
            else:
                subject = (
                    f'【勤怠レポート】{user["name"]}さんの'
                    f'{period_label}（{start}〜{end}）'
                )

            # メール本文生成
            body = _build_individual_body(
                user['name'], start, end, period_label, anomalies
            )

            filename = (
                f'{user["name"]}_'
                f'{start.strftime("%Y%m%d")}_{end.strftime("%Y%m%d")}.csv'
            )

            send_csv_report([user['email']], subject, body, csv_content, filename)
            success += 1
            note = f'（異常{len(anomalies)}件）' if anomalies else ''
            print(f'[個別送付] {user["name"]} → {user["email"]} 完了{note}')

        except Exception as e:
            fail += 1
            print(f'[ERROR] {user["name"]} ({user["email"]}) 送付失敗: {e}')

    return success, fail


# ─────────────────────────────────────────
# 日付ヘルパー
# ─────────────────────────────────────────

def get_prev_week_range() -> Tuple[date, date]:
    """前週の月曜〜日曜を返す"""
    today       = date.today()
    this_monday = today - timedelta(days=today.weekday())
    end         = this_monday - timedelta(days=1)   # 先週日曜
    start       = end - timedelta(days=6)            # 先週月曜
    return start, end


def get_prev_month_range() -> Tuple[date, date]:
    """直近の締め切り済み期間を返す（DEFAULT_CUTOFF_DAY基準）"""
    today  = date.today()
    cutoff = DEFAULT_CUTOFF_DAY

    this_last   = calendar.monthrange(today.year, today.month)[1]
    this_cutoff = min(cutoff, this_last)

    if today.day > this_cutoff:
        # 今月の締め日を過ぎている → 今月が直近の締め切り済み期間
        end = date(today.year, today.month, this_cutoff)
        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1
        prev_last = calendar.monthrange(prev_year, prev_month)[1]
        start = date(prev_year, prev_month, min(cutoff + 1, prev_last))
    else:
        # 今月の締め日前 → 前月が直近の締め切り済み期間
        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1
        prev_last = calendar.monthrange(prev_year, prev_month)[1]
        end = date(prev_year, prev_month, min(cutoff, prev_last))
        if prev_month == 1:
            pp_year, pp_month = prev_year - 1, 12
        else:
            pp_year, pp_month = prev_year, prev_month - 1
        pp_last = calendar.monthrange(pp_year, pp_month)[1]
        start = date(pp_year, pp_month, min(cutoff + 1, pp_last))

    return start, end

