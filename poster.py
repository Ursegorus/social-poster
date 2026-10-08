import sys; sys.stdout.reconfigure(encoding="utf-8")
"""social-poster: публикация постов в Telegram, VK, Max. YouTube — через браузер (API нет).

Пост = markdown-файл в queue/ с шапкой:
---
status: draft | approved | published
platforms: tg, vk, max
image: путь/к/картинке.jpg   # необязательно
---
Текст поста

Использование:
  python poster.py list
  python poster.py preview queue/x.md        # шлёт черновик ТОЛЬКО владельцу в TG
  python poster.py publish queue/x.md        # dry-run: показывает, что уйдёт
  python poster.py publish queue/x.md --send # реальная отправка (только status: approved)
"""
import json, os, re, sys, urllib.parse, urllib.request, urllib.error, uuid
from pathlib import Path

ROOT = Path(__file__).parent
MAX_API = "https://platform-api2.max.ru"


def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def parse(path):
    raw = Path(path).read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    meta, body = {}, raw
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return meta, body.strip()


def set_status(path, status):
    raw = Path(path).read_text(encoding="utf-8")
    raw = re.sub(r"(?m)^status:.*$", f"status: {status}", raw, count=1)
    Path(path).write_text(raw, encoding="utf-8")


def set_field(path, key, value):
    raw = Path(path).read_text(encoding="utf-8")
    if re.search(rf"(?m)^{key}:", raw):
        raw = re.sub(rf"(?m)^{key}:.*$", f"{key}: {value}", raw, count=1)
    else:
        raw = raw.replace("\n---\n", f"\n{key}: {value}\n---\n", 1)
    Path(path).write_text(raw, encoding="utf-8")


def http(url, data=None, headers=None, method=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode("utf-8", "replace")[:300]}


def multipart(fields, files):
    b = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (name, content) in files.items():
        out += (f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                f'Content-Type: application/octet-stream\r\n\r\n').encode() + content + b"\r\n"
    out += f"--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"


def split(text, n):
    parts = []
    while len(text) > n:
        cut = text.rfind("\n", 0, n)
        cut = cut if cut > n // 2 else n
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    return parts + [text]


def to_html(t):
    import html
    t = html.escape(t, quote=False)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)


def images_of(image):
    return [x.strip() for x in (image or "").split(",") if x.strip()]


def tg_send(chat, text, image=None):
    tok = os.environ["TG_BOT_TOKEN"]
    base = f"https://api.telegram.org/bot{tok}"
    imgs = images_of(image)
    if len(imgs) == 1:  # подпись в фото <=1024
        cap, rest = to_html(text[:1024]), text[1024:]
        body, ct = multipart({"chat_id": chat, "caption": cap, "parse_mode": "HTML"},
                             {"photo": (Path(imgs[0]).name, Path(imgs[0]).read_bytes())})
        res = http(f"{base}/sendPhoto", body, {"Content-Type": ct})
        if rest and "error" not in res:
            tg_send(chat, rest)
        return res
    if len(imgs) > 1:  # альбом до 10 фото, подпись на первом
        cap, rest = to_html(text[:1024]), text[1024:]
        media, files = [], {}
        for i, f in enumerate(imgs[:10]):
            item = {"type": "photo", "media": f"attach://f{i}"}
            if i == 0:
                item.update(caption=cap, parse_mode="HTML")
            media.append(item)
            files[f"f{i}"] = (Path(f).name, Path(f).read_bytes())
        body, ct = multipart({"chat_id": chat, "media": json.dumps(media)}, files)
        res = http(f"{base}/sendMediaGroup", body, {"Content-Type": ct})
        if rest and "error" not in res:
            tg_send(chat, rest)
        return res
    res = {}
    for chunk in split(text, 4096):
        res = http(f"{base}/sendMessage", json.dumps({"chat_id": chat, "text": to_html(chunk), "parse_mode": "HTML"}).encode(),
                   {"Content-Type": "application/json"})
    return res


