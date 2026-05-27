# FeliCa 勤怠端末クライアント（Windows）

FeliCa カード対応の勤怠打刻端末・カード登録アプリです。  
Sony RC-S380（USB接続）と組み合わせて使用します。

## 必要なもの

| 項目 | 内容 |
|------|------|
| OS | Windows 10 / 11 |
| Python | 3.11（推奨） |
| NFC リーダー | Sony RC-S380 |
| USB ドライバ | WinUSB（Zadig で切り替え） |
| サーバー | FeliCa 勤怠管理サーバー（別途セットアップ） |

---

## セットアップ手順

### 1. Python のインストール

https://www.python.org/downloads/ から Python 3.11 をインストール。  
インストール時に **「Add Python to PATH」** にチェックを入れること。

### 2. リポジトリをクローン

```bash
git clone https://github.com/yourname/felica-attendance-client.git
cd felica-attendance-client
```

またはZIPをダウンロードして展開してもOKです。

### 3. USB ドライバを WinUSB に切り替え（重要）

nfcpy が RC-S380 を認識するために、USB ドライバを変更する必要があります。

1. **Zadig** をダウンロード: https://zadig.akeo.ie/
2. RC-S380 を USB 接続する
3. Zadig を起動 → メニュー「Options」→「List All Devices」にチェック
4. ドロップダウンから「RC-S380」を選択
5. ドライバを「WinUSB」に変更 → 「Replace Driver」をクリック
6. 完了後、PCを再起動

> ⚠️ この変更を行うと Sony の純正ソフト（PaSoRi 等）は使用不可になります。  
> 元に戻す場合はデバイスマネージャーでドライバを削除して再インストールしてください。

### 4. パッケージのインストール

```cmd
setup.bat
```

または手動で：

```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. 設定ファイルを作成

```cmd
copy config.py.example config.py
notepad config.py
```

以下を編集してください：

```python
SERVER_URL = 'https://your-domain.com'   # サーバーの URL
API_KEY    = 'your-api-key-here'          # サーバーと同じ API キー
```

---

## 使い方

### 打刻端末（felica_reader.py）

#### 出勤端末として起動

```cmd
python felica_reader.py IN
```

#### 退勤端末として起動

```cmd
python felica_reader.py OUT
```

#### オプション一覧

```
python felica_reader.py IN|OUT [オプション]

オプション:
  --server URL          サーバーURL（config.py の値を上書き）
  --api-key KEY         APIキー（config.py の値を上書き）
  --no-ssl-verify       SSL証明書の検証を無効にする（自己署名証明書の場合）
  --no-gui              GUI を無効にしてコンソールのみで動作
```

#### 実行例

```cmd
# 通常起動（config.py の設定を使用）
python felica_reader.py IN

# サーバーURLを指定して起動
python felica_reader.py OUT --server https://your-domain.com

