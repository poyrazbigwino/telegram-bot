"""
Telegram Bot - Web Service Modu (Render Ücretsiz Uyumlu)
=========================================================
Bot normal işini yapar + aynı zamanda küçük bir web sunucusu açar
(Render bunu "Web Service" sanır ve ücretsiz çalıştırır).

UptimeRobot ile web sayfası 5 dakikada bir ping'lenirse bot 7/24 ayakta kalır.
"""

import logging
import json
import os
import asyncio
from datetime import datetime
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ====== AYARLAR (Environment Variables) ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@kanalinizinkullaniciadi")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/kanalinizinkullaniciadi")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7961574063"))
GUNCEL_GIRIS_LINK = os.environ.get("GUNCEL_GIRIS_LINK", "https://bwino.link/sosyal")
TELEGRAM_ADRES_LINK = os.environ.get("TELEGRAM_ADRES_LINK", "https://t.me/bigwinososyal")

# Render PORT'u otomatik veriyor
PORT = int(os.environ.get("PORT", "10000"))

# Bonus metni
BONUS_TEXT = (
    "🎁 *TELEGRAM BONUSU* 🎁\n\n"
    "Tebrikler! Kanal üyeliğin doğrulandı.\n\n"
    "🎟️ *Bonus Kodu:* `BIGWIN2026`\n\n"
    "Bu kodu sitemizdeki bonus alanına girerek bonusunu talep edebilirsin.\n\n"
    "İyi şanslar! 🍀"
)

STATS_FILE = "stats.json"
# =============================================

WAITING_BROADCAST = 1

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- Veri Yönetimi ----------

def load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "users": {},
        "button_clicks": {
            "guncel_giris": 0,
            "telegram_adresi": 0,
            "bonus": 0,
        },
        "bonus_receivers": {},
    }


def save_stats(stats: dict) -> None:
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def register_user(user) -> None:
    stats = load_stats()
    uid = str(user.id)
    if uid not in stats["users"]:
        stats["users"][uid] = {
            "first_name": user.first_name or "",
            "username": user.username or "",
            "joined_at": datetime.now().isoformat(),
        }
        save_stats(stats)


def increment_click(button_name: str) -> None:
    stats = load_stats()
    stats["button_clicks"][button_name] = stats["button_clicks"].get(button_name, 0) + 1
    save_stats(stats)


def record_bonus(user) -> None:
    stats = load_stats()
    uid = str(user.id)
    if uid not in stats["bonus_receivers"]:
        stats["bonus_receivers"][uid] = {
            "first_name": user.first_name or "",
            "username": user.username or "",
            "received_at": datetime.now().isoformat(),
        }
        save_stats(stats)


# ---------- Yardımcı Fonksiyonlar ----------

async def is_user_in_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        ]
    except Exception as e:
        logger.error(f"Üyelik kontrolünde hata: {e}")
        return False


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🌐 Güncel Giriş", callback_data="guncel_giris")],
        [InlineKeyboardButton("📱 Telegram Adresi", callback_data="telegram_adresi")],
        [InlineKeyboardButton("🎁 Telegram Bonusu", callback_data="bonus")],
    ]
    return InlineKeyboardMarkup(keyboard)


