"""Слушатель кнопок одобрения. Реагирует ТОЛЬКО на callback_query от владельца (TG_OWNER_CHAT).
Нажатие ✅ -> status approved -> publish --send по платформам из шапки. ❌ -> status rejected.
Запуск: python bot_approve.py   (long polling; обычные сообщения боту игнорируются)
"""
import json, os, subprocess, sys, time
from pathlib import Path
import poster

ROOT = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8")


def api(method, _timeout=30, **p):
    tok = os.environ["TG_BOT_TOKEN"]
    return poster.http(f"https://api.telegram.org/bot{tok}/{method}", json.dumps(p).encode(),
                       {"Content-Type": "application/json"}, timeout=_timeout)


def handle(cb):
    owner = int(os.environ["TG_OWNER_CHAT"])
    if cb["from"]["id"] != owner:
        api("answerCallbackQuery", callback_query_id=cb["id"], text="Нет доступа"); return
    action, _, stem = cb["data"].partition(":")
    f = ROOT / "queue" / f"{stem}.md"
    chat, mid = cb["message"]["chat"]["id"], cb["message"]["message_id"]
    if not f.exists():
        api("answerCallbackQuery", callback_query_id=cb["id"], text="Файл не найден"); return
    status = poster.parse(f)[0].get("status")
    if status in ("published", "rejected"):
        api("answerCallbackQuery", callback_query_id=cb["id"], text=f"Уже: {status}"); return
    if action == "r":
        poster.set_status(f, "rejected")
        api("answerCallbackQuery", callback_query_id=cb["id"], text="Отклонено")
        api("editMessageText", chat_id=chat, message_id=mid, text=f"❌ Отклонено: {stem}"); return
    poster.set_status(f, "approved")
    res = subprocess.run([sys.executable, str(ROOT / "poster.py"), "publish", str(f), "--send"],
                         capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    ok = res.returncode == 0 and "error" not in res.stdout.lower() and "'ok': false" not in res.stdout.lower()
    done = poster.parse(f)[0].get("status") == "published"
    api("answerCallbackQuery", callback_query_id=cb["id"], text="Опубликовано" if done else "Ошибка")
    api("editMessageText", chat_id=chat, message_id=mid,
        text=(f"✅ Опубликовано: {stem}" if done else f"⚠️ Не опубликовано: {stem}\n{res.stdout[-300:]}"))


def main():
    poster.load_env()
    offset = None
    print("слушаю кнопки…", flush=True)
    while True:
        try:
            r = api("getUpdates", _timeout=70, offset=offset, timeout=50, allowed_updates=["callback_query"])
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                if "callback_query" in u:
                    handle(u["callback_query"])
            if "error" in r:
                time.sleep(10)
        except Exception as e:
            print("ошибка:", repr(e)[:150], flush=True); time.sleep(10)


if __name__ == "__main__":
    main()
