#!/usr/bin/env python3
"""
cron/send_notification.py
定期メール通知（crontab から呼び出す）
"""
import sys
import os
import calendar
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

from config import DEFAULT_CUTOFF_DAY
from notifier import (
    get_notification_settings,
    send_admin_report,
    send_individual_reports,
    get_prev_week_range,
)


def run_daily(settings):
    yesterday  = date.today() - timedelta(days=1)
    recipients = [e.strip() for e in settings.get('recipient_emails', '').split(',') if e.strip()]

    # 管理者宛 日次
    if settings.get('notify_daily') and recipients:
        send_admin_report(yesterday, yesterday, '日次', recipients)

    # 個別 日次
    if settings.get('notify_individual_daily'):
        send_individual_reports(yesterday, yesterday, '日次')


def run_weekly(settings):
    today = date.today()
    if today.weekday() != 0:   # 月曜のみ実行
        return

    start, end = get_prev_week_range()
    recipients = [e.strip() for e in settings.get('recipient_emails', '').split(',') if e.strip()]

    # 管理者宛 週次
    if settings.get('notify_weekly') and recipients:
        send_admin_report(start, end, '週次', recipients)

    # 個別 週次
    if settings.get('notify_individual_weekly'):
        send_individual_reports(start, end, '週次')


def run_monthly(settings):
    today  = date.today()
    cutoff = DEFAULT_CUTOFF_DAY
    last   = calendar.monthrange(today.year, today.month)[1]

    # 締め日翌日かどうか確認
    next_day = 1 if cutoff >= last else cutoff + 1
    if today.day != next_day:
        return

    # 期間: 前月締め日翌日 〜 今月締め日
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    prev_last = calendar.monthrange(prev_year, prev_month)[1]
    start = date(prev_year, prev_month, min(cutoff + 1, prev_last))
    end   = date(today.year, today.month, min(cutoff, last))

    recipients = [e.strip() for e in settings.get('recipient_emails', '').split(',') if e.strip()]

    # 管理者宛 月次
    if settings.get('notify_monthly') and recipients:
        send_admin_report(start, end, '月次', recipients)

    # 個別 月次
    if settings.get('notify_individual_monthly'):
        send_individual_reports(start, end, '月次')


def main():
    print(f'[{date.today()}] send_notification.py 開始')
    settings = get_notification_settings()
    if settings is None:
        print('notification_settings が未設定です')
        sys.exit(1)

    run_daily(settings)
    run_weekly(settings)
    run_monthly(settings)
    print(f'[{date.today()}] send_notification.py 完了')


if __name__ == '__main__':
    main()
