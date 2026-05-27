# app/db.py
import sqlite3
import logging
import os
import sys

# 親ディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH

def get_connection():
    """DB接続取得"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能にする
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_db():
    """DBの初期化・テーブル作成"""
    with get_connection() as conn:
        cur = conn.cursor()

        # ユーザーマスター
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                felica_id VARCHAR(16) UNIQUE NOT NULL,
                name      VARCHAR(100) NOT NULL,
                email     VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 入退室ログ
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                felica_id   VARCHAR(16) NOT NULL,
                log_type    VARCHAR(3)  NOT NULL,
                log_time    DATETIME    NOT NULL,
                terminal_id VARCHAR(20) NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (felica_id) REFERENCES users(felica_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS notification_settings (
                id               INTEGER PRIMARY KEY CHECK(id=1),
                notify_daily     INTEGER DEFAULT 0,
                notify_weekly    INTEGER DEFAULT 1,
                notify_monthly   INTEGER DEFAULT 0,
                recipient_emails TEXT    DEFAULT '',
                updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # デフォルト行（週次ONで初期化）
        cur.execute(
            "INSERT OR IGNORE INTO notification_settings "
            "(id, notify_daily, notify_weekly, notify_monthly, recipient_emails) "
            "VALUES (1, 0, 1, 0, '')"
        )

        conn.commit()
        logging.info("Database initialized")


if __name__ == '__main__':
    initialize_db()
    print("✓ データベース初期化完了")
