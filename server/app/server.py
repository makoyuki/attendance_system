from flask import Flask, request, jsonify
from functools import wraps
import sqlite3
import logging
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LOG_DIR, API_KEY
from app.db import get_connection, initialize_db

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'server.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

app = Flask(__name__, template_folder='../templates')
app.secret_key = 'your-secret-key-here'
app.json.ensure_ascii = False
from datetime import timedelta

# DB初期化
initialize_db()


# ========================
# APIキー認証デコレータ
# ========================
def check_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            logging.warning(f"API key missing - IP: {request.remote_addr}")
            return jsonify({'status': 'error', 'message': 'APIキーがありません'}), 401
        if api_key != API_KEY:
            logging.warning(f"Invalid API key - IP: {request.remote_addr}")
            return jsonify({'status': 'error', 'message': 'APIキーが無効です'}), 401
        return f(*args, **kwargs)
    return decorated


# ========================
# 挨拶文の生成
# ========================
def get_greeting(log_type):
    """時間帯・ログタイプに応じた挨拶を返す"""
    hour = datetime.now().hour
    if log_type == 'IN':
        if 4 <= hour < 12:
            return 'おはようございます'
        elif 12 <= hour < 18:
            return 'こんにちは'
        else:
            return 'こんばんは'
    else:  # OUT
        return 'おつかれさまでした'


# ========================
# 入退室ログ記録API
# ========================
@app.route('/api/log', methods=['POST'])
@check_api_key
def log_attendance():
    try:
        data = request.json

        # 必須フィールド確認
        required_fields = ['felica_id', 'log_type', 'timestamp', 'terminal_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'{field}が不足しています'}), 400

        with get_connection() as conn:
            cur = conn.cursor()

            # ユーザー存在確認
            cur.execute(
                "SELECT user_id, name, is_active FROM users WHERE felica_id = ?",
                (data['felica_id'],)
            )
            user = cur.fetchone()

            if not user:
                logging.warning(f"Unregistered card: {data['felica_id']}")
                return jsonify({
                    'status': 'error',
                    'message': '未登録のカードです'
                }), 404
            if not user['is_active']:
                logging.warning(f"Disabled user card: {data['felica_id']}")
                return jsonify({
                    'status': 'error',
                    'message': '無効化されたユーザーです'
                }), 403

            # ログ記録
            cur.execute("""
                INSERT INTO attendance_logs (felica_id, log_type, log_time, terminal_id)
                VALUES (?, ?, ?, ?)
            """, (
                data['felica_id'],
                data['log_type'],
                data['timestamp'],
                data['terminal_id']
            ))
            conn.commit()

        greeting = get_greeting(data['log_type'])
        logging.info(f"Log recorded - {data['log_type']}: {data['felica_id']} ({user[1]})")

        # ★ 名前・挨拶をレスポンスに追加
        return jsonify({
            'status': 'success',
            'employee_name': user[1],
            'greeting': greeting,
            'log_type': data['log_type']
        })

    except Exception as e:
        logging.error(f"Log error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# server.py に追記
# ========================
# カード登録API
# ========================
@app.route('/api/register', methods=['POST'])
@check_api_key
def register_card():
    try:
        data = request.json

        # 必須フィールド確認
        if 'felica_id' not in data or 'name' not in data:
            return jsonify({
                'status': 'error',
                'message': 'felica_id と name は必須です'
            }), 400

        felica_id = data['felica_id'].strip()
        name      = data['name'].strip()
        email     = data.get('email', '').strip()

        if not felica_id or not name:
            return jsonify({
                'status': 'error',
                'message': 'felica_id と name は空にできません'
            }), 400

        with get_connection() as conn:
            cur = conn.cursor()

            # 重複チェック
            cur.execute(
                "SELECT user_id, name FROM users WHERE felica_id = ?",
                (felica_id,)
            )
            existing = cur.fetchone()
            if existing:
                return jsonify({
                    'status': 'error',
                    'message': f'このカードは既に登録済みです（{existing["name"]}）'
                }), 409

            # 登録
            cur.execute(
                "INSERT INTO users (felica_id, name, email) VALUES (?, ?, ?)",
                (felica_id, name, email)
            )
            conn.commit()

        logging.info(f"新規登録: {name} ({felica_id})")
        return jsonify({
            'status':  'success',
            'message': f'{name} を登録しました',
            'user': {
                'felica_id': felica_id,
                'name':      name,
                'email':     email,
            }
        })

    except Exception as e:
        logging.error(f"登録エラー: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ========================
# カード削除API（おまけ）
# ========================
@app.route('/api/register/<felica_id>', methods=['DELETE'])
@check_api_key
def delete_card(felica_id):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM users WHERE felica_id = ?", (felica_id,)
            )
            user = cur.fetchone()
            if not user:
                return jsonify({
                    'status': 'error', 'message': '登録されていないカードです'
                }), 404

            cur.execute(
                "DELETE FROM users WHERE felica_id = ?", (felica_id,)
            )
            conn.commit()

        logging.info(f"削除: {user['name']} ({felica_id})")
        return jsonify({
            'status':  'success',
            'message': f'{user["name"]} を削除しました'
        })

    except Exception as e:
        logging.error(f"削除エラー: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 管理画面Blueprint登録
from app.admin import admin_bp
app.register_blueprint(admin_bp, url_prefix='/admin')


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )
