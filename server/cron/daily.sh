#!/bin/bash
# daily.sh - 前日分の日次集計

PYTHON=/home/makoyuki/attendance/venv/bin/python
SCRIPT=/home/makoyuki/attendance/processor.py

TARGET=$(date -d yesterday +%Y-%m-%d)

echo "========================================"
echo "[日次バッチ] 開始: $(date '+%Y-%m-%d %H:%M:%S')"
echo "[日次バッチ] 対象日: ${TARGET}"

$PYTHON $SCRIPT --start $TARGET --end $TARGET

RESULT=$?
if [ $RESULT -eq 0 ]; then
    echo "[日次バッチ] 正常終了: $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo "[日次バッチ] 異常終了（終了コード: ${RESULT}）: $(date '+%Y-%m-%d %H:%M:%S')"
fi
