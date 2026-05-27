#!/bin/bash
# monthly.sh - 月次集計（締め日は config.py の DEFAULT_CUTOFF_DAY を参照）
# 毎日実行されるが、締め日翌日のみ実処理する

PYTHON=/home/makoyuki/attendance/venv/bin/python
SCRIPT=/home/makoyuki/attendance/processor.py
HELPER=/home/makoyuki/attendance/cron/get_period.py

# ── 今日が実行日かチェック ──────────────────
IS_RUN_DAY=$($PYTHON $HELPER --check)

if [ "$IS_RUN_DAY" != "1" ]; then
    # 実行日でなければ何もしない
    exit 0
fi

# ── 集計期間を取得 ─────────────────────────
read START END <<< $($PYTHON $HELPER)

if [ -z "$START" ] || [ -z "$END" ]; then
    echo "[月次バッチ] エラー: 期間の取得に失敗しました"
    exit 1
fi

echo "========================================"
echo "[月次バッチ] 開始: $(date '+%Y-%m-%d %H:%M:%S')"
echo "[月次バッチ] 集計範囲: ${START} 〜 ${END}"

$PYTHON $SCRIPT --start $START --end $END

RESULT=$?
if [ $RESULT -eq 0 ]; then
    echo "[月次バッチ] 正常終了: $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo "[月次バッチ] 異常終了（終了コード: ${RESULT}）: $(date '+%Y-%m-%d %H:%M:%S')"
fi