def link_keyboard(url: str, label: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(label, url=url)],
        [InlineKeyboardButton("⬅️ Ana Menü", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def join_channel_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📢 Kanala Katıl", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Üyeliğimi Kontrol Et", callback_data="bonus")],
        [InlineKeyboardButton("⬅️ Ana Menü", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("⬅️ Ana Menü", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)


# ---------- Kullanıcı Komutları ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    register_user(user)
    welcome_text = (
        f"👋 Merhaba {user.first_name}!\n\n"
        f"Aşağıdaki menüden istediğin seçeneğe tıklayabilirsin:"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    register_user(user)

    if query.data == "main_menu":
        await query.edit_message_text(
            f"👋 Merhaba {user.first_name}!\n\n"
            f"Aşağıdaki menüden istediğin seçeneğe tıklayabilirsin:",
            reply_markup=main_menu_keyboard(),
        )
        return

    if query.data == "guncel_giris":
        increment_click("guncel_giris")
        await query.edit_message_text(
            "🌐 *Güncel Giriş*\n\n"
            "Aşağıdaki butona tıklayarak siteye gidebilirsin:",
            reply_markup=link_keyboard(GUNCEL_GIRIS_LINK, "🔗 Siteye Git"),
            parse_mode="Markdown",
        )
        return

    if query.data == "telegram_adresi":
        increment_click("telegram_adresi")
        await query.edit_message_text(
            "📱 *Telegram Adresi*\n\n"
            "Aşağıdaki butona tıklayarak Telegram kanalına gidebilirsin:",
            reply_markup=link_keyboard(TELEGRAM_ADRES_LINK, "🔗 Kanala Git"),
            parse_mode="Markdown",
        )
        return

    if query.data == "bonus":
        increment_click("bonus")
        is_member = await is_user_in_channel(context, user.id)
        if not is_member:
            await query.edit_message_text(
                "❌ *Bonus alabilmek için önce kanalımıza katılman gerekiyor!*\n\n"
                "1. Aşağıdaki 'Kanala Katıl' butonuna bas\n"
                "2. Kanala katıl\n"
                "3. 'Üyeliğimi Kontrol Et' butonuna bas",
                reply_markup=join_channel_keyboard(),
                parse_mode="Markdown",
            )
            return

        record_bonus(user)
        await query.edit_message_text(
            BONUS_TEXT,
            reply_markup=back_keyboard(),
            parse_mode="Markdown",
        )


# ---------- Yönetici Komutları ----------

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return

    stats = load_stats()
    total_users = len(stats["users"])
    total_bonus = len(stats["bonus_receivers"])
    clicks = stats["button_clicks"]

    text = (
        "🛠️ *YÖNETİCİ PANELİ*\n\n"
        f"👥 *Toplam Kullanıcı:* {total_users}\n"
        f"🎁 *Bonus Alan:* {total_bonus}\n\n"
        f"📊 *Buton Tıklamaları:*\n"
        f"  🌐 Güncel Giriş: {clicks.get('guncel_giris', 0)}\n"
        f"  📱 Telegram Adresi: {clicks.get('telegram_adresi', 0)}\n"
        f"  🎁 Telegram Bonusu: {clicks.get('bonus', 0)}\n\n"
        f"📋 *Komutlar:*\n"
        f"/bonuslist - Bonus alanların listesi\n"
        f"/broadcast - Tüm kullanıcılara mesaj gönder"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def bonus_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return

    stats = load_stats()
    receivers = stats["bonus_receivers"]
    if not receivers:
        await update.message.reply_text("📭 Henüz bonus alan kimse yok.")
        return

    lines = [f"🎁 *BONUS ALAN KİŞİLER ({len(receivers)} kişi)*\n"]
    for i, (uid, info) in enumerate(receivers.items(), 1):
        name = info.get("first_name", "?")
        username = f"@{info['username']}" if info.get("username") else "(kullanıcı adı yok)"
        date = info.get("received_at", "")[:10]
        lines.append(f"{i}. {name} - {username}\n   ID: `{uid}` - {date}")

    full_text = "\n".join(lines)
    if len(full_text) > 4000:
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 2 > 4000:
                chunks.append(current)
                current = line
            else:
                current += "\n" + line if current else line
        if current:
            chunks.append(current)
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(full_text, parse_mode="Markdown")


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 *Toplu Mesaj Gönderme*\n\n"
        "Tüm kullanıcılara göndermek istediğin mesajı yaz.\n"
        "İptal için /cancel yaz.",
        parse_mode="Markdown",
    )
    return WAITING_BROADCAST


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text
    stats = load_stats()
    users = stats["users"]
    if not users:
        await update.message.reply_text("📭 Gönderilecek kullanıcı yok.")
        return ConversationHandler.END

    await update.message.reply_text(f"⏳ {len(users)} kullanıcıya mesaj gönderiliyor...")
    success = 0
    failed = 0
    for uid in users.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=message_text)
            success += 1
        except Exception as e:
            logger.warning(f"Mesaj gönderilemedi ({uid}): {e}")
            failed += 1

    await update.message.reply_text(
        f"✅ Toplu mesaj tamamlandı!\n\n"
        f"✔️ Başarılı: {success}\n"
        f"❌ Başarısız: {failed}"
    )
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Toplu mesaj iptal edildi.")
    return ConversationHandler.END


# ---------- Web Server (UptimeRobot için) ----------

class HealthHandler(BaseHTTPRequestHandler):
    """Basit HTTP sunucusu - UptimeRobot'un ping atması için"""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Bot Status</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px; background: #1a1a1a; color: #fff;">
            <h1>🤖 Telegram Bot</h1>
            <p style="color: #4CAF50; font-size: 24px;">✅ Çalışıyor</p>
            <p>Bot 7/24 aktif durumda.</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        # Web logları gereksiz, sadece bot logları görünsün
        return


def run_web_server():
    """Web sunucusunu ayrı bir thread'de çalıştır"""
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Web sunucusu {PORT} portunda başladı")
    server.serve_forever()


# ---------- Ana Fonksiyon ----------

def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable'i ayarlanmamış!")
        raise SystemExit("BOT_TOKEN bulunamadı. Lütfen environment variable olarak ekleyin.")

    # Web sunucusunu ayrı thread'de başlat
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()

    # Telegram botu başlat
    application = Application.builder().token(BOT_TOKEN).build()

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            WAITING_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)
            ],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )

    application.add_handler(broadcast_conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("bonuslist", bonus_list))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot başlatıldı. Durdurmak için Ctrl+C basın.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
