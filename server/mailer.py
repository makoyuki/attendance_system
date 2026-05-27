#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mailer.py
Gmail 経由で CSV レポートをメール送信する
"""

import smtplib
import logging
import os
import sys
from urllib.parse import quote                          # ← 追加
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, \
                   MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM

log = logging.getLogger(__name__)


def send_csv_report(
    recipients:   list,
    subject:      str,
    body:         str,
    csv_content:  str,
    csv_filename: str,
) -> bool:
    """
    CSV をメール添付で送信する

    Args:
        recipients:   送信先アドレスリスト ['a@b.com', ...]
        subject:      件名
        body:         本文
        csv_content:  CSV 文字列（BOM なし）
        csv_filename: 添付ファイル名

    Returns:
        True = 成功 / False = 失敗
    """
    if not recipients:
        log.warning("送信先アドレスが未設定")
        return False

    try:
        msg            = MIMEMultipart()
        msg['From']    = MAIL_FROM
        msg['To']      = ', '.join(recipients)
        msg['Subject'] = subject

        # 本文
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # CSV 添付（BOM 付き UTF-8 → Excel で文字化けしない）
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(('\ufeff' + csv_content).encode('utf-8'))
        encoders.encode_base64(part)

        # 日本語ファイル名を RFC 2231 形式でエンコード ← 修正
        encoded_filename = quote(csv_filename, encoding='utf-8')
        part.add_header(
            'Content-Disposition',
            f"attachment; filename*=UTF-8''{encoded_filename}"
        )
        part.add_header(
            'Content-Type',
            'text/csv',
            name=csv_filename                          # ASCII以外はfallback用
        )
        msg.attach(part)

        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15) as server:
            if MAIL_USE_TLS:
                server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM, recipients, msg.as_bytes())

        log.info(f"メール送信成功: {recipients} / {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error("Gmail 認証エラー: アプリパスワードを確認してください")
        return False
    except Exception as e:
        log.error(f"メール送信エラー: {e}")
        return False
