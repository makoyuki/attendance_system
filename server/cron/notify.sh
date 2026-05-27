#!/bin/bash
# notify.sh - 通知メール送信バッチ

PYTHON=/home/makoyuki/attendance/venv/bin/python
SCRIPT=/home/makoyuki/attendance/cron/send_notification.py

echo "========================================"
echo "[通知バッチ] 開始: $(date '+%Y-%m-%d %H:%M:%S')"

$PYTHON $SCRIPT

RESULT=$?
if [ $RESULT -eq 0 ]; then
    echo "[通知バッチ] 正常終了: $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo "[通知バッチ] 異常終了（コード: ${RESULT}）: $(date '+%Y-%m-%d %H:%M:%S')"
fi
