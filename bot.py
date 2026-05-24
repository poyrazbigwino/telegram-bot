"""
Telegram Bot - Tam Sürüm (Supabase + Mesajlaşma + Grup Bildirimi)
==================================================================
Bonus alındığında:
- Admin'e detaylı bildirim
- Log grubuna kısa bildirim: "🔔 Telegram Bonus Talebi - siteadi - tarih"
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
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

# Log grubu/kanalı (boş bırakılırsa gönderilmez)
LOG_CHAT_ID = os.environ.get("LOG_CHAT_ID", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

PORT = int(os.environ.get("PORT", "10000"))

BONUS_TEXT = (
    "🎁 *TELEGRAM BONUSU* 🎁\n\n"
    "Tebrikler! Bonus talebin alındı.\n\n"
    "🎟️ *Bonus Kodu:* `winoTG05RDx6`\n\n"
    "Bu kodu sitemizdeki bonus alanına girerek bonusunu talep edebilirsin.\n\n"
    "Dikkat site kullanıcı adınızı doğru kaydetmeniz gerekmektedir. Detaylar için promosyon sayfasını incelemeyi unutmayın.\n\n"
    "İyi şanslar! 🍀"
)
# =====================

WAITING_BROADCAST = 1
WAITING_USERNAME = 2
WAITING_BONUS_BROADCAST = 3
WAITING_FILTER_DAYS = 4
WAITING_FILTER_BROADCAST = 5

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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
    if not supabase:
        return None
    try:
        result = supabase.table("bonus_receivers").select("*").eq("user_id", user_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Bonus kaydı sorgulama hatası: {e}")
        return None


def save_bonus(user, site_username: str) -> None:
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


def get_bonus_user_ids() -> list:
    if not supabase:
        return []
    try:
        result = supabase.table("bonus_receivers").select("user_id").execute()
        return [row["user_id"] for row in (result.data or [])]
    except Exception:
        return []


def find_user_by_site_username(site_username: str) -> dict:
    if not supabase:
        return None
    try:
        result = supabase.table("bonus_receivers").select("*").ilike("site_username", site_username).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Site kullanıcı sorgulama hatası: {e}")
        return None


def get_user_ids_joined_in_last_days(days: int) -> list:
    if not supabase:
        return []
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = supabase.table("users").select("user_id").gte("joined_at", threshold).execute()
        return [row["user_id"] for row in (result.data or [])]
    except Exception as e:
        logger.error(f"Filtre hatası: {e}")
        return []


def get_user_ids_NOT_joined_in_last_days(days: int) -> list:
    if not supabase:
        return []
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = supabase.table("users").select("user_id").lt("joined_at", threshold).execute()
        return [row["user_id"] for row in (result.data or [])]
    except Exception as e:
        logger.error(f"Filtre hatası: {e}")
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
    keyboard = [
        [InlineKeyboardButton("✅ Bu Kullanıcı Adıyla Devam Et", callback_data="use_existing_username")],
        [InlineKeyboardButton("✏️ Kullanıcı Adını Değiştir", callback_data="change_username")],
        [InlineKeyboardButton("⬅️ Ana Menü", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def filter_choice_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🆕 Son X günde katılanlar", callback_data="filter_new")],
        [InlineKeyboardButton("😴 Son X gündür gelmeyenler", callback_data="filter_inactive")],
        [InlineKeyboardButton("❌ İptal", callback_data="filter_cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ---------- Bildirimler ----------

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, user, site_username: str) -> None:
    """Admin'e detaylı bildirim"""
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


async def notify_log_chat(context: ContextTypes.DEFAULT_TYPE, site_username: str) -> None:
    """Log grubuna/kanalına kısa bildirim"""
    if not LOG_CHAT_ID:
        return
    try:
        # Türkiye saati (UTC+3)
        tz_tr = timezone(timedelta(hours=3))
        now_tr = datetime.now(tz_tr).strftime("%d.%m.%Y %H:%M")
        text = f"🔔 Telegram Bonus Talebi - {site_username} - {now_tr}"
        await context.bot.send_message(chat_id=int(LOG_CHAT_ID), text=text)
    except Exception as e:
        logger.error(f"Log chat bildirimi hatası: {e}")