def vk_send(group_id, text, image=None):
    tok, v = os.environ["VK_TOKEN"], "5.199"
    def call(method, **p):
        p.update(access_token=tok, v=v)
        return http(f"https://api.vk.com/method/{method}", urllib.parse.urlencode(p).encode())
    p = dict(owner_id=f"-{group_id}", from_group=1, message=text)
    atts = []
    for img in images_of(image):
        up = call("photos.getWallUploadServer", group_id=group_id)
        url = up.get("response", {}).get("upload_url")
        if not url:
            return up
        body, ct = multipart({}, {"photo": (Path(img).name, Path(img).read_bytes())})
        u = http(url, body, {"Content-Type": ct})
        sv = call("photos.saveWallPhoto", group_id=group_id, photo=u["photo"], server=u["server"], hash=u["hash"])
        ph = sv["response"][0]
        atts.append(f"photo{ph['owner_id']}_{ph['id']}")
    if atts:
        p["attachments"] = ",".join(atts)
    return call("wall.post", **p)


def max_send(chat, text, image=None):
    if image:
        print("  (Max: картинки пока не поддерживаются, отправляю текст)")
    h = {"Authorization": os.environ["MAX_BOT_TOKEN"], "Content-Type": "application/json"}
    res = {}
    for chunk in split(text, 4000):
        res = http(f"{MAX_API}/messages?chat_id={chat}", json.dumps({"text": chunk, "format": "markdown"}).encode(), h)
    return res


PLATFORMS = {  # имя -> (функция, переменная со списком получателей)
    "tg": (tg_send, "TG_TARGETS"), "vk": (vk_send, "VK_GROUP_IDS"), "max": (max_send, "MAX_CHAT_IDS"),
}


def targets(var):
    return [x.strip() for x in os.environ.get(var, "").split(",") if x.strip()]


def main():
    load_env()
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == "list":
        for f in sorted((ROOT / "queue").glob("*.md")):
            m, _ = parse(f)
            print(f"{m.get('status','?'):10} {m.get('platforms','')}\t{f.name}")
        return
    if cmd == "preview-new":  # все draft без previewed -> владельцу с кнопками
        import subprocess
        for f in sorted((ROOT / "queue").glob("*.md")):
            m, _ = parse(f)
            if m.get("status") == "draft" and m.get("previewed") != "yes" and not f.name.startswith("_"):
                subprocess.run([sys.executable, __file__, "preview", str(f)], check=False)
        return
    meta, text = parse(a[1])
    image = meta.get("image") or None
    if cmd == "preview":
        owner = os.environ["TG_OWNER_CHAT"]
        r = tg_send(owner, text, image)  # черновик ровно в том виде, как уйдёт в канал
        stem = Path(a[1]).stem
        tok = os.environ["TG_BOT_TOKEN"]
        kb = {"inline_keyboard": [[{"text": "✅ Опубликовать", "callback_data": f"p:{stem}"},
                                   {"text": "❌ Отклонить", "callback_data": f"r:{stem}"}]]}
        targets_txt = ", ".join(targets("TG_TARGETS")) or "каналы не заданы"
        r2 = http(f"https://api.telegram.org/bot{tok}/sendMessage", json.dumps(
            {"chat_id": owner, "text": f"Черновик «{stem}». Опубликовать в {targets_txt}?", "reply_markup": kb}).encode(),
            {"Content-Type": "application/json"})
        if "error" not in r and "error" not in r2:
            set_field(a[1], "previewed", "yes")
        print("ok" if "error" not in r and "error" not in r2 else (r, r2)); return
    if cmd == "publish":
        send = "--send" in a
        if send and meta.get("status") != "approved":
            sys.exit("Отказ: status не approved. Сначала согласование.")
        failed = False
        for name in [p.strip() for p in meta.get("platforms", "").split(",") if p.strip()]:
            if name == "yt":
                print("yt: через браузер (Claude в Chrome), здесь пропуск"); continue
            fn, var = PLATFORMS[name]
            for t in targets(var):
                if not send:
                    print(f"[dry-run] {name} -> {t}: {len(text)} симв., image={image}"); continue
                r = fn(t, text, image)
                ok = "error" not in r and not (name == "vk" and "error" in r)
                failed |= not ok
                print(f"{name} -> {t}:", "ok" if ok else r)
        if send and not failed:
            set_status(a[1], "published")
        return
    print(__doc__)


if __name__ == "__main__":
    main()
