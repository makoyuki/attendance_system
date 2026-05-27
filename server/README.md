# FeliCa 勤怠管理システム

FeliCa カードを使った入退室記録・勤怠管理システムです。

## 機能概要

- FeliCa カードによる入退室打刻（IN/OUT 自動判定）
- Web 管理画面（ユーザー管理・ログ確認・レポート出力）
- 勤怠レポートの CSV ダウンロード（日次・週次・月次）
- メール通知（管理者宛まとめ送付・ユーザー個別送付）
- 打刻異常検知（退室漏れ・長時間・短時間）

## システム要件

- Ubuntu Linux 20.04 以上
- Python 3.10 以上
- SQLite3
- Nginx + Let's Encrypt（HTTPS推奨）

## ディレクトリ構成

```
attendance/
├── app/
│   ├── server.py          # Flask アプリ本体
│   ├── admin.py           # 管理画面 Blueprint
│   └── db.py              # DB 初期化
├── processor.py           # 勤怠ログ処理エンジン
├── notifier.py            # メール通知共通ロジック
├── mailer.py              # Gmail 送信
├── config.py              # 設定ファイル（要作成）
├── config.py.example      # 設定ファイルテンプレート
├── cron/
│   ├── send_notification.py  # 定期通知スクリプト
│   ├── daily.sh              # 日次 CSV 生成
│   ├── monthly.sh            # 月次 CSV 生成
│   ├── notify.sh             # メール通知起動
│   └── get_period.py         # 締め期間計算
├── templates/             # HTML テンプレート
├── data/                  # SQLite DB（自動生成）
├── output/                # CSV 出力先（自動生成）
│   ├── daily/
│   ├── weekly/
│   └── monthly/
└── logs/                  # ログ出力先（自動生成）
```

## インストール手順

### 1. リポジトリをクローン

```bash
git clone https://github.com/yourname/attendance.git
cd attendance
```

### 2. 仮想環境を作成・有効化

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 設定ファイルを作成

```bash
cp config.py.example config.py
nano config.py
```

設定が必要な項目：

| 項目 | 説明 |
|------|------|
| `ADMIN_USERNAME` | 管理画面ログインユーザー名 |
| `ADMIN_PASSWORD` | 管理画面ログインパスワード |
| `API_KEY` | 打刻端末との認証キー |
| `MAIL_USERNAME` | Gmail アドレス |
| `MAIL_PASSWORD` | Google アプリパスワード（16桁） |
| `MAIL_FROM` | 送信元アドレス |
| `DEFAULT_CUTOFF_DAY` | 月次締め日（デフォルト: 20） |

### 4. ディレクトリ作成

```bash
mkdir -p data output/daily output/weekly output/monthly logs
```

### 5. データベース初期化

```bash
venv/bin/python -c "from app.db import initialize_db; initialize_db()"
```

### 6. 動作確認

```bash
cd attendance
venv/bin/python app/server.py
```

ブラウザで `http://localhost:5000/admin` にアクセスして確認。

---

## 本番環境セットアップ

### systemd サービス登録

`/etc/systemd/system/attendance-service.service` を作成：

```ini
[Unit]
Description=Attendance Management System
After=network.target

[Service]
User=makoyuki
WorkingDirectory=/home/makoyuki/attendance
ExecStart=/home/makoyuki/attendance/venv/bin/gunicorn \
    -w 2 \
    -b 127.0.0.1:5000 \
    app.server:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable attendance-service
sudo systemctl start attendance-service
```

### Nginx 設定例

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### crontab 設定

```bash
crontab -e
```

```cron
# 日次 CSV 生成（毎日 5:00）
0 5 * * * /home/makoyuki/attendance/cron/daily.sh >> /home/makoyuki/attendance/logs/cron.log 2>&1

# 月次 CSV 生成（毎日 5:30）
30 5 * * * /home/makoyuki/attendance/cron/monthly.sh >> /home/makoyuki/attendance/logs/cron.log 2>&1

# メール通知（毎日 6:00）
0 6 * * * /home/makoyuki/attendance/cron/notify.sh >> /home/makoyuki/attendance/logs/cron.log 2>&1
```

---

## Gmail アプリパスワードの設定

1. Google アカウントの「2段階認証」を有効にする
2. [Google アカウント] → [セキュリティ] → [アプリパスワード] を開く
3. 「メール」「その他のデバイス」で16桁のパスワードを生成
4. `config.py` の `MAIL_PASSWORD` に設定する
5. サービス再起動: `sudo systemctl restart attendance-service`

---

## API 仕様

すべての API リクエストに `X-API-Key` ヘッダーが必要です。

