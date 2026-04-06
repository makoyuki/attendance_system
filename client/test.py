import nfc

def on_connect(tag):
    if hasattr(tag, 'idm'):
        felica_id = tag.idm.hex().upper()
    elif hasattr(tag, 'identifier'):
        felica_id = tag.identifier.hex().upper()
    else:
        print('IDを取得できませんでした')
        return True
    
    print(f'カード検出: {felica_id}')
    return True

print('カードをタッチしてください...')
print('終了する場合は Ctrl+C を押してください')

with nfc.ContactlessFrontend('usb') as clf:
    clf.connect(rdwr={'on-connect': on_connect})