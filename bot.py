"""
Telegram Bot - Supabase + Site Kullanıcı Adı
=============================================
Özellikler:
- 3 butonlu menü (Güncel Giriş / Telegram Adresi / Telegram Bonusu)
- Bonus için kanal üyeliği kontrolü
- Bonus için site kullanıcı adı talebi
- Veriler Supabase'de kalıcı
- Admin'e anlık bildirim
"""

import logging
import os
import re
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

# ====== AYARLAR ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@kanalinizinkullaniciadi")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/kanalinizinkullaniciadi")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7961574063"))
GUNCEL_GIRIS_LINK = os.environ.get("GUNCEL_GIRIS_LINK", "https://bwino.link/sosyal")
TELEGRAM_ADRES_LINK = os.environ.get("TELEGRAM_ADRES_LINK", "https://t.me/bigwinososyal")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

PORT = int(os.environ.get("PORT", "10000"))

BONUS_TEXT = (
    "🎁 *TELEGRAM BONUSU* 🎁\n\n"
    "Tebrikler! Bonus talebin alındı.\n\n"
    "🎟️ *Bonus Kodu:* `winoTG05RDx`\n\n"
    "Bu kodu sitemizdeki bonus alanına girerek bonusunu talep edebilirsin.\n\n"
    "İyi şanslar! 🍀"
)
# =====================

# Konuşma durumları
WAITING_BROADCAST = 1
WAITING_USERNAME = 2

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Supabase client
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu.")
    except Exception as e:
        logger.error(f"Supabase bağlantı hatası: {e}")


# ---------- Veritabanı Fonksiyonları ----------

def register_user(user) -> None:
    if not supabase:
        return
    try:
        supabase.table("users").upsert({
            "user_id": user.id,
            "first_name": user.first_name or "",
            "username": user.username or "",
        }, on_conflict="user_id", ignore_duplicates=True).execute()
    except Exception as e:
        logger.error(f"Kullanıcı kaydı hatası: {e}")


def increment_click(button_name: str) -> None:
    if not supabase:
        return
    try:
        result = supabase.table("button_clicks").select("click_count").eq("button_name", button_name).execute()
        current = result.data[0]["click_count"] if result.data else 0
        supabase.table("button_clicks").upsert({
            "button_name": button_name,
            "click_count": current + 1,
        }, on_conflict="button_name").execute()
    except Exception as e:
        logger.error(f"Click sayısı artırma hatası: {e}")


