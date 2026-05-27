# app/admin.py
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, session
)
import sys
import os

# admin.py の場合: app/ の1つ上がBASE_DIR
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# こちらも insert(0, ...) に変更
sys.path.insert(0, BASE_DIR)

import sqlite3
import csv
import io
import zipfile
import logging
from notifier import send_admin_report, send_individual_reports, get_prev_week_range, _get_db as get_db
from functools import wraps
from datetime import datetime, date, timedelta

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, session
)
from config  import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, ADMIN_USERNAME, ADMIN_PASSWORD
from app.db  import get_connection

from processor import process, fetch_logs, _hm, Session
from mailer    import send_csv_report

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, ADMIN_USERNAME, ADMIN_PASSWORD
from app.db import get_connection

from notifier import (
    send_admin_report,
    send_individual_reports,
    get_prev_week_range,
    get_prev_month_range,   # ← 追加
    _get_db as get_db,
)


admin_bp = Blueprint('admin', __name__)

# ──────────────────────────────────────────────
# 日時パース・勤務時間計算
# ──────────────────────────────────────────────

_TIME_FORMATS = [
    '%Y-%m-%dT%H:%M:%S.%f',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d %H:%M:%S',
]

def parse_dt(s: str):
    if not s:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def calc_work_time(first_in_str, last_out_str):
    """first_in〜last_out の経過時間を 'h:mm' で返す。算出不可なら None"""
    in_dt  = parse_dt(first_in_str)
    out_dt = parse_dt(last_out_str)
    if not in_dt or not out_dt:
        return None
    total_min = int((out_dt - in_dt).total_seconds() / 60)
    if total_min < 0:
        return None
    return f"{total_min // 60}:{total_min % 60:02d}"

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# ────────────────────────────────────────────
# レポート用ヘルパー
# ────────────────────────────────────────────

_WEEKDAYS_JA = ['月', '火', '水', '木', '金', '土', '日']


def _detect_day_anomalies(sessions) -> list:
    """1日のセッションリストから異常を検知して [str] を返す"""
    issues = []
    for s in sessions:
        if s.midnight_out:
            issues.append("OUT未打刻（24:00強制終了）")
        if s.minutes > 12 * 60:
            issues.append(
                f"長時間勤務 {s.in_str}〜{s.out_str} "
                f"({s.minutes // 60}時間{s.minutes % 60}分)"
            )
        if s.minutes < 30 and not s.midnight_in:
            issues.append(
                f"短時間勤務 {s.in_str}〜{s.out_str} ({s.minutes}分)"
            )
    return issues


def _build_report_data(conn, start: date, end: date, user_filter: str = '') -> list:
    """
    指定期間の処理済みデータを構築して返す

    Returns: [{name, felica_id, daily_data, total_str, anomaly_count, result}]
    """
    cur = conn.cursor()
    if user_filter:
        cur.execute(
            "SELECT felica_id, name FROM users WHERE user_id=? ORDER BY name",
            (user_filter,)
        )
    else:
        cur.execute("SELECT felica_id, name FROM users ORDER BY name")
    users = cur.fetchall()

    report = []
    for user in users:
        logs = fetch_logs(conn, user['felica_id'], start, end)
        if not logs:
            continue
        full   = process(logs, user['felica_id'])
        result = {d: v for d, v in full.items() if start <= d <= end}
        if not result:
            continue

        daily_data    = []
        anomaly_count = 0

        for d in sorted(result):
            sessions  = result[d]
            total_min = sum(s.minutes for s in sessions)
            anomalies = _detect_day_anomalies(sessions)
            if anomalies:
                anomaly_count += 1

            daily_data.append({
                'date_str':  f"{d.strftime('%Y/%m/%d')}({_WEEKDAYS_JA[d.weekday()]})",
                'date':      d,
                'sessions':  [
                    {
                        'in_str':       s.in_str,
                        'out_str':      s.out_str,
                        'minutes':      s.minutes,
                        'midnight_out': s.midnight_out,
                    }
                    for s in sessions
                ],
                'total_min': total_min,
                'total_str': _hm(total_min),
                'anomalies': anomalies,
            })

        total_all = sum(r['total_min'] for r in daily_data)
        report.append({
            'name':          user['name'],
            'felica_id':     user['felica_id'],
            'daily_data':    daily_data,
            'total_str':     _hm(total_all),
            'total_min':     total_all,
            'anomaly_count': anomaly_count,
            'result':        result,
        })

    return report


