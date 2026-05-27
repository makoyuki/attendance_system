import nfc
import requests
import sys
import time
import urllib3
import threading
import signal
import os
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime
import logging
import argparse

# pygameは音声のみに使用
try:
    import pygame
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False
    logging.warning("pygameが見つかりません。音声機能は無効です。")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('attendance_reader.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

try:
    from config import SERVER_URL as DEFAULT_SERVER_URL
    from config import API_KEY    as DEFAULT_API_KEY
except ImportError:
    DEFAULT_SERVER_URL = 'https://mc.fnow.org'
    DEFAULT_API_KEY    = 'your-api-key-here'

# ========================
# 音声の初期化
# ========================
def init_sound():
    if not SOUND_AVAILABLE:
        return None
    try:
        pygame.mixer.init()
        # 音声ファイルがない場合はビープ音で代替
        if os.path.exists('touch.wav'):
            return pygame.mixer.Sound('touch.wav')
        else:
            logging.info("touch.wavが見つかりません。ビープ音を使用します。")
            return None
    except Exception as e:
        logging.warning(f"音声初期化エラー: {e}")
        return None

def play_sound(sound):
    """音声再生（エラーが出ても処理を止めない）"""
    if sound:
        try:
            sound.play()
        except Exception as e:
            logging.warning(f"音声再生エラー: {e}")
    else:
        # pygameがない or ファイルなし → コンソールビープ
        print('\a', end='', flush=True)


# ========================
# GUI クラス
# ========================
class AttendanceDisplay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("勤怠管理システム")
        self.root.configure(bg='#1a1a2e')

        # フルスクリーン対応（必要であればTrueに変更）
        self.fullscreen = False
        self.root.attributes('-fullscreen', self.fullscreen)

        # ウィンドウサイズ
        self.root.geometry('800x480')

        # Escキーでフルスクリーン解除
        self.root.bind('<Escape>', self._toggle_fullscreen)

        self._build_ui()
        self._show_standby()

    def _toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes('-fullscreen', self.fullscreen)

    def _build_ui(self):
        """画面レイアウト構築"""
        # フォント定義
        self.font_large   = tkfont.Font(family='Yu Gothic', size=48, weight='bold')
        self.font_medium  = tkfont.Font(family='Yu Gothic', size=32)
        self.font_small   = tkfont.Font(family='Yu Gothic', size=20)
        self.font_standby = tkfont.Font(family='Yu Gothic', size=24)

        # メインフレーム
        self.frame = tk.Frame(self.root, bg='#1a1a2e')
        self.frame.pack(expand=True, fill='both')

        # 挨拶ラベル
        self.label_greeting = tk.Label(
            self.frame,
            text='',
            font=self.font_medium,
            bg='#1a1a2e',
            fg='#e0e0e0'
        )
        self.label_greeting.pack(pady=(60, 10))

        # 名前ラベル
        self.label_name = tk.Label(
            self.frame,
            text='',
            font=self.font_large,
            bg='#1a1a2e',
            fg='#00d4ff'
        )
        self.label_name.pack(pady=10)

        # ステータスラベル（IN/OUT表示）
        self.label_status = tk.Label(
            self.frame,
            text='',
            font=self.font_small,
            bg='#1a1a2e',
            fg='#a0a0a0'
        )
        self.label_status.pack(pady=10)

        # 時刻ラベル
        self.label_time = tk.Label(
            self.frame,
            text='',
            font=self.font_small,
            bg='#1a1a2e',
            fg='#a0a0a0'
        )
        self.label_time.pack(pady=5)

        # 時計の更新開始
        self._update_clock()

    def _update_clock(self):
        """現在時刻を1秒ごとに更新"""
        now = datetime.now().strftime('%Y年%m月%d日  %H:%M:%S')
        self.label_time.config(text=now)
        self.root.after(1000, self._update_clock)

    def _show_standby(self):
        """待機画面表示"""
        self.label_greeting.config(text='カードをタッチしてください', fg='#a0a0a0',
                                    font=self.font_standby)
        self.label_name.config(text='', fg='#00d4ff')
        self.label_status.config(text='')
        self.root.configure(bg='#1a1a2e')
        self.frame.configure(bg='#1a1a2e')
        for widget in self.frame.winfo_children():
            widget.configure(bg='#1a1a2e')

    def show_success(self, name, greeting, log_type):
        """タッチ成功時の表示"""
        # IN/OUTで背景色を変える
        if log_type == 'IN':
            bg_color = '#0d2b0d'   # 緑系
            name_color = '#00ff88'
        else:
            bg_color = '#2b0d1a'   # 赤系
            name_color = '#ff6688'

        self.root.configure(bg=bg_color)
        self.frame.configure(bg=bg_color)
        for widget in self.frame.winfo_children():
            widget.configure(bg=bg_color)

        self.label_greeting.config(
            text=greeting,
            fg='#ffffff',
            font=self.font_medium
        )
        self.label_name.config(
            text=f'{name} さん',
            fg=name_color
        )
        status_text = '出勤' if log_type == 'IN' else '退勤'
        self.label_status.config(
            text=f'[ {status_text} ]',
            fg='#ffffff'
        )

        # 3秒後に待機画面に戻す
        self.root.after(3000, self._show_standby)

    def show_error(self, message):
        """エラー表示"""
        self.root.configure(bg='#2b1a00')
        self.frame.configure(bg='#2b1a00')
        for widget in self.frame.winfo_children():
            widget.configure(bg='#2b1a00')

        self.label_greeting.config(
            text=message,
            fg='#ff9900',
            font=self.font_medium
        )
        self.label_name.config(text='', fg='#ff9900')
        self.label_status.config(text='')

        # 3秒後に待機画面に戻す
        self.root.after(3000, self._show_standby)

    def update(self, func, *args):
        """スレッドからGUIを安全に更新するためのラッパー"""
        self.root.after(0, func, *args)

    def start(self):
        self.root.mainloop()

    def stop(self):
        self.root.quit()


# ========================
# FeliCaリーダークラス
# ========================
class FelicaReader:
    def __init__(self, terminal_type='IN', server_url=DEFAULT_SERVER_URL,
                 api_key=DEFAULT_API_KEY, verify_ssl=True, display=None, sound=None):
        self.terminal_type = terminal_type
        self.server_url    = server_url
        self.api_key       = api_key
        self.verify_ssl    = verify_ssl
        self.display       = display
        self.sound         = sound
        self.running       = True

    def on_connect(self, tag):
        try:
            if hasattr(tag, 'idm'):
                felica_id = tag.idm.hex().upper()
            elif hasattr(tag, 'identifier'):
                felica_id = tag.identifier.hex().upper()
            else:
                logging.warning("Felica IDを取得できませんでした")
                return True

            # 音声再生（タッチ時）
            play_sound(self.sound)

            timestamp = datetime.now().isoformat()
            data = {
                'felica_id':   felica_id,
                'log_type':    self.terminal_type,
                'timestamp':   timestamp,
                'terminal_id': f'TERM_{self.terminal_type}_01'
            }

            response = requests.post(
                f'{self.server_url}/api/log',
                json=data,
                headers={'X-API-Key': self.api_key},
                verify=self.verify_ssl,
                timeout=10
            )

            if response.status_code == 200:
                res_data = response.json()
                name     = res_data.get('employee_name', '不明')
                greeting = res_data.get('greeting', '')
                log_type = res_data.get('log_type', self.terminal_type)

                print(f"? {log_type}: {name} ({felica_id}) at {timestamp}")
                logging.info(f"Success - {log_type}: {name} ({felica_id})")

                # GUI更新（別スレッドから安全に呼び出し）
                if self.display:
                    self.display.update(
                        self.display.show_success,
                        name, greeting, log_type
                    )

            elif response.status_code == 401:
                msg = '認証エラー: APIキーを確認してください'
                print(f"? {msg}")
                logging.error(f"API key error: {response.json()}")
                if self.display:
                    self.display.update(self.display.show_error, msg)

            elif response.status_code == 404:
                msg = '未登録カードです'
                print(f"? {msg}: {felica_id}")
                logging.warning(f"Unregistered card: {felica_id}")
                if self.display:
                    self.display.update(self.display.show_error, msg)

            else:
                msg = f'サーバーエラー: {response.status_code}'
                print(f"? {msg}")
                logging.error(f"Server error: {response.status_code}")
                if self.display:
                    self.display.update(self.display.show_error, msg)

        except requests.exceptions.ConnectionError:
            msg = 'サーバーに接続できません'
            print(f"? {msg}")
            logging.error("Connection error")
            if self.display:
                self.display.update(self.display.show_error, msg)
        except requests.exceptions.Timeout:
            msg = 'タイムアウト'
            print(f"? {msg}")
            logging.error("Request timeout")
            if self.display:
                self.display.update(self.display.show_error, msg)
        except Exception as e:
            print(f"? 予期せぬエラー: {e}")
            logging.error(f"Unexpected error: {e}")

        return True

    def start_reading(self):
        """NFCリーダーのループ（別スレッドで実行）"""
        retry_count = 0
        max_retries = 5

        logging.info(f"Terminal started - Type: {self.terminal_type}")

        while self.running:
            try:
                with nfc.ContactlessFrontend('usb') as clf:
                    if clf is None:
                        raise Exception("NFCデバイスを開けません")
                    retry_count = 0
                    clf.connect(rdwr={'on-connect': self.on_connect})

            except KeyboardInterrupt:
                break
            except Exception as e:
                if not self.running:
                    break
                retry_count += 1
                logging.error(f"Reader error (attempt {retry_count}): {e}")

                if retry_count >= max_retries:
                    logging.critical("Max retries reached, exiting")
                    if self.display:
                        self.display.update(
                            self.display.show_error,
                            'NFCデバイスエラー\n再起動してください'
                        )
                    break

                time.sleep(5)

    def stop(self):
        self.running = False


# ========================
# メイン
# ========================
def main():

    parser = argparse.ArgumentParser(description='FeliCa勤怠リーダー')
    parser.add_argument('type', choices=['IN', 'OUT'], help='端末タイプ')
    parser.add_argument('--server',       default=DEFAULT_SERVER_URL, help='サーバーURL')
    parser.add_argument('--api-key',      default=DEFAULT_API_KEY,    help='APIキー')
    parser.add_argument('--no-ssl-verify',action='store_true',        help='SSL検証無効化')
    parser.add_argument('--no-gui',       action='store_true',        help='GUI無効化（コンソールのみ）')
    args = parser.parse_args()

    # 音声初期化
    sound = init_sound()

    # GUI初期化
    display = None
    if not args.no_gui:
        display = AttendanceDisplay()
        display.root.title(f"勤怠管理 - {'出勤' if args.type == 'IN' else '退勤'}端末")

    # リーダー初期化
    reader = FelicaReader(
        terminal_type=args.type,
        server_url=args.server,
        api_key=args.api_key,
        verify_ssl=not args.no_ssl_verify,
        display=display,
        sound=sound
    )

    # Ctrl+C ハンドラ
    def signal_handler(sig, frame):
        print("\n終了します...")
        logging.info("Application terminated by user")
        reader.stop()
        if display:
            display.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # NFCリーダーを別スレッドで起動
    reader_thread = threading.Thread(target=reader.start_reading, daemon=True)
    reader_thread.start()

    print(f"=================================")
    print(f"  {args.type} 端末起動")
    print(f"  サーバー: {args.server}")
    print(f"  SSL検証: {not args.no_ssl_verify}")
    print(f"  終了: Ctrl+C")
    print(f"=================================")

    # GUIメインループ（メインスレッドで実行）
    if display:
        display.start()
    else:
        # GUI無効時はスレッドの終了を待機
        try:
            reader_thread.join()
        except KeyboardInterrupt:
            reader.stop()
            sys.exit(0)


if __name__ == '__main__':
    main()