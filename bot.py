import os
import asyncio
import feedparser
import httpx
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY  = os.environ["GEMINI_API_KEY"]
CHAT_ID         = os.environ["CHAT_ID"]

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)

# Danh sách nguồn RSS crypto — thêm/xoá tuỳ ý
RSS_SOURCES = [
    # 📰 Tin tức crypto quốc tế
    {"name": "CoinDesk",        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "CoinTelegraph",   "url": "https://cointelegraph.com/rss"},
    {"name": "CryptoSlate",     "url": "https://cryptoslate.com/feed/"},
    {"name": "Decrypt",         "url": "https://decrypt.co/feed"},
    {"name": "The Block",       "url": "https://www.theblock.co/rss.xml"},

    # 📱 Kênh Telegram (qua RSSHub)
    {"name": "TradeCoin Underground", "url": "https://rsshub.app/telegram/channel/tradecoinundergroundchannel"},
    {"name": "LKS02 Community",       "url": "https://rsshub.app/telegram/channel/LKS02community"},
    {"name": "GTrading Channel",      "url": "https://rsshub.app/telegram/channel/gtradingchannel"},
    {"name": "Hocvien Underground",   "url": "https://rsshub.app/telegram/channel/HocvienUndergroundNew"},
    {"name": "Luca Channel",          "url": "https://rsshub.app/telegram/channel/lucachannel79"},
    {"name": "Ho Van Thuc",           "url": "https://rsshub.app/telegram/channel/hovanthuc"},
    {"name": "Richkid Tradings",      "url": "https://rsshub.app/telegram/channel/Richkidtradings"},
    {"name": "Jess Training",         "url": "https://rsshub.app/telegram/channel/Jesstraining"},
    {"name": "Lucy Zubu UG",          "url": "https://rsshub.app/telegram/channel/LucyZubuUG"},
    {"name": "Binance",               "url": "https://rsshub.app/telegram/channel/binance"},
    {"name": "Crypto Whale",          "url": "https://rsshub.app/telegram/channel/CryptoWhale"},
]

MAX_ARTICLES_PER_SOURCE = 3
sent_urls: set = set()


# ── Tóm tắt bằng Gemini ───────────────────────────────────────────────────────
async def summarize(title: str, content: str) -> str:
    prompt = (
        f"Bài báo tiếng Việt sau đây:\n"
        f"Tiêu đề: {title}\n"
        f"Nội dung: {content[:1500]}\n\n"
        f"Hãy tóm tắt ngắn gọn trong 2-3 câu tiếng Việt, "
        f"nêu bật thông tin quan trọng nhất."
    )
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 300, "temperature": 0.3},
            },
        )
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return "_(Không thể tóm tắt bài này)_"


# ── Thu thập RSS ──────────────────────────────────────────────────────────────
async def fetch_rss() -> list[dict]:
    articles = []
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
                url = entry.get("link", "")
                if url in sent_urls:
                    continue
                articles.append({
                    "source":  src["name"],
                    "title":   entry.get("title", ""),
                    "url":     url,
                    "content": entry.get("summary", entry.get("description", "")),
                })
        except Exception as e:
            print(f"[RSS Error] {src['name']}: {e}")
    return articles


# ── Gửi bản tin ───────────────────────────────────────────────────────────────
async def send_digest(bot: Bot):
    articles = await fetch_rss()
    if not articles:
        await bot.send_message(chat_id=CHAT_ID, text="ℹ️ Không có tin mới.")
        return

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    header = f"📰 *Bản tin tổng hợp* — {now}\n{'─' * 30}"
    await bot.send_message(chat_id=CHAT_ID, text=header, parse_mode="Markdown")

    for art in articles:
        try:
            summary = await summarize(art["title"], art["content"])
            msg = (
                f"🔹 *{art['source']}*\n"
                f"*{art['title']}*\n\n"
                f"{summary}\n\n"
                f"[Đọc thêm]({art['url']})"
            )
            await bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            sent_urls.add(art["url"])
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f"[Send Error] {art['title']}: {e}")


# ── Lệnh bot ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Xin chào! Bot tin tức đang hoạt động.\n\n"
        "📌 Lệnh:\n"
        "/fetch — Lấy tin ngay bây giờ\n"
        "/sources — Xem danh sách nguồn\n"
        "/help — Trợ giúp"
    )

async def cmd_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Đang thu thập tin tức, vui lòng chờ...")
    await send_digest(context.bot)

async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [f"• {s['name']}: {s['url']}" for s in RSS_SOURCES]
    await update.message.reply_text("📡 Nguồn hiện tại:\n" + "\n".join(lines))

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Hướng dẫn sử dụng*\n\n"
        "/fetch — Lấy tin tức ngay\n"
        "/sources — Xem nguồn RSS\n"
        "/start — Khởi động lại\n\n"
        "Bot tự động gửi bản tin mỗi 1 giờ.",
        parse_mode="Markdown",
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("fetch",   cmd_fetch))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("help",    cmd_help))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_digest,
        "interval",
        hours=1,
        args=[app.bot],
        id="news_digest",
    )
    scheduler.start()

    print("✅ Bot đang chạy...")
    app.run_polling()


if __name__ == "__main__":
    main()