def _generate_csv_content(result) -> str:
    """Dict[date, List[Session]] → CSV 文字列（BOM なし）"""
    if not result:
        return ""

    max_s  = max(len(v) for v in result.values())
    output = io.StringIO()
    w      = csv.writer(output)

    header = ['日付']
    for n in range(1, max_s + 1):
        header += [f'IN{n}', f'OUT{n}']
    header += ['合計(h:m)', '合計(分)']
    w.writerow(header)

    for d in sorted(result):
        ss    = result[d]
        row   = [d.strftime('%Y/%m/%d')]
        for s in ss:
            row += [s.in_str, s.out_str]
        row  += [''] * ((max_s - len(ss)) * 2)
        total = sum(s.minutes for s in ss)
        row  += [_hm(total), total]
        w.writerow(row)

    return output.getvalue()

# ══════════════════════════════════════════════
# セッション認証
# ══════════════════════════════════════════════

def requires_auth(f):
    """未ログインならログイン画面にリダイレクト"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('ログインしてください', 'warning')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


# ========================
# ログイン
# ========================
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    # 既にログイン済みなら一覧へ
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.user_list'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.permanent = True          # セッションを持続
            session['admin_logged_in'] = True
            return redirect(url_for('admin.user_list'))
        else:
            flash('ユーザー名またはパスワードが違います', 'error')

    return render_template('login.html')


# ========================
# ログアウト
# ========================
@admin_bp.route('/logout')
def logout():
    session.clear()
    flash('ログアウトしました', 'success')
    return redirect(url_for('admin.login'))


# ══════════════════════════════════════════════
# ユーザー管理
# ══════════════════════════════════════════════

@admin_bp.route('/')
@admin_bp.route('/users')
@requires_auth
def user_list():
    db     = get_db()
    filter = request.args.get('filter', 'all')

    if filter == 'active':
        users = db.execute(
            'SELECT * FROM users WHERE is_active=1 ORDER BY name'
        ).fetchall()
    elif filter == 'inactive':
        users = db.execute(
            'SELECT * FROM users WHERE is_active=0 ORDER BY name'
        ).fetchall()
    else:
        users = db.execute(
            'SELECT * FROM users ORDER BY is_active DESC, name'
        ).fetchall()

    return render_template('user_list.html', users=users, filter=filter)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@requires_auth
def user_add():
    if request.method == 'POST':
        felica_id = request.form.get('felica_id', '').strip().upper()
        name      = request.form.get('name',      '').strip()
        email     = request.form.get('email',     '').strip()

        if not felica_id or not name:
            flash('Felica IDと氏名は必須です', 'error')
            return render_template('user_add.html')

        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO users (felica_id, name, email) VALUES (?,?,?)",
                    (felica_id, name, email)
                )
                conn.commit()
            flash(f'ユーザー「{name}」を追加しました', 'success')
            return redirect(url_for('admin.user_list'))

        except sqlite3.IntegrityError:
            flash('このFelica IDは既に登録されています', 'error')
        except Exception as e:
            flash(f'エラー: {e}', 'error')

    return render_template('user_add.html')


@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@requires_auth
def user_edit(user_id):
    if request.method == 'POST':
        felica_id = request.form.get('felica_id', '').strip().upper()
        name      = request.form.get('name',      '').strip()
        email     = request.form.get('email',     '').strip()

        if not felica_id or not name:
            flash('Felica IDと氏名は必須です', 'error')
        else:
            try:
                with get_connection() as conn:
                    conn.execute("""
                        UPDATE users SET felica_id=?, name=?, email=?
                        WHERE user_id=?
                    """, (felica_id, name, email, user_id))
                    conn.commit()
                flash('ユーザー情報を更新しました', 'success')
                return redirect(url_for('admin.user_list'))
            except sqlite3.IntegrityError:
                flash('このFelica IDは既に使用されています', 'error')
            except Exception as e:
                flash(f'エラー: {e}', 'error')

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, felica_id, name, email FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cur.fetchone()

    if not user:
        flash('ユーザーが見つかりません', 'error')
        return redirect(url_for('admin.user_list'))

    return render_template('user_edit.html', user=user)


@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@requires_auth
def user_delete(user_id):
    db   = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE user_id=?', (user_id,)
    ).fetchone()
    if not user:
        flash('ユーザーが見つかりません', 'danger')
        return redirect(url_for('admin.user_list'))

    # 外部キー制約回避のためログを先に削除
    db.execute(
        'DELETE FROM attendance_logs WHERE felica_id=?',
        (user['felica_id'],)
    )
    db.execute(
        'DELETE FROM users WHERE user_id=?', (user_id,)
    )
    db.commit()
    flash(f'{user["name"]} を削除しました', 'success')
    return redirect(url_for('admin.user_list'))

@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@requires_auth
def user_toggle(user_id):
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE user_id=?', (user_id,)
    ).fetchone()
    if not user:
        flash('ユーザーが見つかりません', 'danger')
        return redirect(url_for('admin.user_list'))

    new_status = 0 if user['is_active'] else 1
    db.execute(
        'UPDATE users SET is_active=? WHERE user_id=?',
        (new_status, user_id)
    )
    db.commit()

    label = '有効' if new_status else '無効'
    flash(f'{user["name"]} を{label}にしました', 'success')
    return redirect(url_for('admin.user_list'))

# ──────────────────────────────────────────────
# CSV インポート / エクスポート
# ──────────────────────────────────────────────

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
            stream  = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader  = csv.DictReader(stream)
            success = skip = 0
            errors  = []

            with get_connection() as conn:
                cur = conn.cursor()
                for i, row in enumerate(reader, start=2):
                    try:
                        felica_id = str(row['felica_id']).strip().upper()
                        name      = str(row['name']).strip()
                        email     = str(row.get('email', '')).strip()

                        if not felica_id or not name:
                            errors.append(f"{i}行目: IDまたは氏名が空")
                            continue

                        cur.execute(
                            "INSERT INTO users (felica_id, name, email) VALUES (?,?,?)",
                            (felica_id, name, email)
                        )
                        success += 1

                    except sqlite3.IntegrityError:
                        skip += 1
                    except Exception as e:
                        errors.append(f"{i}行目: {e}")

                conn.commit()

            flash(f'{success}件インポート / {skip}件スキップ（重複）', 'success')
            if errors:
                flash('エラー行: ' + ' / '.join(errors[:5]), 'warning')

            return redirect(url_for('admin.user_list'))

        except Exception as e:
            flash(f'ファイル処理エラー: {e}', 'error')

    return render_template('user_import.html')


@admin_bp.route('/users/export')
@requires_auth
def user_export():
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT felica_id, name, email FROM users ORDER BY name"
            )
            users = cur.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['felica_id', 'name', 'email'])
        for u in users:
            writer.writerow([u['felica_id'], u['name'], u['email']])

        return Response(
            '\ufeff' + output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=users.csv'}
        )

    except Exception as e:
        flash(f'エクスポートエラー: {e}', 'error')
        return redirect(url_for('admin.user_list'))

# ══════════════════════════════════════════════
# レポート（日付範囲表示 + CSVダウンロード）
# ══════════════════════════════════════════════

@admin_bp.route('/reports')
@requires_auth
def reports():
    today     = date.today()
    start_str = request.args.get('start', today.replace(day=1).strftime('%Y-%m-%d'))
    end_str   = request.args.get('end',   today.strftime('%Y-%m-%d'))
    user_filter = request.args.get('user_id', '')

    try:
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
    except ValueError:
        start, end = today.replace(day=1), today

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, name FROM users ORDER BY name")
        users       = cur.fetchall()
        report_data = _build_report_data(conn, start, end, user_filter)

    return render_template(
        'reports.html',
        report_data=report_data,
        users=users,
        start=start_str,
        end=end_str,
        selected_user_id=user_filter,
    )


@admin_bp.route('/reports/download')
@requires_auth
def reports_download():
    today     = date.today()
    start_str = request.args.get('start', today.replace(day=1).strftime('%Y-%m-%d'))
    end_str   = request.args.get('end',   today.strftime('%Y-%m-%d'))
    user_filter = request.args.get('user_id', '')

    try:
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
    except ValueError:
        return "日付形式が不正です", 400

    with get_connection() as conn:
        report_data = _build_report_data(conn, start, end, user_filter)

    if not report_data:
        flash("ダウンロードするデータがありません", "warning")
        return redirect(url_for('admin.reports'))

    if len(report_data) == 1:
        # 1ユーザー → CSV 直接返却
        emp         = report_data[0]
        csv_content = _generate_csv_content(emp['result'])
        filename    = f"{emp['name']}_{start:%Y%m%d}_{end:%Y%m%d}_daily.csv"
        return Response(
            '\ufeff' + csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    # 複数ユーザー → ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for emp in report_data:
            csv_content = _generate_csv_content(emp['result'])
            filename    = f"{emp['name']}_{start:%Y%m%d}_{end:%Y%m%d}_daily.csv"
            zf.writestr(filename, '\ufeff' + csv_content)

    zip_buf.seek(0)
    return Response(
        zip_buf.getvalue(),
        mimetype='application/zip',
        headers={
            'Content-Disposition':
                f'attachment; filename="attendance_{start:%Y%m%d}_{end:%Y%m%d}.zip"'
        }
    )


# ══════════════════════════════════════════════
# 手動打刻追加
# ══════════════════════════════════════════════

@admin_bp.route('/logs/add', methods=['GET', 'POST'])
@requires_auth
def log_add():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT felica_id, name FROM users ORDER BY name")
        users = cur.fetchall()

    if request.method == 'POST':
        felica_id = request.form.get('felica_id', '').strip()
        log_type  = request.form.get('log_type',  '').strip()
        log_date  = request.form.get('log_date',  '').strip()
        log_time  = request.form.get('log_time',  '').strip()
        reason    = request.form.get('reason',    '').strip()

        if not all([felica_id, log_type, log_date, log_time]):
            flash('全項目を入力してください', 'error')
        elif log_type not in ('IN', 'OUT'):
            flash('種別は IN または OUT を選択してください', 'error')
        else:
            try:
                log_datetime = f"{log_date}T{log_time}:00"
                terminal_id  = f"manual:{reason}" if reason else "manual"

                with get_connection() as conn:
                    conn.execute("""
                        INSERT INTO attendance_logs
                            (felica_id, log_type, log_time, terminal_id)
                        VALUES (?, ?, ?, ?)
                    """, (felica_id, log_type, log_datetime, terminal_id))
                    conn.commit()

                flash(
                    f'手動打刻を追加しました: {log_date} {log_time} {log_type}',
                    'success'
                )
                return redirect(url_for('admin.log_list') + f'?date={log_date}')

            except Exception as e:
                flash(f'エラー: {e}', 'error')

    return render_template(
        'log_add.html',
        users=users,
        today=date.today().strftime('%Y-%m-%d'),
    )


# ══════════════════════════════════════════════
# 通知設定
# ══════════════════════════════════════════════
@admin_bp.route('/settings', methods=['GET', 'POST'])
@requires_auth
def settings():
    db  = get_db()
    msg = None

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'save':
            notify_daily              = 1 if request.form.get('notify_daily')              else 0
            notify_weekly             = 1 if request.form.get('notify_weekly')             else 0
            notify_monthly            = 1 if request.form.get('notify_monthly')            else 0
            notify_individual_daily   = 1 if request.form.get('notify_individual_daily')   else 0
            notify_individual_weekly  = 1 if request.form.get('notify_individual_weekly')  else 0
            notify_individual_monthly = 1 if request.form.get('notify_individual_monthly') else 0
            recipient_emails          = request.form.get('recipient_emails', '').strip()

            db.execute('''
                UPDATE notification_settings
                SET notify_daily=?, notify_weekly=?, notify_monthly=?,
                    notify_individual_daily=?, notify_individual_weekly=?,
                    notify_individual_monthly=?,
                    recipient_emails=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=1
            ''', (notify_daily, notify_weekly, notify_monthly,
                  notify_individual_daily, notify_individual_weekly,
                  notify_individual_monthly, recipient_emails))
            db.commit()
            msg = ('success', '設定を保存しました')

        elif action == 'send_test':
            # 管理者宛 週次（前週）
            row        = db.execute('SELECT * FROM notification_settings WHERE id=1').fetchone()
            recipients = [e.strip() for e in (row['recipient_emails'] or '').split(',') if e.strip()]
            if not recipients:
                msg = ('danger', '送付先メールアドレスが設定されていません')
            else:
                start, end = get_prev_week_range()
                ok  = send_admin_report(start, end, '週次（テスト）', recipients)
                msg = (
                    ('success', f'送信完了: {", ".join(recipients)}（{start}〜{end}）')
                    if ok else
                    ('danger', '送信に失敗しました。メール設定を確認してください')
                )

        elif action == 'send_individual_weekly':
            # 個別 週次（前週）
            start, end    = get_prev_week_range()
            success, fail = send_individual_reports(start, end, '週次（手動送信）')
            msg = _individual_result_msg(success, fail, start, end)

        elif action == 'send_individual_daily':
            # 個別 日次（昨日）
            from datetime import timedelta
            yesterday     = date.today() - timedelta(days=1)
            success, fail = send_individual_reports(yesterday, yesterday, '日次（手動送信）')
            msg = _individual_result_msg(success, fail, yesterday, yesterday)

        elif action == 'send_individual_monthly':
            # 個別 月次（直近の締め切り済み期間）
            start, end    = get_prev_month_range()
            success, fail = send_individual_reports(start, end, '月次（手動送信）')
            msg = _individual_result_msg(success, fail, start, end)

    row = db.execute('SELECT * FROM notification_settings WHERE id=1').fetchone()
    s   = dict(row) if row else {}
    s.setdefault('notify_individual_daily',   0)
    s.setdefault('notify_individual_weekly',  0)
    s.setdefault('notify_individual_monthly', 0)
    return render_template('settings.html', s=s, msg=msg)


def _individual_result_msg(success, fail, start, end):
    """個別送付結果メッセージを返す"""
    if success == 0 and fail == 0:
        return ('warning', 'メールアドレスが登録されているユーザーがいません')
    elif fail == 0:
        return ('success', f'個別送付完了: {success}名に送信しました（{start}〜{end}）')
    else:
        return ('warning', f'個別送付: 成功{success}名 / 失敗{fail}名（{start}〜{end}）')

# ══════════════════════════════════════════════
# ログ一覧
# ══════════════════════════════════════════════

@admin_bp.route('/logs')
@requires_auth
def log_list():
    target_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    user_id     = request.args.get('user_id', '')

    with get_connection() as conn:
        cur = conn.cursor()

        # ユーザー一覧（絞り込み用）
        cur.execute("SELECT user_id, name FROM users ORDER BY name")
        users = cur.fetchall()

        # ── 詳細ログ ────────────────────────────
        query  = """
            SELECT al.log_id, al.log_time, al.log_type, al.terminal_id,
                   u.name, u.felica_id
            FROM   attendance_logs al
            JOIN   users u ON al.felica_id = u.felica_id
            WHERE  DATE(al.log_time) = ?
        """
        params = [target_date]
        if user_id:
            query  += " AND u.user_id = ?"
            params.append(user_id)
        query += " ORDER BY al.log_time"
        cur.execute(query, params)
        raw_logs = cur.fetchall()

        # log_time を HH:MM 形式に整形
        logs = []
        for row in raw_logs:
            d         = dict(row)
            dt        = parse_dt(d['log_time'])
            d['time_display'] = dt.strftime('%H:%M') if dt else d['log_time']
            logs.append(d)

        # ── サマリー（最初のIN・最後のOUT・勤務時間）────
        sum_query = """
            SELECT u.name,
                   MIN(CASE WHEN al.log_type='IN'  THEN al.log_time END) AS first_in,
                   MAX(CASE WHEN al.log_type='OUT' THEN al.log_time END) AS last_out
            FROM   attendance_logs al
            JOIN   users u ON al.felica_id = u.felica_id
            WHERE  DATE(al.log_time) = ?
        """
        sum_params = [target_date]
        if user_id:
            sum_query  += " AND u.user_id = ?"
            sum_params.append(user_id)
        sum_query += " GROUP BY u.name ORDER BY u.name"

        cur.execute(sum_query, sum_params)
        raw_summary = cur.fetchall()

        # 勤務時間を Python 側で計算
        summary = []
        for row in raw_summary:
            d = dict(row)
            in_dt  = parse_dt(d['first_in'])
            out_dt = parse_dt(d['last_out'])
            d['first_in_display']  = in_dt.strftime('%H:%M')  if in_dt  else '-'
            d['last_out_display']  = out_dt.strftime('%H:%M') if out_dt else '-'
            d['work_time']         = calc_work_time(d['first_in'], d['last_out']) or '-'
            summary.append(d)

    return render_template(
        'log_list.html',
        logs=logs,
        summary=summary,
        users=users,
        target_date=target_date,
        selected_user_id=user_id,
    )