def get_bonus_receiver(user_id: int) -> dict:
    """Kullanıcının bonus kaydını getir (varsa)"""
    if not supabase:
        return None
    try:
        result = supabase.table("bonus_receivers").select("*").eq("user_id", user_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Bonus kaydı sorgulama hatası: {e}")
        return None


def save_bonus(user, site_username: str) -> None:
    """Bonus talebini ve site kullanıcı adını kaydet"""
    if not supabase:
        return
    try:
        supabase.table("bonus_receivers").upsert({
            "user_id": user.id,
            "first_name": user.first_name or "",
            "username": user.username or "",
            "site_username": site_username,
        }, on_conflict="user_id").execute()
    except Exception as e:
        logger.error(f"Bonus kaydı hatası: {e}")


def get_total_users() -> int:
    if not supabase:
        return 0
    try:
        result = supabase.table("users").select("user_id", count="exact").execute()
        return result.count or 0
    except Exception:
        return 0


def get_total_bonus() -> int:
    if not supabase:
        return 0
    try:
        result = supabase.table("bonus_receivers").select("user_id", count="exact").execute()
        return result.count or 0
    except Exception:
        return 0


def get_button_clicks() -> dict:
    if not supabase:
        return {}
    try:
        result = supabase.table("button_clicks").select("*").execute()
        return {row["button_name"]: row["click_count"] for row in (result.data or [])}
    except Exception:
        return {}


def get_all_bonus_receivers() -> list:
    if not supabase:
        return []
    try:
        result = supabase.table("bonus_receivers").select("*").order("received_at").execute()
        return result.data or []
    except Exception:
        return []


def get_all_user_ids() -> list:
    if not supabase:
        return []
    try:
        result = supabase.table("users").select("user_id").execute()
        return [row["user_id"] for row in (result.data or [])]
    except Exception:
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


def is_valid_username(name: str) -> bool:
    """3-32 karakter, sadece harf ve rakam"""
    return bool(re.fullmatch(r"[A-Za-z0-9]{3,32}", name))


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


def existing_username_keyboard() -> InlineKeyboardMarkup:
    """Mevcut kayıtlı kullanıcı için: bonusu al veya kullanıcı adını değiştir"""
    keyboard = [
        [InlineKeyboardButton("✅ Bu Kullanıcı Adıyla Devam Et", callback_data="use_existing_username")],
        [InlineKeyboardButton("✏️ Kullanıcı Adını Değiştir", callback_data="change_username")],
        [InlineKeyboardButton("⬅️ Ana Menü", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ---------- Admin Bildirim ----------

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, user, site_username: str) -> None:
    """Admin'e bonus alındığını anlık bildir"""
    try:
        tg_username = f"@{user.username}" if user.username else "(yok)"
        text = (
            "🔔 *Yeni Bonus Talebi*\n\n"
            f"👤 *Ad:* {user.first_name or '-'}\n"
            f"📱 *Telegram:* {tg_username}\n"
            f"🆔 *Telegram ID:* `{user.id}`\n"
            f"🎮 *Site Kullanıcı Adı:* `{site_username}`"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Admin bildirimi hatası: {e}")


# ---------- Kullanıcı Komutları ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    register_user(user)
    welcome_text = (
        f"👋 Merhaba {user.first_name}!\n\n"
        f"Aşağıdaki menüden istediğin seçeneğe tıklayabilirsin:"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Buton tıklamalarını işle. Kullanıcı adı isteme durumuna geçebilir."""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    register_user(user)

    # Ana menüye dönüş
    if query.data == "main_menu":
        await query.edit_message_text(
            f"👋 Merhaba {user.first_name}!\n\n"
            f"Aşağıdaki menüden istediğin seçeneğe tıklayabilirsin:",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    # Bonus butonu
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
            return ConversationHandler.END

        # Üye - mevcut kayıt var mı?
        existing = get_bonus_receiver(user.id)
        if existing and existing.get("site_username"):
            # Eskiden kaydolmuş, soruyoruz
            await query.edit_message_text(
                f"✅ Kanal üyeliğin doğrulandı!\n\n"
                f"🎮 Daha önce kaydettiğin site kullanıcı adı:\n"
                f"`{existing['site_username']}`\n\n"
                f"Bu kullanıcı adıyla devam etmek mi yoksa değiştirmek mi istersin?",
                reply_markup=existing_username_keyboard(),
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        # Yeni kullanıcı - site adını sor
        await query.edit_message_text(
            "✅ Kanal üyeliğin doğrulandı!\n\n"
            "🎮 *Lütfen site kullanıcı adını yaz:*\n\n"
            "_(3-32 karakter, sadece harf ve rakam)_\n"
            "_İptal için /cancel yaz._",
            parse_mode="Markdown",
        )
        return WAITING_USERNAME

    # Mevcut kullanıcı adıyla devam
    if query.data == "use_existing_username":
        existing = get_bonus_receiver(user.id)
        site_username = existing.get("site_username", "") if existing else ""

        # Bonus metnini göster
        await query.edit_message_text(
            BONUS_TEXT + f"\n\n🎮 *Kayıtlı Site Kullanıcı Adın:* `{site_username}`",
            reply_markup=back_keyboard(),
            parse_mode="Markdown",
        )
        # Admin'e bildir
        await notify_admin(context, user, site_username)
        return ConversationHandler.END

    # Kullanıcı adını değiştir
    if query.data == "change_username":
        await query.edit_message_text(
            "🎮 *Yeni site kullanıcı adını yaz:*\n\n"
            "_(3-32 karakter, sadece harf ve rakam)_\n"
            "_İptal için /cancel yaz._",
            parse_mode="Markdown",
        )
        return WAITING_USERNAME

    return ConversationHandler.END


async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcı site adını yazdığında işle"""
    user = update.effective_user
    site_username = update.message.text.strip()

    if not is_valid_username(site_username):
        await update.message.reply_text(
            "⚠️ Geçersiz kullanıcı adı.\n\n"
            "Kullanıcı adı *3-32 karakter* uzunluğunda olmalı ve sadece *harf veya rakam* içermelidir.\n\n"
            "Lütfen tekrar dene veya /cancel ile iptal et.",
            parse_mode="Markdown",
        )
        return WAITING_USERNAME

    # Üyelik son kontrol (güvenlik)
    is_member = await is_user_in_channel(context, user.id)
    if not is_member:
        await update.message.reply_text(
            "❌ Kanal üyeliğin artık geçerli değil. Lütfen /start yazarak tekrar başla.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    # Kaydet
    save_bonus(user, site_username)

    # Bonus metnini gönder
    await update.message.reply_text(
        BONUS_TEXT + f"\n\n🎮 *Kayıtlı Site Kullanıcı Adın:* `{site_username}`",
        reply_markup=back_keyboard(),
        parse_mode="Markdown",
    )

    # Admin'e anlık bildirim
    await notify_admin(context, user, site_username)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ İşlem iptal edildi.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


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
        tg_username = f"@{info['username']}" if info.get("username") else "(yok)"
        site_username = info.get("site_username") or "(yok)"
        date = (info.get("received_at") or "")[:10]
        uid = info.get("user_id", "")
        lines.append(
            f"{i}. {name}\n"
            f"   📱 TG: {tg_username}\n"
            f"   🎮 Site: `{site_username}`\n"
            f"   🆔 `{uid}` - {date}"
        )

    full_text = "\n\n".join(lines)
    if len(full_text) > 4000:
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 2 > 4000:
                chunks.append(current)
                current = line
            else:
                current += "\n\n" + line if current else line
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


# ---------- Web Server ----------

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

    # Ana kullanıcı akışı (start + butonlar + kullanıcı adı isteme)
    main_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(button_handler),
        ],
        states={
            WAITING_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # Broadcast akışı
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
    application.add_handler(main_conv)
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("bonuslist", bonus_list))

    logger.info("Bot başlatıldı.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
