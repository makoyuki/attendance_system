import os

# ベースディレクトリ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# データベース設定
DB_PATH = os.path.join(BASE_DIR, 'data', 'attendance.db')

# 出力ディレクトリ
OUTPUT_DAILY_DIR   = os.path.join(BASE_DIR, 'output', 'daily')
OUTPUT_MONTHLY_DIR = os.path.join(BASE_DIR, 'output', 'monthly')

# ログディレクトリ
LOG_DIR = os.path.join(BASE_DIR, 'logs')

# アップロード設定
UPLOAD_FOLDER      = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'csv'}

# Flask設定
SECRET_KEY = 'your-secret-key-here'  # 本番環境では必ず変更すること

# メール設定（後程設定）
MAIL_SERVER   = 'smtp.your-domain.com'
MAIL_PORT     = 587
MAIL_USE_TLS  = True
MAIL_USERNAME = 'your-email@your-domain.com'
MAIL_PASSWORD = 'your-password'
MAIL_FROM     = 'attendance@your-domain.com'

# 締め日設定（デフォルト: 20日締め）
DEFAULT_CUTOFF_DAY = 20

# 管理画面認証情報
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'P@$$w0rd')

# APIキー（クライアント認証用）← 追加
API_KEY = os.environ.get('API_KEY', 'your-api-key-here')

# ディレクトリ作成
for directory in [
    OUTPUT_DAILY_DIR,
    OUTPUT_MONTHLY_DIR,
    LOG_DIR,
    UPLOAD_FOLDER,
    os.path.dirname(DB_PATH)
]:
    os.makedirs(directory, exist_ok=True)
