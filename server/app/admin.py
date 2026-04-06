from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, Response
import sqlite3
import csv
import io
import os
import sys
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime, date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, ADMIN_USERNAME, ADMIN_PASSWORD
from app.db import get_connection

admin_bp = Blueprint('admin', __name__)


# ========================
# Basic認証
# ========================
def check_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def authenticate():
    return Response(
        '認証が必要です',
        401,
        {'WWW-Authenticate': 'Basic realm="Attendance Admin"'}
    )

def requires_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================
# ユーザー一覧
# ========================
@admin_bp.route('/')
@admin_bp.route('/users')
@requires_auth
def user_list():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, felica_id, name, email, created_at FROM users ORDER BY name")
        users = cur.fetchall()
    return render_template('user_list.html', users=users)


# ========================
# ユーザー追加
# ========================
@admin_bp.route('/users/add', methods=['GET', 'POST'])
@requires_auth
def user_add():
    if request.method == 'POST':
        felica_id = request.form.get('felica_id', '').strip().upper()
        name      = request.form.get('name', '').strip()
        email     = request.form.get('email', '').strip()

        if not felica_id or not name:
            flash('Felica IDと氏名は必須です', 'error')
            return render_template('user_add.html')

        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (felica_id, name, email) VALUES (?, ?, ?)",
                    (felica_id, name, email)
                )
                conn.commit()
            flash(f'ユーザー「{name}」を追加しました', 'success')
            return redirect(url_for('admin.user_list'))

        except sqlite3.IntegrityError:
            flash('このFelica IDは既に登録されています', 'error')
        except Exception as e:
            flash(f'エラーが発生しました: {e}', 'error')

    return render_template('user_add.html')


# ========================
# ユーザー編集
# ========================
@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@requires_auth
def user_edit(user_id):
    if request.method == 'POST':
        felica_id = request.form.get('felica_id', '').strip().upper()
        name      = request.form.get('name', '').strip()
        email     = request.form.get('email', '').strip()

        if not felica_id or not name:
            flash('Felica IDと氏名は必須です', 'error')
        else:
            try:
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE users SET felica_id=?, name=?, email=?
                        WHERE user_id=?
                    """, (felica_id, name, email, user_id))
                    conn.commit()
                flash('ユーザー情報を更新しました', 'success')
                return redirect(url_for('admin.user_list'))

            except sqlite3.IntegrityError:
                flash('このFelica IDは既に使用されています', 'error')
            except Exception as e:
                flash(f'エラーが発生しました: {e}', 'error')

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, felica_id, name, email FROM users WHERE user_id=?", (user_id,))
        user = cur.fetchone()

    if not user:
        flash('ユーザーが見つかりません', 'error')
        return redirect(url_for('admin.user_list'))

    return render_template('user_edit.html', user=user)


# ========================
# ユーザー削除
# ========================
@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@requires_auth
def user_delete(user_id):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
            user = cur.fetchone()

            if not user:
                flash('ユーザーが見つかりません', 'error')
                return redirect(url_for('admin.user_list'))

            cur.execute("DELETE FROM users WHERE user_id=?", (user_id,))
            conn.commit()

        flash(f'ユーザー「{user["name"]}」を削除しました', 'success')

    except Exception as e:
        flash(f'削除エラー: {e}', 'error')

    return redirect(url_for('admin.user_list'))


# ========================
# CSVインポート
# ========================
@admin_bp.route('/users/import', methods=['GET', 'POST'])
@requires_auth
def user_import():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('ファイルが選択されていません', 'error')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('ファイルが選択されていません', 'error')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('CSVファイルのみ対応しています', 'error')
            return redirect(request.url)

        try:
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)

            required_columns = ['felica_id', 'name', 'email']
            if not all(col in reader.fieldnames for col in required_columns):
                flash(f'CSVに必要な列が不足しています。必要な列: {required_columns}', 'error')
                return redirect(request.url)

            success_count = 0
            skip_count    = 0
            error_list    = []

            with get_connection() as conn:
                cur = conn.cursor()
                for i, row in enumerate(reader, start=2):
                    try:
                        felica_id = str(row['felica_id']).strip().upper()
                        name      = str(row['name']).strip()
                        email     = str(row['email']).strip()

                        if not felica_id or not name:
                            error_list.append(f"{i}行目: Felica IDまたは氏名が空です")
                            continue

                        cur.execute("""
                            INSERT INTO users (felica_id, name, email)
                            VALUES (?, ?, ?)
                        """, (felica_id, name, email))
                        success_count += 1

                    except sqlite3.IntegrityError:
                        skip_count += 1
                    except Exception as e:
                        error_list.append(f"{i}行目: {e}")

                conn.commit()

            flash(f'{success_count}件インポート完了 / {skip_count}件スキップ（重複）', 'success')
            if error_list:
                flash(f'エラー行: {" / ".join(error_list[:5])}', 'warning')

            return redirect(url_for('admin.user_list'))

        except Exception as e:
            flash(f'ファイル処理エラー: {e}', 'error')

    return render_template('user_import.html')


# ========================
# CSVエクスポート
# ========================
@admin_bp.route('/users/export')
@requires_auth
def user_export():
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT felica_id, name, email FROM users ORDER BY name")
            users = cur.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['felica_id', 'name', 'email'])
        for user in users:
            writer.writerow([user['felica_id'], user['name'], user['email']])

        output.seek(0)

        return Response(
            '\ufeff' + output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=users.csv'}
        )

    except Exception as e:
        flash(f'エクスポートエラー: {e}', 'error')
        return redirect(url_for('admin.user_list'))


# ========================
# ログ一覧表示
# ========================
@admin_bp.route('/logs')
@requires_auth
def log_list():
    # 検索パラメータ取得
    target_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    user_id     = request.args.get('user_id', '')

    # ユーザー一覧（検索用プルダウン）
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, name FROM users ORDER BY name")
        users = cur.fetchall()

        # ログ検索クエリ
        query = """
            SELECT
                al.log_id,
                al.log_time,
                al.log_type,
                al.terminal_id,
                u.name,
                u.felica_id
            FROM attendance_logs al
            JOIN users u ON al.felica_id = u.felica_id
            WHERE DATE(al.log_time) = ?
        """
        params = [target_date]

        # ユーザー絞り込み
        if user_id:
            query += " AND u.user_id = ?"
            params.append(user_id)

        query += " ORDER BY al.log_time DESC"

        cur.execute(query, params)
        logs = cur.fetchall()

        # 本日のサマリー（最初のINと最後のOUT）
        summary_query = """
            SELECT
                u.name,
                MIN(CASE WHEN al.log_type = 'IN'  THEN al.log_time END) AS first_in,
                MAX(CASE WHEN al.log_type = 'OUT' THEN al.log_time END) AS last_out
            FROM attendance_logs al
            JOIN users u ON al.felica_id = u.felica_id
            WHERE DATE(al.log_time) = ?
        """
        summary_params = [target_date]

        if user_id:
            summary_query += " AND u.user_id = ?"
            summary_params.append(user_id)

        summary_query += " GROUP BY u.name ORDER BY u.name"

        cur.execute(summary_query, summary_params)
        summary = cur.fetchall()

    return render_template(
        'log_list.html',
        logs=logs,
        summary=summary,
        users=users,
        target_date=target_date,
        selected_user_id=user_id
    )
