"""Одноразовая проверка нажатий кнопок (для GitHub Actions по cron). Без состояния:
забирает callback_query, обрабатывает, подтверждает offset."""
import sys
import poster
from bot_approve import api, handle

poster.load_env()
sys.stdout.reconfigure(encoding="utf-8")
offset = None
while True:
    r = api("getUpdates", offset=offset, timeout=0, allowed_updates=["callback_query"])
    if "error" in r or not r.get("ok", True):
        print("ОШИБКА Telegram:", str(r)[:200])
    ups = r.get("result", [])
    print("обновлений:", len(ups))
    if not ups:
        break
    for u in ups:
        offset = u["update_id"] + 1
        if "callback_query" in u:
            print("кнопка:", u["callback_query"]["data"])
            handle(u["callback_query"])
if offset:
    api("getUpdates", offset=offset, timeout=0, allowed_updates=["callback_query"])  # подтвердить
print("готово")
