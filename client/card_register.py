# -*- coding: utf-8 -*-
"""
card_register.py
カード登録専用アプリ (Windows)

動作:
  1. 起動するとカード待ち受け状態
  2. RC-S380 にカードをタッチ → カードID自動入力
  3. 氏名・メールを入力して「登録」ボタン
  4. サーバーAPIに送信 → 結果表示

依存: nfcpy, requests, tkinter(標準)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
import nfc

# ──────────────────────────────────────────────
# 設定（環境に合わせて変更）
# ──────────────────────────────────────────────
try:
    from config import SERVER_URL, API_KEY
except ImportError:
    SERVER_URL = 'https://your-domain.com'
    API_KEY    = 'your-api-key-here'


# ??????????????????????????????????????????????
# メインアプリ
# ??????????????????????????????????????????????

class CardRegisterApp:
    def __init__(self, root: tk.Tk):
        self.root     = root
        self.card_id  = None      # 読み取り済みカードID
        self._reading = False     # リーダースレッド制御フラグ

        self.root.title("カード登録")
        self.root.geometry("420x380")
        self.root.resizable(False, False)

        self._build_ui()
        self._start_reader()

    # ─────────────────────────────────
    # UI 構築
    # ─────────────────────────────────
    def _build_ui(self):

        # ── ステータス ──────────────────────
        self.status_var = tk.StringVar(value="カードをタッチしてください")
        lbl_status = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Meiryo", 12),
            fg="#1565C0",
            pady=10,
        )
        lbl_status.pack(fill='x', padx=20)

        # ── 入力フォーム ────────────────────
        frame = tk.LabelFrame(self.root, text="登録情報", padx=15, pady=10)
        frame.pack(fill='x', padx=20, pady=5)

        # カードID（読み取り自動入力・編集不可）
        tk.Label(frame, text="カードID", anchor='w', width=10).grid(
            row=0, column=0, sticky='w', pady=4
        )
        self.card_id_var = tk.StringVar()
        tk.Entry(
            frame,
            textvariable=self.card_id_var,
            state='readonly',
            width=28,
            bg="#F5F5F5",
        ).grid(row=0, column=1, sticky='w')

        # 氏名
        tk.Label(frame, text="氏名 *", anchor='w', width=10).grid(
            row=1, column=0, sticky='w', pady=4
        )
        self.name_var = tk.StringVar()
        self.entry_name = tk.Entry(frame, textvariable=self.name_var, width=28)
        self.entry_name.grid(row=1, column=1, sticky='w')

        # メールアドレス（任意）
        tk.Label(frame, text="メール", anchor='w', width=10).grid(
            row=2, column=0, sticky='w', pady=4
        )
        self.email_var = tk.StringVar()
        tk.Entry(frame, textvariable=self.email_var, width=28).grid(
            row=2, column=1, sticky='w'
        )

        # ── ボタン ──────────────────────────
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=12)

        self.btn_register = tk.Button(
            btn_frame,
            text="　登　録　",
            command=self._on_register,
            state='disabled',
            bg="#43A047",
            fg="white",
            font=("Meiryo", 11, "bold"),
            relief='raised',
            cursor='hand2',
        )
        self.btn_register.pack(side='left', padx=8)

        tk.Button(
            btn_frame,
            text="　クリア　",
            command=self._reset,
            bg="#757575",
            fg="white",
            font=("Meiryo", 11),
            cursor='hand2',
        ).pack(side='left', padx=8)

        # ── 結果表示 ─────────────────────────
        self.result_var = tk.StringVar()
        tk.Label(
            self.root,
            textvariable=self.result_var,
            font=("Meiryo", 11),
            wraplength=380,
            justify='left',
            pady=5,
        ).pack(fill='x', padx=20)

    # ─────────────────────────────────
    # カード読み取り（バックグラウンド）
    # ─────────────────────────────────
    def _start_reader(self):
        """別スレッドでカード待ち受けを開始"""
        self._reading = True
        t = threading.Thread(target=self._reader_loop, daemon=True)
        t.start()

    def _reader_loop(self):
        """nfcpy でカードを待ち受けるループ"""
        try:
            with nfc.ContactlessFrontend('usb') as clf:
                while self._reading:
                    clf.connect(rdwr={
                        'on-connect': self._on_card_touch,
                    })
        except Exception as e:
            # UIスレッドにエラーを通知
            self.root.after(0, self._set_status, f"リーダーエラー: {e}", "red")

    def _on_card_touch(self, tag) -> bool:
        """カードタッチ時のコールバック（リーダースレッドから呼ばれる）"""
        card_id = tag.identifier.hex().upper()
        # UIはメインスレッドでのみ更新する
        self.root.after(0, self._on_card_detected, card_id)
        return False   # 即切断（True だと接続維持になる）

    def _on_card_detected(self, card_id: str):
        """カードID検出後のUI更新（メインスレッド）"""
        self.card_id = card_id
        self.card_id_var.set(card_id)
        self._set_status("カードを読み取りました。氏名を入力してください。", "#1565C0")
        self.btn_register.config(state='normal')
        self.result_var.set("")
        self.entry_name.focus_set()   # 氏名欄にフォーカス

    # ─────────────────────────────────
    # 登録処理
    # ─────────────────────────────────
    def _on_register(self):
        if not self.card_id:
            messagebox.showwarning("確認", "カードをタッチしてください")
            return

        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("確認", "氏名を入力してください")
            self.entry_name.focus_set()
            return

        email = self.email_var.get().strip()

        # 確認ダイアログ
        if not messagebox.askyesno(
            "登録確認",
            f"以下の内容で登録しますか？\n\n"
            f"カードID : {self.card_id}\n"
            f"氏　　名 : {name}\n"
            f"メール   : {email or '（未入力）'}"
        ):
            return

        self._set_status("登録中...", "#FF8F00")
        self.btn_register.config(state='disabled')

        # 通信はバックグラウンドで実行（UIフリーズ防止）
        t = threading.Thread(
            target=self._send_register,
            args=(self.card_id, name, email),
            daemon=True
        )
        t.start()

    def _send_register(self, felica_id: str, name: str, email: str):
        """サーバーへ登録リクエストを送信（別スレッド）"""
        try:
            resp = requests.post(
                f"{SERVER_URL}/api/register",
                json={
                    'felica_id': felica_id,
                    'name':      name,
                    'email':     email,
                },
                headers={'X-API-Key': API_KEY},
                timeout=10,
            )
            data = resp.json()

            if data['status'] == 'success':
                self.root.after(0, self._on_register_success, name)
            else:
                self.root.after(0, self._on_register_error, data['message'])

        except requests.exceptions.ConnectionError:
            self.root.after(
                0, self._on_register_error, "サーバーに接続できません"
            )
        except requests.exceptions.Timeout:
            self.root.after(
                0, self._on_register_error, "タイムアウトしました"
            )
        except Exception as e:
            self.root.after(0, self._on_register_error, str(e))

    def _on_register_success(self, name: str):
        self.result_var.set(f"?  {name} を登録しました")
        self._set_status("カードをタッチしてください", "#1565C0")
        self._reset()

    def _on_register_error(self, message: str):
        self.result_var.set(f"?  {message}")
        self._set_status("カードをタッチしてください", "#1565C0")
        self.btn_register.config(state='normal')

    # ─────────────────────────────────
    # ユーティリティ
    # ─────────────────────────────────
    def _set_status(self, text: str, color: str = "#1565C0"):
        self.status_var.set(text)

    def _reset(self):
        """フォームをリセットして次の登録待ちに戻る"""
        self.card_id = None
        self.card_id_var.set("")
        self.name_var.set("")
        self.email_var.set("")
        self.btn_register.config(state='disabled')
        self.result_var.set("")

    def on_close(self):
        self._reading = False
        self.root.destroy()


# ──────────────────────────────────────────────
# 起動
# ──────────────────────────────────────────────
if __name__ == '__main__':
    root = tk.Tk()
    app  = CardRegisterApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()