# SSL検証なし・GUI無効
python felica_reader.py IN --no-ssl-verify --no-gui
```

#### 画面の説明

| 状態 | 表示 |
|------|------|
| 待機中 | 「カードをタッチしてください」（紺色背景） |
| 出勤打刻成功 | 名前・「出勤」表示（緑背景、3秒後に待機画面へ） |
| 退勤打刻成功 | 名前・「退勤」表示（赤背景、3秒後に待機画面へ） |
| エラー | エラーメッセージ（橙背景、3秒後に待機画面へ） |

- `Esc` キー: フルスクリーン切り替え
- `Ctrl+C`: 終了

---

### カード登録（card_register.py）

新規ユーザーの FeliCa カードをサーバーに登録するアプリです。

```cmd
python card_register.py
```

#### 操作手順

1. アプリを起動する
2. 登録したいカードを RC-S380 にタッチする
3. カードIDが自動入力される
4. 氏名（必須）・メールアドレス（任意）を入力する
5. 「登録」ボタンをクリック → 確認ダイアログ → 登録完了

---

## ファイル構成

```
felica-attendance-client/
├── felica_reader.py       # 打刻端末アプリ
├── card_register.py       # カード登録アプリ
├── requirements.txt       # 依存パッケージ
├── setup.bat              # セットアップスクリプト
├── config.py.example      # 設定ファイルテンプレート
├── config.py              # 設定ファイル（要作成、Git管理外）
└── touch.wav              # タッチ音声（任意、Git管理外）
```

---

## 音声について

カードタッチ時の効果音を設定できます。

1. `touch.wav` という名前の WAV ファイルを同じフォルダに置く
2. 次回起動時から自動的に使用される

`touch.wav` がない場合はビープ音が鳴ります。  
pygame が未インストールの場合も同様です。

---

## 自動起動の設定（Windows）

起動時に自動的に打刻端末を立ち上げる場合は、  
タスクスケジューラに以下を登録してください。

### バッチファイルを作成（例：start_in.bat）

```bat
@echo off
cd /d C:\path\to\felica-attendance-client
python felica_reader.py IN
pause
```

### タスクスケジューラの設定

1. 「タスクスケジューラ」を開く
2. 「タスクの作成」
3. トリガー: 「ログオン時」
4. 操作: 上記の `.bat` ファイルを指定
5. 全般: 「最上位の特権で実行する」にチェック

---

## トラブルシューティング

### NFC デバイスが認識されない

```
Error: NFC デバイスを開けません
```

**原因と対処:**

| 原因 | 対処 |
|------|------|
| WinUSB ドライバ未設定 | Zadig でドライバを切り替える |
| RC-S380 が USB 未接続 | USB ケーブルを確認、抜き差しする |
| 別アプリが使用中 | Sony 純正ソフトを終了させる |
| Python 権限不足 | コマンドプロンプトを管理者として実行 |

### サーバーに接続できない

```
サーバーに接続できません
```

**確認事項:**
- `config.py` の `SERVER_URL` が正しいか確認
- サーバーが起動しているか確認
- ファイアウォールで 443（HTTPS）または 5000 ポートが開いているか確認
- 自己署名証明書を使っている場合は `--no-ssl-verify` を追加

### 未登録カードです

```
未登録カードです
```

**対処:** `card_register.py` でカードを登録してください。

### 認証エラー

```
認証エラー: APIキーを確認してください
```

**対処:** `config.py` の `API_KEY` がサーバー側の設定と一致しているか確認してください。

### nfcpy のインストールエラー

```
error: Microsoft Visual C++ 14.0 or greater is required.
```

**対処:**
1. https://visualstudio.microsoft.com/visual-cpp-build-tools/ から  
   「Build Tools for Visual Studio」をインストール
2. 「C++ によるデスクトップ開発」を選択してインストール
3. 再度 `pip install -r requirements.txt` を実行

### ログの確認

```cmd
type attendance_reader.log
```

---

## 依存パッケージ

| パッケージ | バージョン | 用途 |
|-----------|-----------|------|
| nfcpy | 1.0.4 | FeliCa カード読み取り |
| pyscard | 2.0.7 | PC/SC スマートカード |
| libusb-package | ≥1.0.26 | USB通信 |
| libusb1 | ≥3.0.0 | USB通信 |
| requests | 2.31.0 | HTTP通信 |
| urllib3 | 1.26.18 | HTTP通信 |
| pygame | 2.6.1 | 音声再生（任意） |

---

## API 仕様（参考）

### 打刻記録

```
POST /api/log
X-API-Key: {API_KEY}

{
  "felica_id":   "01020304AABBCCDD",
  "log_type":    "IN" | "OUT",
  "timestamp":   "2026-05-25T09:00:00.000000",
  "terminal_id": "TERM_IN_01"
}
```

| ステータス | 意味 |
|-----------|------|
| 200 | 打刻成功 → `{ employee_name, greeting, log_type }` |
| 401 | API キー不正 |
| 403 | 無効化されたユーザー |
| 404 | 未登録カード |

### カード登録

```
POST /api/register
X-API-Key: {API_KEY}

{
  "felica_id": "01020304AABBCCDD",
  "name":      "山田太郎",
  "email":     "yamada@example.com"
}
```

---

## ライセンス

MIT License