"""
Telegram Bot - Supabase Veritabanlı Sürüm
==========================================
Veriler artık Supabase'de kalıcı olarak saklanıyor.
Render yeniden başlasa bile veriler kaybolmaz.
"""

import logging
import os
from datetime import datetime
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from supabase import create_client, Client
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

# Supabase ayarları
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

PORT = int(os.environ.get("PORT", "10000"))

BONUS_TEXT = (
    "🎁 *TELEGRAM BONUSU* 🎁\n\n"
    "Tebrikler! Kanal üyeliğin doğrulandı.\n\n"
    "🎟️ *Bonus Kodu:* `BIGWIN2026`\n\n"
    "Bu kodu sitemizdeki bonus alanına girerek bonusunu talep edebilirsin.\n\n"
    "İyi şanslar! 🍀"
)
# =============================================

WAITING_BROADCAST = 1

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Supabase client başlat
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu.")
    except Exception as e:
        logger.error(f"Supabase bağlantı hatası: {e}")


# ---------- Veritabanı Fonksiyonları ----------

def register_user(user) -> None:
    """Kullanıcıyı veritabanına kaydet (varsa atla)"""
    if not supabase:
        return
    try:
        # upsert: varsa güncelle, yoksa ekle
        supabase.table("users").upsert({
            "user_id": user.id,
            "first_name": user.first_name or "",
            "username": user.username or "",
        }, on_conflict="user_id", ignore_duplicates=True).execute()
    except Exception as e:
        logger.error(f"Kullanıcı kaydı hatası: {e}")


def increment_click(button_name: str) -> None:
    """Buton tıklama sayısını artır"""
    if not supabase:
        return
    try:
        # Mevcut değeri al
        result = supabase.table("button_clicks").select("click_count").eq("button_name", button_name).execute()
        current = result.data[0]["click_count"] if result.data else 0
        # Güncelle
        supabase.table("button_clicks").upsert({
            "button_name": button_name,
            "click_count": current + 1,
        }, on_conflict="button_name").execute()
    except Exception as e:
        logger.error(f"Click sayısı artırma hatası: {e}")


def record_bonus(user) -> None:
    """Bonus alan kişiyi kaydet"""
    if not supabase:
        return
    try:
        supabase.table("bonus_receivers").upsert({
            "user_id": user.id,
            "first_name": user.first_name or "",
            "username": user.username or "",
        }, on_conflict="user_id", ignore_duplicates=True).execute()
    except Exception as e:
        logger.error(f"Bonus kaydı hatası: {e}")


def get_total_users() -> int:
    if not supabase:
        return 0
    try:
        result = supabase.table("users").select("user_id", count="exact").execute()
        return result.count or 0
    except Exception as e:
        logger.error(f"Kullanıcı sayısı alma hatası: {e}")
        return 0


def get_total_bonus() -> int:
    if not supabase:
        return 0
    try:
        result = supabase.table("bonus_receivers").select("user_id", count="exact").execute()
        return result.count or 0
    except Exception as e:
        logger.error(f"Bonus sayısı alma hatası: {e}")
        return 0


def get_button_clicks() -> dict:
    if not supabase:
        return {}
    try:
        result = supabase.table("button_clicks").select("*").execute()
        return {row["button_name"]: row["click_count"] for row in (result.data or [])}
    except Exception as e:
        logger.error(f"Click sayıları alma hatası: {e}")
        return {}


def get_all_bonus_receivers() -> list:
    if not supabase:
        return []
    try:
        result = supabase.table("bonus_receivers").select("*").order("received_at").execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Bonus listesi alma hatası: {e}")
        return []


def get_all_user_ids() -> list:
    if not supabase:
        return []
    try:
        result = supabase.table("users").select("user_id").execute()
        return [row["user_id"] for row in (result.data or [])]
    except Exception as e:
        logger.error(f"Kullanıcı listesi alma hatası: {e}")
        return []


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
        [InlineKeyboardButton("🌐 Güncel Giriş", url=GUNCEL_GIRIS_LINK)],
        [InlineKeyboardButton("📱 Telegram Adresi", url=TELEGRAM_ADRES_LINK)],
        [InlineKeyboardButton("🎁 Telegram Bonusu", callback_data="bonus")],
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

    total_users = get_total_users()
    total_bonus = get_total_bonus()
    clicks = get_button_clicks()

    text = (
        "🛠️ *YÖNETİCİ PANELİ*\n\n"
        f"👥 *Toplam Kullanıcı:* {total_users}\n"
        f"🎁 *Bonus Alan:* {total_bonus}\n\n"
        f"📊 *Bonus Buton Tıklaması:* {clicks.get('bonus', 0)}\n\n"
        f"_(Not: Güncel Giriş ve Telegram Adresi direkt link açan butonlar olduğu için tıklamaları sayılamıyor.)_\n\n"
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

    receivers = get_all_bonus_receivers()
    if not receivers:
        await update.message.reply_text("📭 Henüz bonus alan kimse yok.")
        return

    lines = [f"🎁 *BONUS ALAN KİŞİLER ({len(receivers)} kişi)*\n"]
    for i, info in enumerate(receivers, 1):
        name = info.get("first_name") or "?"
        username = f"@{info['username']}" if info.get("username") else "(kullanıcı adı yok)"
        date = (info.get("received_at") or "")[:10]
        uid = info.get("user_id", "")
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
    user_ids = get_all_user_ids()

    if not user_ids:
        await update.message.reply_text("📭 Gönderilecek kullanıcı yok.")
        return ConversationHandler.END

    await update.message.reply_text(f"⏳ {len(user_ids)} kullanıcıya mesaj gönderiliyor...")
    success = 0
    failed = 0
    for uid in user_ids:
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

HEALTH_HTML = """<!DOCTYPE html>
<html>
<head><title>Bot Status</title></head>
<body style="font-family: Arial; text-align: center; padding: 50px; background: #1a1a1a; color: #fff;">
    <h1>🤖 Telegram Bot</h1>
    <p style="color: #4CAF50; font-size: 24px;">✅ Çalışıyor</p>
    <p>Bot 7/24 aktif durumda.</p>
</body>
</html>
"""


class HealthHandler(BaseHTTPRequestHandler):
    def _send_headers(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HEALTH_HTML.encode("utf-8"))))
        self.end_headers()

    def do_GET(self):
        self._send_headers()
        self.wfile.write(HEALTH_HTML.encode("utf-8"))

    def do_HEAD(self):
        self._send_headers()

    def log_message(self, format, *args):
        return


def run_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Web sunucusu {PORT} portunda başladı")
    server.serve_forever()


# ---------- Ana Fonksiyon ----------

def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable'i ayarlanmamış!")
        raise SystemExit("BOT_TOKEN bulunamadı.")

    if not supabase:
        logger.warning("⚠️ Supabase bağlantısı yok! Veriler saklanamayacak.")

    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()

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

    logger.info("Bot başlatıldı.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
