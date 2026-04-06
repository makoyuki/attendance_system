@echo off
echo FeliCa勤怠システム クライアントセットアップ
echo =====================================

python --version >nul 2>&1
if errorlevel 1 (
    echo エラー: Pythonがインストールされていません
    echo https://www.python.org/downloads/ からPython 3.11をインストールしてください
    pause
    exit /b 1
)

echo pipをアップグレードしています...
python -m pip install --upgrade pip

echo 必要なパッケージをインストールしています...
pip install -r requirements.txt

echo NFCリーダーの動作確認を行います...
python -m nfc
if errorlevel 1 (
    echo 警告: NFCリーダーが検出されませんでした
    echo USB接続を確認してください
)

echo セットアップ完了
echo.
echo 使用方法:
echo   IN端末:  python felica_reader.py IN  --server https://your-domain.com
echo   OUT端末: python felica_reader.py OUT --server https://your-domain.com
echo.
pause
