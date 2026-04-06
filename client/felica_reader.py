import nfc
import requests
import sys
import time
import urllib3
from datetime import datetime
import logging
import argparse

# SSL警告の制御
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('attendance_reader.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ========================
# 設定
# ========================
# サーバーURL・APIキーは起動時の引数で指定
# 引数なしの場合はここのデフォルト値が使用される
DEFAULT_SERVER_URL = 'https://your-domain.com'
DEFAULT_API_KEY    = 'your-api-key-here'  # config.pyのAPI_KEYと同じ値を設定


class FelicaReader:
    def __init__(self, terminal_type='IN', server_url=DEFAULT_SERVER_URL,
                 api_key=DEFAULT_API_KEY, verify_ssl=True):
        self.terminal_type = terminal_type
        self.server_url    = server_url
        self.api_key       = api_key
        self.verify_ssl    = verify_ssl

    def on_connect(self, tag):
        try:
            # Felica ID取得
            if hasattr(tag, 'idm'):
                felica_id = tag.idm.hex().upper()
            elif hasattr(tag, 'identifier'):
                felica_id = tag.identifier.hex().upper()
            else:
                logging.warning("Felica IDを取得できませんでした")
                return True

            timestamp = datetime.now().isoformat()

            data = {
                'felica_id':   felica_id,
                'log_type':    self.terminal_type,
                'timestamp':   timestamp,
                'terminal_id': f'TERM_{self.terminal_type}_01'
            }

            # APIキーをヘッダーに付与してPOST
            response = requests.post(
                f'{self.server_url}/api/log',
                json=data,
                headers={'X-API-Key': self.api_key},
                verify=self.verify_ssl,
                timeout=10
            )

            if response.status_code == 200:
                print(f"? {self.terminal_type}: {felica_id} at {timestamp}")
                logging.info(f"Success - {self.terminal_type}: {felica_id}")

            elif response.status_code == 401:
                print(f"? 認証エラー: APIキーを確認してください")
                logging.error(f"API key error: {response.json()}")

            elif response.status_code == 404:
                print(f"? 未登録カード: {felica_id}")
                logging.warning(f"Unregistered card: {felica_id}")

            else:
                print(f"? サーバーエラー: {response.status_code}")
                logging.error(f"Server error: {response.status_code} - {response.text}")

        except requests.exceptions.SSLError as e:
            print(f"? SSLエラー: {e}")
            logging.error(f"SSL error: {e}")
        except requests.exceptions.ConnectionError as e:
            print(f"? 接続エラー: {e}")
            logging.error(f"Connection error: {e}")
        except requests.exceptions.Timeout:
            print("? タイムアウト")
            logging.error("Request timeout")
        except Exception as e:
            print(f"? 予期せぬエラー: {e}")
            logging.error(f"Unexpected error: {e}")

        return True

    def start_reading(self):
        retry_count = 0
        max_retries = 5

        print(f"=================================")
        print(f"  {self.terminal_type} 端末起動")
        print(f"  サーバー: {self.server_url}")
        print(f"  SSL検証: {self.verify_ssl}")
        print(f"=================================")
        print(f"カードをタッチしてください...")
        print(f"終了する場合は Ctrl+C を押してください")
        logging.info(f"Terminal started - Type: {self.terminal_type}")

        while True:
            try:
                with nfc.ContactlessFrontend('usb') as clf:
                    if clf is None:
                        raise Exception("NFCデバイスを開けません")

                    retry_count = 0
                    clf.connect(rdwr={'on-connect': self.on_connect})

            except KeyboardInterrupt:
                print("\n?? 終了します")
                logging.info("Application terminated by user")
                break
            except Exception as e:
                retry_count += 1
                logging.error(f"Reader error (attempt {retry_count}): {e}")

                if retry_count >= max_retries:
                    print(f"? 最大再試行回数に達しました")
                    logging.critical("Max retries reached, exiting")
                    break

                print(f"? エラー (再試行 {retry_count}/{max_retries}): {e}")
                time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description='FeliCa勤怠リーダー')
    parser.add_argument(
        'type',
        choices=['IN', 'OUT'],
        help='端末タイプ'
    )
    parser.add_argument(
        '--server',
        default=DEFAULT_SERVER_URL,
        help=f'サーバーURL (デフォルト: {DEFAULT_SERVER_URL})'
    )
    parser.add_argument(
        '--api-key',
        default=DEFAULT_API_KEY,
        help='APIキー'
    )
    parser.add_argument(
        '--no-ssl-verify',
        action='store_true',
        help='SSL証明書検証を無効化'
    )
    args = parser.parse_args()

    reader = FelicaReader(
        terminal_type=args.type,
        server_url=args.server,
        api_key=args.api_key,
        verify_ssl=not args.no_ssl_verify
    )
    reader.start_reading()


if __name__ == '__main__':
    main()