import sys
import os
import csv
import logging
from datetime import datetime, date, timedelta, time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LOG_DIR, OUTPUT_DAILY_DIR
from app.db import get_connection

# ──────────────────────────────────────────────
# ログ設定
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, 'processor.log'),
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# log_time パース
# ══════════════════════════════════════════════

_TIME_FORMATS = [
    '%Y-%m-%dT%H:%M:%S.%f',   # 2026-04-15T21:55:18.098790 ← 実フォーマット
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d %H:%M:%S',
]

def parse_dt(s: str) -> datetime:
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"日時フォーマット不明: {s!r}")


# ══════════════════════════════════════════════
# DB アクセス
# ══════════════════════════════════════════════

def fetch_all_users(conn) -> Dict[str, str]:
    cur = conn.execute(
        "SELECT felica_id, name FROM users ORDER BY user_id"
    )
    return {row['felica_id']: row['name'] for row in cur.fetchall()}


def fetch_logs(
    conn,
    felica_id: str,
    start: date,
    end:   date,
) -> List[Tuple[datetime, str]]:
    """日マタギ対応のため前後1日バッファを含めて取得"""
    q_start = (start - timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
    q_end   = (end   + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')

    cur = conn.execute("""
        SELECT log_time, log_type
        FROM   attendance_logs
        WHERE  felica_id = ?
          AND  log_time >= ?
          AND  log_time <  ?
        ORDER  BY log_time
    """, (felica_id, q_start, q_end))

    rows = []
    for row in cur.fetchall():
        try:
            rows.append((parse_dt(row['log_time']), row['log_type']))
        except ValueError as e:
            log.warning(f"パース失敗スキップ: {e}")
    return rows


# ══════════════════════════════════════════════
# セッションクラス
# ══════════════════════════════════════════════

class Session:
    """IN〜OUT の1勤務ペア"""
    def __init__(
        self,
        in_dt:        datetime,
        out_dt:       datetime,
        midnight_in:  bool = False,
        midnight_out: bool = False,
    ):
        self.in_dt        = in_dt
        self.out_dt       = out_dt
        self.midnight_in  = midnight_in
        self.midnight_out = midnight_out

    @property
    def in_str(self) -> str:
        return "00:00" if self.midnight_in  else self.in_dt.strftime('%H:%M')

    @property
    def out_str(self) -> str:
        return "24:00" if self.midnight_out else self.out_dt.strftime('%H:%M')

    @property
    def minutes(self) -> int:
        return int((self.out_dt - self.in_dt).total_seconds() / 60)

    def __repr__(self):
        tag = ("[繰越]" if self.midnight_in  else "") + \
              ("[強制]" if self.midnight_out else "")
        return f"Session({self.in_str}→{self.out_str} {self.minutes}分{tag})"


# ══════════════════════════════════════════════
# コアロジック
# ══════════════════════════════════════════════

def collapse(
    records: List[Tuple[datetime, str]]
) -> List[Tuple[str, datetime]]:
    """
    連続する同一 log_type をまとめる
      IN  連続 → 最も早い時刻
      OUT 連続 → 最も遅い時刻
    """
    result: List[Tuple[str, datetime]] = []
    i = 0
    while i < len(records):
        action = records[i][1]
        group: List[datetime] = []
        while i < len(records) and records[i][1] == action:
            group.append(records[i][0])
            i += 1
        ts = min(group) if action == 'IN' else max(group)
        result.append((action, ts))
    return result


def to_sessions(
    collapsed:    List[Tuple[str, datetime]],
    work_date:    date,
    carryover_in: bool,
) -> Tuple[List[Session], bool]:
    """
    正規化済みリスト → Session リスト

    Returns:
        sessions       : この日のセッションリスト
        next_carryover : True = この日が OUT 未出現で終了
    """
    sessions: List[Session] = []
    next_carryover = False
    i = 0

    # 先頭 OUT（孤立）→ スキップ
    if collapsed and collapsed[0][0] == 'OUT':
        log.warning(
            f"[{work_date}] 先頭 OUT（孤立）スキップ: "
            f"{collapsed[0][1]:%H:%M}"
        )
        i = 1

    while i < len(collapsed):
        action, ts = collapsed[i]

        if action == 'OUT':
            log.warning(f"[{work_date}] 孤立 OUT スキップ: {ts:%H:%M}")
            i += 1
            continue

        is_mid_in = carryover_in and (i == 0)

        if i + 1 < len(collapsed) and collapsed[i + 1][0] == 'OUT':
            # 通常ペア: IN → OUT
            _, out_ts = collapsed[i + 1]
            sessions.append(Session(ts, out_ts, midnight_in=is_mid_in))
            i += 2
        else:
            # OUT なし → 24:00 強制終了
            # ※ 実打刻の IN がある日に限り発動（carryover のみの日は来ない）
            end_of_day = datetime.combine(
                work_date + timedelta(days=1), time(0, 0)
            )
            sessions.append(Session(
                ts, end_of_day,
                midnight_in=is_mid_in,
                midnight_out=True,
            ))
            next_carryover = True
            log.info(
                f"[{work_date}] {ts:%H:%M} IN のまま終了 "
                f"→ 24:00強制OUT / 翌日繰り越し"
            )
            break

    return sessions, next_carryover


def process(
    logs:      List[Tuple[datetime, str]],
    felica_id: str = "",
) -> Dict[date, List[Session]]:
    """
    生ログ全体 → {日付: [Session]}

    【carryover ルール】
      carryover = True（前日 IN のみで終了）の場合でも
      翌日に実打刻が1件もなければ繰り越しを終了し記録を作らない

      理由: 実打刻のない日に 00:00IN → 24:00OUT の phantom 記録が
            連鎖生成されるのを防ぐ
    """
    if not logs:
        return {}

    by_date: Dict[date, List[Tuple[datetime, str]]] = defaultdict(list)
    for ts, action in logs:
        by_date[ts.date()].append((ts, action))

    first_day = min(by_date)
    last_day  = max(by_date)
    result:   Dict[date, List[Session]] = {}
    carryover = False

    cur_day = first_day
    while cur_day <= last_day:
        day_records   = list(by_date.get(cur_day, []))
        has_real_recs = len(day_records) > 0   # 実際の打刻があるか

        if carryover:
            if has_real_recs:
                # ✅ 実打刻がある日のみ 00:00 IN を注入して繰り越し継続
                midnight = datetime.combine(cur_day, time(0, 0))
                day_records.insert(0, (midnight, 'IN'))
                log.info(f"[{cur_day}] 00:00 IN（前日繰り越し）注入")
            else:
                # ❌ 実打刻がない日 → 繰り越しを終了（phantom 記録を作らない）
                log.warning(
                    f"[{cur_day}] 繰り越しINあるが実打刻なし "
                    f"→ 繰り越し終了（OUT未検出のまま打ち切り）"
                )
                carryover = False
                cur_day += timedelta(days=1)
                continue

        if day_records:
            collapsed = collapse(day_records)
            sessions, next_carryover = to_sessions(
                collapsed, cur_day, carryover
            )
            if sessions:
                result[cur_day] = sessions
            carryover = next_carryover
        else:
            carryover = False

        cur_day += timedelta(days=1)

    if carryover:
        log.warning(
            f"[{felica_id}] 最終日({last_day}) IN 未解決。"
            "次回バッチ実行時に実打刻があれば 00:00 IN として継続されます。"
        )

    return result


# ══════════════════════════════════════════════
# 日次 CSV 出力
# ══════════════════════════════════════════════

def _hm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def write_daily_csv(
    result: Dict[date, List[Session]],
    path:   Path,
) -> None:
    """
    日次 CSV
    列: 日付, IN1, OUT1, IN2, OUT2, ..., 合計(h:m), 合計(分)
    セッション数が少ない日は空白で埋める
    """
    if not result:
        log.info(f"出力データなし: {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    max_s = max(len(v) for v in result.values())

    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)

        # ヘッダー
        header = ['日付']
        for n in range(1, max_s + 1):
            header += [f'IN{n}', f'OUT{n}']
        header += ['合計(h:m)', '合計(分)']
        w.writerow(header)

        # データ行
        for d in sorted(result):
            ss  = result[d]
            row = [d.strftime('%Y/%m/%d')]
            for s in ss:
                row += [s.in_str, s.out_str]
            row += [''] * ((max_s - len(ss)) * 2)
            total = sum(s.minutes for s in ss)
            row  += [_hm(total), total]
            w.writerow(row)

    log.info(f"日次CSV → {path}")


# ══════════════════════════════════════════════
# バッチ実行
# ══════════════════════════════════════════════

def run(start: date, end: date) -> None:
    with get_connection() as conn:
        users = fetch_all_users(conn)

        if not users:
            log.warning("登録ユーザーが存在しません")
            return

        log.info(f"処理開始: {start} 〜 {end} / 対象 {len(users)} 名")

        for felica_id, name in users.items():
            log.info(f"── {name}({felica_id}) 処理開始")

            logs = fetch_logs(conn, felica_id, start, end)
            if not logs:
                log.info(f"   {name}: 対象期間にデータなし、スキップ")
                continue

            full_result = process(logs, felica_id)

            # 指定期間に絞る（前後バッファ分を除外）
            result = {
                d: v for d, v in full_result.items()
                if start <= d <= end
            }
            if not result:
                log.info(f"   {name}: 絞り込み後データなし、スキップ")
                continue

            span = f"{start:%Y%m%d}_{end:%Y%m%d}"
            write_daily_csv(
                result,
                Path(OUTPUT_DAILY_DIR) / f"{name}_{span}_daily.csv"
            )
            log.info(f"── {name} 完了")

        log.info("全処理完了")


# ──────────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='出退勤日次集計バッチ')
    p.add_argument('--start', required=True, help='開始日 YYYY-MM-DD')
    p.add_argument('--end',   required=True, help='終了日 YYYY-MM-DD')
    a = p.parse_args()
    run(date.fromisoformat(a.start), date.fromisoformat(a.end))
