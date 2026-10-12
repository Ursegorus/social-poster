// Telegram webhook: нажатие кнопки -> мгновенный ответ -> запуск GitHub Action approve.yml
const REPO = "Ursegorus/social-poster";

async function tg(env, method, body) {
  return fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export default {
  async fetch(req, env) {
    if (req.method !== "POST") return new Response("ok");
    if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const u = await req.json();
    const cb = u.callback_query;
    if (!cb) return new Response("ok");
    if (String(cb.from.id) !== String(env.OWNER_ID)) {
      await tg(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Нет доступа" });
      return new Response("ok");
    }
    await tg(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Принято, обрабатываю…" });
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/approve.yml/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "social-poster-tg",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          data: cb.data,
          chat_id: String(cb.message.chat.id),
          message_id: String(cb.message.message_id),
        },
      }),
    });
    if (!r.ok) {
      await tg(env, "sendMessage", { chat_id: cb.message.chat.id, text: `⚠️ Не удалось запустить публикацию: GitHub ${r.status}` });
    }
    return new Response("ok");
  },
};