### 打刻記録

```
POST /api/log
X-API-Key: {API_KEY}
Content-Type: application/json

{
  "felica_id": "01020304AABBCCDD",
  "log_type": "IN" or "OUT",
  "timestamp": "2026-05-25T09:00:00.000000",
  "terminal_id": "terminal-01"
}
```

| レスポンス | 意味 |
|-----------|------|
| 200 OK | 打刻成功 |
| 400 | 必須フィールド不足 |
| 403 | 無効化されたユーザー |
| 404 | 未登録カード |

### カード登録

```
POST /api/register
X-API-Key: {API_KEY}
Content-Type: application/json

{
  "felica_id": "01020304AABBCCDD",
  "name": "山田太郎",
  "email": "yamada@example.com"
}
```

### カード削除

```
DELETE /api/register/{felica_id}
X-API-Key: {API_KEY}
```

---

## 管理画面

`https://your-domain.com/admin` にアクセス

| メニュー | 機能 |
|---------|------|
| ユーザー管理 | ユーザーの追加・編集・削除・有効化/無効化・CSV入出力 |
| 入退室ログ | 打刻ログの確認・手動打刻追加 |
| レポート | 期間指定での勤怠レポート表示・CSV/ZIPダウンロード |
| 設定 | メール通知設定・手動送信 |

### ユーザーの有効化/無効化

- **無効化**: 打刻不可・メール送付対象外。打刻ログは残る
- **有効化**: 元通り打刻可能・メール送付対象に戻る
- **削除**: ユーザーと打刻ログを完全削除（要確認）

---

## メール通知設定

管理画面の「設定」から以下を設定できます。

### 自動通知（cron）

| 種別 | 管理者宛 | 個別送付 | タイミング |
|------|---------|---------|-----------|
| 日次 | ON/OFF | ON/OFF | 毎日前日分 |
| 週次 | ON/OFF | ON/OFF | 毎週月曜 前週分 |
| 月次 | ON/OFF | ON/OFF | 締め日翌日 前月分 |

### 手動送信

| ボタン | 内容 |
|--------|------|
| 管理者宛に全員分送信 | 前週分・全ユーザーまとめ |
| 個別送付（昨日分） | 各ユーザーに前日分 |
| 個別送付（前週分） | 各ユーザーに前週分 |
| 個別送付（直近締め期間） | 各ユーザーに直近締め期間分 |

### 打刻異常検知

個別送付メールに以下の異常情報が含まれます：

| 種別 | 条件 |
|------|------|
| 退室打刻なし | 退室記録がない |
| 退室打刻漏れ | 日付をまたいで強制退室（24:00 OUT） |
| 長時間勤務 | 12時間超のセッション |
| 短時間打刻 | 30分未満のセッション |

異常がある場合は件名に ⚠️ が付き、本文冒頭に警告が表示されます。

---

## Windows カード登録クライアント

`card_register.py` を Windows PC で実行することで、FeliCa カードをかざして
ユーザー登録ができます。

### 設定

`card_register.py` の先頭にある以下を編集：

```python
SERVER_URL = 'https://your-domain.com'
API_KEY    = 'your-api-key-here'
```

### 実行

```bash
python card_register.py
```

---

## トラブルシューティング

### サービスが起動しない

```bash
sudo journalctl -u attendance-service -n 50 --no-pager
```

### メールが送信されない

```bash
cd /home/makoyuki/attendance
venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from notifier import send_admin_report, get_prev_week_range
start, end = get_prev_week_range()
result = send_admin_report(start, end, 'テスト', ['your@email.com'])
print('結果:', result)
"
```

### DB のマイグレーション（カラム追加）

```bash
venv/bin/python -c "
import sqlite3
from config import DB_PATH
conn = sqlite3.connect(DB_PATH)
conn.execute('ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1')
conn.execute('ALTER TABLE notification_settings ADD COLUMN notify_individual_daily INTEGER DEFAULT 0')
conn.execute('ALTER TABLE notification_settings ADD COLUMN notify_individual_weekly INTEGER DEFAULT 0')
conn.execute('ALTER TABLE notification_settings ADD COLUMN notify_individual_monthly INTEGER DEFAULT 0')
conn.commit()
conn.close()
print('完了')
"
```

---

## 注意事項

- `processor.py` は `attendance/` 直下に置くこと（`app/` 配下は不可）
- venv 内に `processor`（Hy言語パッケージ）が存在すると名前衝突するため注意
- `config.py` は `.gitignore` で除外済み。Git に機密情報をコミットしないこと

---

## ライセンス

MIT License