async def notify_both(context: ContextTypes.DEFAULT_TYPE, user, site_username: str) -> None:
    """Hem admin'e hem log grubuna bildirim gönder"""
    await notify_admin(context, user, site_username)
    await notify_log_chat(context, site_username)


# ---------- Toplu Mesaj Yardımcı ----------

async def send_broadcast(context, user_ids, message_text, notify_message):
    if not user_ids:
        await notify_message.reply_text("📭 Gönderilecek kullanıcı yok.")
        return

    await notify_message.reply_text(f"⏳ {len(user_ids)} kullanıcıya mesaj gönderiliyor...")
    success = 0
    failed = 0
    blocked = 0

    for i, uid in enumerate(user_ids):
        try:
            await context.bot.send_message(chat_id=int(uid), text=message_text)
            success += 1
        except Exception as e:
            err_str = str(e).lower()
            if "blocked" in err_str or "deactivated" in err_str:
                blocked += 1
            else:
                failed += 1
            logger.warning(f"Mesaj gönderilemedi ({uid}): {e}")

        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)

    await notify_message.reply_text(
        f"✅ *Toplu mesaj tamamlandı!*\n\n"
        f"✔️ Başarılı: {success}\n"
        f"🚫 Engellenen: {blocked}\n"
        f"❌ Diğer hata: {failed}",
        parse_mode="Markdown",
    )


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
        return ConversationHandler.END

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

        existing = get_bonus_receiver(user.id)
        if existing and existing.get("site_username"):
            await query.edit_message_text(
                f"✅ Kanal üyeliğin doğrulandı!\n\n"
                f"🎮 Daha önce kaydettiğin site kullanıcı adı:\n"
                f"`{existing['site_username']}`\n\n"
                f"Bu kullanıcı adıyla devam etmek mi yoksa değiştirmek mi istersin?",
                reply_markup=existing_username_keyboard(),
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        await query.edit_message_text(
            "✅ Kanal üyeliğin doğrulandı!\n\n"
            "🎮 *Lütfen site kullanıcı adını yaz:*\n\n"
            "_(3-32 karakter, sadece harf ve rakam)_\n"
            "_İptal için /cancel yaz._",
            parse_mode="Markdown",
        )
        return WAITING_USERNAME

    if query.data == "use_existing_username":
        existing = get_bonus_receiver(user.id)
        site_username = existing.get("site_username", "") if existing else ""
        await query.edit_message_text(
            BONUS_TEXT + f"\n\n🎮 *Kayıtlı Site Kullanıcı Adın:* `{site_username}`",
            reply_markup=back_keyboard(),
            parse_mode="Markdown",
        )
        await notify_both(context, user, site_username)
        return ConversationHandler.END

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

    is_member = await is_user_in_channel(context, user.id)
    if not is_member:
        await update.message.reply_text(
            "❌ Kanal üyeliğin artık geçerli değil. Lütfen /start yazarak tekrar başla.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    save_bonus(user, site_username)
    await update.message.reply_text(
        BONUS_TEXT + f"\n\n🎮 *Kayıtlı Site Kullanıcı Adın:* `{site_username}`",
        reply_markup=back_keyboard(),
        parse_mode="Markdown",
    )
    await notify_both(context, user, site_username)
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
    log_status = "✅ Aktif" if LOG_CHAT_ID else "❌ Kapalı"

    text = (
        "🛠️ *YÖNETİCİ PANELİ*\n\n"
        f"👥 *Toplam Kullanıcı:* {total_users}\n"
        f"🎁 *Bonus Alan:* {total_bonus}\n\n"
        f"📊 *Bonus Buton Tıklaması:* {clicks.get('bonus', 0)}\n"
        f"📡 *Log Grubu:* {log_status}\n\n"
        f"📋 *Komutlar:*\n"
        f"/bonuslist - Bonus alanların listesi\n"
        f"/sendlogall - Tüm bonus alanları log grubuna gönder\n\n"
        f"📢 *Mesajlaşma:*\n"
        f"/broadcast - Tüm kullanıcılara mesaj\n"
        f"/bonusbroadcast - Sadece bonus alanlara mesaj\n"
        f"/sitebroadcast - Belirli site adına özel mesaj\n"
        f"/filterbroadcast - Filtreli mesaj"
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


# ---------- /sendlogall: Tüm bonus alanları log grubuna gönder ----------

async def send_log_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mevcut tüm bonus alanları tek seferlik log grubuna gönder"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return

    if not LOG_CHAT_ID:
        await update.message.reply_text(
            "⚠️ Log grubu/kanalı tanımlı değil.\n\n"
            "Render'da `LOG_CHAT_ID` environment variable'ını ayarla."
        )
        return

    receivers = get_all_bonus_receivers()
    if not receivers:
        await update.message.reply_text("📭 Henüz bonus alan kimse yok.")
        return

    await update.message.reply_text(
        f"⏳ {len(receivers)} bonus kaydı log grubuna gönderiliyor..."
    )

    success = 0
    failed = 0

    for i, info in enumerate(receivers):
        site_username = info.get("site_username") or "(yok)"
        received_at = info.get("received_at") or ""

        # Tarihi Türkiye saatine çevir
        try:
            dt_utc = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            tz_tr = timezone(timedelta(hours=3))
            dt_tr = dt_utc.astimezone(tz_tr)
            tarih_str = dt_tr.strftime("%d.%m.%Y %H:%M")
        except Exception:
            tarih_str = received_at[:16] if received_at else "?"

        text = f"🔔 Telegram Bonus Talebi - {site_username} - {tarih_str}"

        try:
            await context.bot.send_message(chat_id=int(LOG_CHAT_ID), text=text)
            success += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Log gönderilemedi ({site_username}): {e}")

        # Rate limit koruması: her 25 mesajda 1 saniye bekle
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)

    await update.message.reply_text(
        f"✅ *Tamamlandı!*\n\n"
        f"✔️ Gönderilen: {success}\n"
        f"❌ Hata: {failed}",
        parse_mode="Markdown",
    )


# ---------- /broadcast ----------

async def broadcast_start(update, context) -> int:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📢 *Toplu Mesaj — TÜM KULLANICILAR*\n\n"
        "Tüm kullanıcılara göndermek istediğin mesajı yaz.\n"
        "İptal için /cancel yaz.",
        parse_mode="Markdown",
    )
    return WAITING_BROADCAST


async def broadcast_send(update, context) -> int:
    user_ids = get_all_user_ids()
    await send_broadcast(context, user_ids, update.message.text, update.message)
    return ConversationHandler.END


# ---------- /bonusbroadcast ----------

async def bonus_broadcast_start(update, context) -> int:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return ConversationHandler.END
    total = len(get_bonus_user_ids())
    await update.message.reply_text(
        f"🎁 *Toplu Mesaj — BONUS ALANLAR* ({total} kişi)\n\n"
        f"Bonus alan kişilere göndermek istediğin mesajı yaz.\n"
        f"İptal için /cancel yaz.",
        parse_mode="Markdown",
    )
    return WAITING_BONUS_BROADCAST


async def bonus_broadcast_send(update, context) -> int:
    user_ids = get_bonus_user_ids()
    await send_broadcast(context, user_ids, update.message.text, update.message)
    return ConversationHandler.END


# ---------- /sitebroadcast ----------

async def site_broadcast(update, context) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return

    text = update.message.text or ""
    parts = text.split(maxsplit=2)

    if len(parts) < 3:
        await update.message.reply_text(
            "📝 *Kullanım:*\n"
            "`/sitebroadcast siteadi Mesaj metni buraya`\n\n"
            "*Örnek:*\n"
            "`/sitebroadcast ahmet123 Bonusunuz onaylandı, sitemize bekleriz!`",
            parse_mode="Markdown",
        )
        return

    site_username = parts[1]
    message_text = parts[2]

    record = find_user_by_site_username(site_username)
    if not record:
        await update.message.reply_text(
            f"❌ `{site_username}` adında bir kullanıcı bulunamadı.",
            parse_mode="Markdown",
        )
        return

    try:
        await context.bot.send_message(chat_id=int(record["user_id"]), text=message_text)
        await update.message.reply_text(
            f"✅ Mesaj gönderildi!\n\n"
            f"👤 *Alıcı:* {record.get('first_name', '?')}\n"
            f"🎮 *Site Adı:* `{site_username}`\n"
            f"🆔 *TG ID:* `{record['user_id']}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Mesaj gönderilemedi: {e}\n\n"
            f"(Kullanıcı botu engellemiş veya hesabını silmiş olabilir.)"
        )


# ---------- /filterbroadcast ----------

async def filter_broadcast_start(update, context) -> int:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Bu komut sadece yönetici içindir.")
        return ConversationHandler.END

    await update.message.reply_text(
        "🎯 *Filtreli Mesaj*\n\n"
        "Hangi gruba göndermek istersin?",
        reply_markup=filter_choice_keyboard(),
        parse_mode="Markdown",
    )
    return WAITING_FILTER_DAYS


async def filter_choice_handler(update, context) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "filter_cancel":
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END

    if query.data == "filter_new":
        context.user_data["filter_mode"] = "new"
        await query.edit_message_text(
            "🆕 *Son X günde katılanlar*\n\n"
            "Kaç günü hedeflemek istersin? (Sayı yaz)\n"
            "Örnek: `7` = son 7 gün\n\n"
            "İptal için /cancel yaz.",
            parse_mode="Markdown",
        )
        return WAITING_FILTER_DAYS

    if query.data == "filter_inactive":
        context.user_data["filter_mode"] = "inactive"
        await query.edit_message_text(
            "😴 *Son X gündür gelmeyenler*\n\n"
            "Kaç günden eski olmalı? (Sayı yaz)\n"
            "Örnek: `7` = 7 gün önce ve daha eski tarihte katılanlar\n\n"
            "İptal için /cancel yaz.",
            parse_mode="Markdown",
        )
        return WAITING_FILTER_DAYS

    return ConversationHandler.END


async def filter_days_received(update, context) -> int:
    text = (update.message.text or "").strip()
    if not text.isdigit():
        await update.message.reply_text("⚠️ Lütfen sadece bir sayı yaz (örnek: 7).")
        return WAITING_FILTER_DAYS

    days = int(text)
    if days < 1 or days > 365:
        await update.message.reply_text("⚠️ 1-365 arası bir sayı gir.")
        return WAITING_FILTER_DAYS

    mode = context.user_data.get("filter_mode", "new")
    if mode == "new":
        user_ids = get_user_ids_joined_in_last_days(days)
        label = f"son {days} günde katılan"
    else:
        user_ids = get_user_ids_NOT_joined_in_last_days(days)
        label = f"{days} gün önce ve daha eski katılan"

    context.user_data["filter_user_ids"] = user_ids
    await update.message.reply_text(
        f"🎯 *Hedef:* {len(user_ids)} kullanıcı ({label})\n\n"
        f"Göndermek istediğin mesajı yaz.\n"
        f"İptal için /cancel yaz.",
        parse_mode="Markdown",
    )
    return WAITING_FILTER_BROADCAST


async def filter_broadcast_send(update, context) -> int:
    user_ids = context.user_data.get("filter_user_ids", [])
    await send_broadcast(context, user_ids, update.message.text, update.message)
    context.user_data.pop("filter_user_ids", None)
    context.user_data.pop("filter_mode", None)
    return ConversationHandler.END


async def broadcast_cancel(update, context) -> int:
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

    if LOG_CHAT_ID:
        logger.info(f"Log grubu/kanalı aktif: {LOG_CHAT_ID}")
    else:
        logger.info("Log grubu/kanalı tanımlı değil.")

    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()

    application = Application.builder().token(BOT_TOKEN).build()

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

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )

    bonus_broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("bonusbroadcast", bonus_broadcast_start)],
        states={WAITING_BONUS_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bonus_broadcast_send)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )

    filter_broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("filterbroadcast", filter_broadcast_start)],
        states={
            WAITING_FILTER_DAYS: [
                CallbackQueryHandler(filter_choice_handler, pattern="^filter_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, filter_days_received),
            ],
            WAITING_FILTER_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, filter_broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )

    application.add_handler(broadcast_conv)
    application.add_handler(bonus_broadcast_conv)
    application.add_handler(filter_broadcast_conv)
    application.add_handler(main_conv)

    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("bonuslist", bonus_list))
    application.add_handler(CommandHandler("sendlogall", send_log_all))
    application.add_handler(CommandHandler("sitebroadcast", site_broadcast))

    logger.info("Bot başlatıldı.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
