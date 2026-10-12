"""Обработка ОДНОГО нажатия кнопки (вызывается Action approve.yml из Worker): data, chat_id, message_id."""
import os, sys
import poster
from bot_approve import handle

poster.load_env()
data, chat, mid = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
handle({"id": "0", "from": {"id": int(os.environ["TG_OWNER_CHAT"])}, "data": data,
        "message": {"chat": {"id": chat}, "message_id": mid}})
print("обработано:", data)
