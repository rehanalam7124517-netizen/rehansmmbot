import telebot
from telebot import types
import requests
from requests.adapters import HTTPAdapter
import json
import os
import shutil
import zipfile
from datetime import datetime
import csv
import html
import re
import threading
import time
import tempfile
import uuid
import sys
import random
import glob
from urllib.parse import quote
from collections import Counter
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Dummy web server background thread mein start hoga
Thread(target=run).start()

# --- Aapka baaki Telegram bot code niche rahega ---

# Configuration
TOKEN = os.environ.get("TOKEN")
SMM_API_KEY = os.environ.get("SMM_API_KEY")
SMM_API_URL = "https://topsmm.in/api/v2"
ADMIN_ID = 6323330154  # Admin ID
ORDER_LOG_CHANNEL = "@rehansmmbotorderslog"
ORDER_LOG_CHANNEL_LINK = "https://t.me/rehansmmbotorderslog"
BOT_LINK = "https://t.me/rehansmmbot"

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=30)

# Fast shared HTTP session: connection reuse avoids a fresh TLS handshake on every API call.
_HTTP_SESSION = requests.Session()
_HTTP_ADAPTER = HTTPAdapter(pool_connections=40, pool_maxsize=40, max_retries=0)
_HTTP_SESSION.mount("https://", _HTTP_ADAPTER)
_HTTP_SESSION.mount("http://", _HTTP_ADAPTER)

_PANEL_CACHE_LOCK = threading.RLock()
_PANEL_SERVICES_CACHE = {"data": [], "time": 0.0, "url": "", "key": ""}
PANEL_SERVICES_CACHE_TTL = 20

def _api_post(data, timeout=(4, 10)):
    """Panel request using a reusable connection and bounded timeout."""
    return _HTTP_SESSION.post(SMM_API_URL, data=data, timeout=timeout)

def _clear_panel_cache():
    with _PANEL_CACHE_LOCK:
        _PANEL_SERVICES_CACHE.update({"data": [], "time": 0.0, "url": "", "key": ""})

# ✅ Inline buttons: always one button per line for clean mobile UI
try:
    _ORIG_INLINE_ADD = types.InlineKeyboardMarkup.add
    def _inline_add_one_per_row(self, *args, **kwargs):
        if len(args) <= 1:
            return _ORIG_INLINE_ADD(self, *args, **kwargs)
        for btn in args:
            _ORIG_INLINE_ADD(self, btn, **kwargs)
        return self
    types.InlineKeyboardMarkup.add = _inline_add_one_per_row
except Exception:
    pass
DB_FILE = "users.json"
ORDERS_FILE = "orders.json"
FUNDS_HISTORY_FILE = "funds_history.json" # New file for fund history
COUPON_FILE = "coupons.json"
LAST_PRICE_FILE = "last_prices.json"
FUNDS_FILE = "funds.json"
PRICE_HISTORY_FILE = "price_history.json"
WALLET_HISTORY_FILE = "wallet_history.json"
KNOWN_SERVICES_FILE = "known_services.json"
SETTINGS_FILE = "settings.json"

# ================= SUPABASE STORAGE =================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

SUPABASE_TABLE = "bot_data"

def supabase_enabled():
    return bool(SUPABASE_URL and SUPABASE_KEY)

def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

def supabase_get(filename):
    if not supabase_enabled():
        return None

    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
            f"?filename=eq.{quote(filename, safe='')}"
            f"&select=data&limit=1"
        )

        response = _HTTP_SESSION.get(
            url,
            headers=supabase_headers(),
            timeout=15
        )

        if response.status_code != 200:
            print(
                f"[SUPABASE GET ERROR] "
                f"{filename}: {response.status_code}"
            )
            return None

        rows = response.json()

        if rows:
            return rows[0]["data"]

        return None

    except Exception as e:
        print(f"[SUPABASE GET ERROR] {filename}: {e}")
        return None


def supabase_save(filename, data):
    if not supabase_enabled():
        return False

    try:
        url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"

        headers = supabase_headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

        payload = {
            "filename": filename,
            "data": data,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = _HTTP_SESSION.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        if response.status_code not in (200, 201, 204):
            print(
                f"[SUPABASE SAVE ERROR] "
                f"{filename}: {response.status_code} "
                f"{response.text[:200]}"
            )
            return False

        return True

    except Exception as e:
        print(f"[SUPABASE SAVE ERROR] {filename}: {e}")
        return False


# ================= END SUPABASE STORAGE =================

# Runtime API configuration: settings.json values override hard-coded defaults.
def _load_runtime_api_config():
    global SMM_API_URL, SMM_API_KEY
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            _cfg = json.load(f)
        if isinstance(_cfg, dict):
            _url = str(_cfg.get("smm_api_url", "") or "").strip()
            _key = str(_cfg.get("smm_api_key", "") or "").strip()
            if _url:
                SMM_API_URL = _url
            if _key:
                SMM_API_KEY = _key
    except Exception:
        pass

_load_runtime_api_config()
SCHEDULED_FILE = "scheduled_broadcasts.json"
ADDED_SERVICES_FILE = "added_services.json"
LOW_BALANCE_LIMIT = 5
MARGINS_FILE = "margins.json"
SERVICES_FILE = "services.json"
DEFAULT_MARGINS_FILE = "default_margins.json"
VIP_MARGINS_FILE = "vip_margins.json"
ADMIN_LOG_FILE = "admin_logs.json"
PINNED_SERVICES_FILE = "pinned_services.json"
RECENT_SERVICES_FILE = "recent_services.json"
FAVORITES_FILE = "favorites.json"
DELETED_USERS_FILE = "deleted_users.json"
TICKETS_FILE = "tickets.json"
FUND_REQUESTS_FILE = "fund_requests.json"
PENDING_ACTIONS_FILE = "pending_actions.json"
ACHIEVEMENTS_FILE = "achievements.json"
SERVICE_NOTIFY_FILE = "service_notify.json"
MONTHLY_REPORT_FILE = "monthly_reports.json"

def _load_static_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

MULTIPLIERS = _load_static_json(DEFAULT_MARGINS_FILE, {})

def get_panel_price(service_id):
    try:
        for service in get_all_panel_services():
            if str(service.get("service")) == str(service_id):
                return float(service.get("rate", 0))
    except Exception as e:
        print("Price fetch error:", e)
    return None

def get_margin(service_id):
    custom_margins = load_json(MARGINS_FILE)
    return float(custom_margins.get(str(service_id), MULTIPLIERS.get(str(service_id), 1)))


def set_margin(service_id, margin):
    custom_margins = load_json(MARGINS_FILE)
    custom_margins[str(service_id)] = float(margin)
    save_json(MARGINS_FILE, custom_margins)


def is_vip_user(user_id):
    db = load_json(DB_FILE)
    return bool(db.get(str(user_id), {}).get("vip", False))


def get_vip_margin(service_id):
    sid = str(service_id)
    vip_margins = load_json(VIP_MARGINS_FILE)
    if sid in vip_margins:
        return float(vip_margins[sid])

    normal_margin = get_margin(sid)

    # Default VIP price normal se kam rahega, lekin panel price se kam nahi jayega.
    return max(1.0, normal_margin * 0.85)


def set_vip_margin(service_id, margin):
    vip_margins = load_json(VIP_MARGINS_FILE)
    vip_margins[str(service_id)] = float(margin)
    save_json(VIP_MARGINS_FILE, vip_margins)


def get_service_multiplier_for_user(sid, user_id=None):
    if user_id is not None and is_vip_user(user_id):
        return get_vip_margin(sid)
    return get_service_multiplier(sid)


def get_selling_price_for_user(service_id, user_id=None):
    panel_price = get_panel_price(service_id)

    if panel_price is None:
        return None

    multiplier = get_service_multiplier_for_user(service_id, user_id)
    return round(panel_price * multiplier, 4)


def start_vip_margin_editor(message):
    msg = bot.send_message(
        ADMIN_ID,
        "👑 <b>ᴇɴᴛᴇʀ ᴠɪᴘ ᴍᴀʀɢɪɴ ꜱᴇʀᴠɪᴄᴇ ɪᴅ:</b>\n\n"
        "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>567</code> ᴏʀ <code>567 559 4123</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_vip_margin_service_ids)


def process_vip_margin_service_idssss(message):
    if message.chat.id != ADMIN_ID:
        return

    ids = message.text.replace(",", " ").replace("\n", " ").split()
    ids = [x.strip() for x in ids if x.strip()]

    valid_ids = []
    text = "✅ <b>ᴠɪᴘ ᴍᴀʀɢɪɴ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏᴜɴᴅ</b>\n\n"

    for sid in ids:
        s_info = find_service(sid)
        if not s_info:
            continue

        panel_price = get_panel_price(sid) or 0
        normal_margin = get_margin(sid)
        vip_margin = get_vip_margin(sid)

        valid_ids.append(str(sid))

        text += (
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{sid}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(s_info[0]))}\n"
            f"📊 <b>ᴘᴀɴᴇʟ »</b> ₹{panel_price:.2f}\n"
            f"👤 <b>ɴᴏʀᴍᴀʟ »</b> ×{normal_margin:.2f} = ₹{panel_price * normal_margin:.2f}\n"
            f"👑 <b>ᴠɪᴘ »</b> ×{vip_margin:.2f} = ₹{panel_price * vip_margin:.2f}\n\n"
        )

    if not valid_ids:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ᴠᴀʟɪᴅ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return

    admin_state[ADMIN_ID] = {"vip_margin_ids": valid_ids}

    text += (
        "✏️ <b>ᴇɴᴛᴇʀ ɴᴇᴡ ᴠɪᴘ ᴍᴀʀɢɪɴ:</b>\n\n"
        "ꜱᴀᴍᴇ ᴍᴀʀɢɪɴ: <code>1.5</code>\n"
        "ᴀʟᴀɢ-ᴀʟᴀɢ: <code>567=1.5 559=10</code>"
    )

    msg = bot.send_message(ADMIN_ID, text[:4000], parse_mode="HTML")
    bot.register_next_step_handler(msg, process_new_vip_margin)

def start_vip_percent_margin(message):
    msg = bot.send_message(
        ADMIN_ID,
        "👑 <b>ᴇɴᴛᴇʀ ᴠɪᴘ ᴅɪꜱᴄᴏᴜɴᴛ ᴘᴇʀᴄᴇɴᴛ:</b>\n\n"
        "ᴇxᴀᴍᴘʟᴇ: <code>10</code>\n"
        "ᴍᴇᴀɴꜱ ɴᴏʀᴍᴀʟ ᴍᴀʀɢɪɴ ꜱᴇ 10% ᴋᴀᴍ",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_vip_percent_margin)


def process_vip_percent_margin(message):
    if message.chat.id != ADMIN_ID:
        return

    try:
        percent = float(message.text.strip())
    except:
        bot.send_message(
            ADMIN_ID,
            "❌ <b>ɪɴᴠᴀʟɪᴅ ᴘᴇʀᴄᴇɴᴛ</b>",
            parse_mode="HTML"
        )
        return

    if percent < 0 or percent > 100:
        bot.send_message(
            ADMIN_ID,
            "❌ <b>ᴘᴇʀᴄᴇɴᴛ 0 ꜱᴇ 100 ᴋᴇ ʙᴇᴇᴄʜ ʜᴏɴᴀ ᴄʜᴀʜɪʏᴇ.</b>",
            parse_mode="HTML"
        )
        return

    all_services = get_all_bot_services_map()
    vip_margins = load_json(VIP_MARGINS_FILE)

    updated = 0

    for sid in all_services.keys():
        normal_margin = get_margin(sid)
        vip_margin = normal_margin * (1 - percent / 100)

        # panel price se kam na jaye
        vip_margin = max(1.0, vip_margin)

        vip_margins[str(sid)] = round(float(vip_margin), 4)
        updated += 1

    save_json(VIP_MARGINS_FILE, vip_margins)

    bot.send_message(
        ADMIN_ID,
        f"✅ <b>ᴠɪᴘ ᴘᴇʀᴄᴇɴᴛ ᴍᴀʀɢɪɴ ᴀᴘᴘʟɪᴇᴅ</b>\n\n"
        f"📉 <b>ᴅɪꜱᴄᴏᴜɴᴛ »</b> {percent}%\n"
        f"📦 <b>ᴛᴏᴛᴀʟ ꜱᴇʀᴠɪᴄᴇꜱ »</b> {updated}\n\n"
        f"👤 <b>ɴᴏʀᴍᴀʟ ×2</b> ➜ 👑 <b>ᴠɪᴘ ×1.8</b>",
        parse_mode="HTML"
    )

def process_vip_margin_service_ids(message):
    if message.chat.id != ADMIN_ID:
        return

    ids = message.text.replace(",", " ").replace("\n", " ").split()
    ids = [x.strip() for x in ids if x.strip()]

    # ✅ Panel API sirf 1 baar call hoga
    panel_services = get_all_panel_services()
    panel_price_map = {
        str(s.get("service")): float(s.get("rate", 0))
        for s in panel_services
    }

    valid_ids = []
    blocks = []

    for sid in ids:
        s_info = find_service(sid)
        if not s_info:
            continue

        panel_price = panel_price_map.get(str(sid), 0)
        normal_margin = get_margin(sid)
        vip_margin = get_vip_margin(sid)

        valid_ids.append(str(sid))

        blocks.append(
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{sid}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(s_info[0]))}\n"
            f"📊 <b>ᴘᴀɴᴇʟ »</b> ₹{panel_price:.2f}\n"
            f"👤 <b>ɴᴏʀᴍᴀʟ »</b> ×{normal_margin:.2f} = ₹{panel_price * normal_margin:.2f}\n"
            f"👑 <b>ᴠɪᴘ »</b> ×{vip_margin:.2f} = ₹{panel_price * vip_margin:.2f}\n"
        )

    if not valid_ids:
        bot.send_message(
            ADMIN_ID,
            "❌ <b>ɴᴏ ᴠᴀʟɪᴅ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ꜰᴏᴜɴᴅ</b>",
            parse_mode="HTML"
        )
        return

    admin_state[ADMIN_ID] = {"vip_margin_ids": valid_ids}

    # ✅ 10 services per message
    chunk_size = 10
    for i in range(0, len(blocks), chunk_size):
        part = blocks[i:i + chunk_size]
        msg_text = (
            "✅ <b>ᴠɪᴘ ᴍᴀʀɢɪɴ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏᴜɴᴅ</b>\n\n"
            + "\n".join(part)
        )
        bot.send_message(ADMIN_ID, msg_text, parse_mode="HTML")

    # ✅ Prompt alag message me, next-step yahi se chalega
    msg = bot.send_message(
        ADMIN_ID,
        "✏️ <b>ᴇɴᴛᴇʀ ɴᴇᴡ ᴠɪᴘ ᴍᴀʀɢɪɴ:</b>\n\n"
        "ꜱᴀᴍᴇ ᴍᴀʀɢɪɴ: <code>1.5</code>\n"
        "ᴀʟᴀɢ-ᴀʟᴀɢ: <code>567=1.5 559=10</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_new_vip_margin)

def process_new_vip_margin(message):
    if message.chat.id != ADMIN_ID:
        return

    if ADMIN_ID not in admin_state:
        return

    ids = admin_state[ADMIN_ID].get("vip_margin_ids", [])
    raw = message.text.strip()
    updates = {}

    try:
        if "=" in raw:
            for part in raw.replace("\n", " ").split():
                if "=" not in part:
                    continue
                sid, margin = part.split("=")
                sid = sid.strip()
                margin = float(margin.strip())
                if sid in ids:
                    updates[sid] = margin
        else:
            margin = float(raw)
            for sid in ids:
                updates[sid] = margin
    except Exception:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴠɪᴘ ᴍᴀʀɢɪɴ ꜰᴏʀᴍᴀᴛ</b>", parse_mode="HTML")
        return

    if not updates:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ᴠɪᴘ ᴍᴀʀɢɪɴ ᴜᴘᴅᴀᴛᴇᴅ</b>", parse_mode="HTML")
        return

    result = "✅ <b>ᴠɪᴘ ᴍᴀʀɢɪɴ ᴜᴘᴅᴀᴛᴇᴅ</b>\n\n"

    for sid, new_margin in updates.items():
        s_info = find_service(sid)
        panel_price = get_panel_price(sid) or 0
        old_margin = get_vip_margin(sid)

        set_vip_margin(sid, new_margin)

        result += (
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{sid}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(s_info[0])) if s_info else 'Unknown'}\n"
            f"👑 <b>ᴠɪᴘ ᴍᴀʀɢɪɴ »</b> ×{old_margin:.2f} ➜ ×{new_margin:.2f}\n"
            f"💰 <b>ᴠɪᴘ ᴘʀɪᴄᴇ »</b> ₹{panel_price * old_margin:.2f} ➜ ₹{panel_price * new_margin:.2f}\n\n"
        )

    bot.send_message(ADMIN_ID, result[:4000], parse_mode="HTML")
    admin_state.pop(ADMIN_ID, None)


def start_margin_editor(message):
    msg = bot.send_message(
        ADMIN_ID,
        "🆔 <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ:</b>\n\n"
        "<b>ᴇxᴀᴍᴩʟᴇ:</b>(****),(**** ****)\n"
        "<b>*=ᴀɴʏ ɴᴀᴛᴜʀᴀʟ ɴᴜᴍʙᴇʀ</b>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_margin_service_ids)

def get_all_bot_services_map():
    """Return all bot services from default SERVICES + added_services.json without slow API calls."""
    all_services = {}

    for cat_key, items in SERVICES.items():
        for sid, info in items.items():
            sid = str(sid)
            try:
                price = float(info[1])
            except Exception:
                price = 0.0
            all_services[sid] = {
                "id": sid,
                "name": str(info[0]),
                "price": price,
                "subcat": cat_key,
                "source": "default"
            }

    added_db = load_json(ADDED_SERVICES_FILE)

    for sid, item in added_db.items():
        sid = str(sid)
        try:
            price = float(item.get("price", 0))
        except Exception:
            price = 0.0
        all_services[sid] = {
            "id": sid,
            "name": str(item.get("name", "Unknown")),
            "price": price,
            "subcat": item.get("subcat", ""),
            "source": "added"
        }

    return all_services

def process_margin_service_ids(message):
    if message.chat.id != ADMIN_ID:
        return

    ids = message.text.replace(",", " ").replace("\n", " ").split()
    ids = [x.strip() for x in ids if x.strip()]

    valid_ids = []

    text = "✅ <b>ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏᴜɴᴅ</b>\n\n"

    for sid in ids:
        s_info = find_service(sid)

        if not s_info:
            continue

        panel_price = get_panel_price(sid) or 0
        old_margin = get_margin(sid)
        old_price = panel_price * old_margin

        valid_ids.append(sid)

        text += (
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{sid}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ »</b> {html.escape(s_info[0])}\n"
            f"💎 <b>ᴄᴜʀʀᴇɴᴛ ᴍᴀʀɢɪɴ »</b> ×{old_margin:.2f}\n"
            f"💰 <b>ᴄᴜʀʀᴇɴᴛ ᴘʀɪᴄᴇ »</b> ₹{old_price:.2f}\n\n"
        )

    if not valid_ids:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ᴠᴀʟɪᴅ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return

    admin_state[ADMIN_ID] = {"margin_ids": valid_ids}

    text += (
        "✏️ <b>ᴇɴᴛᴇʀ ɴᴇᴡ ᴍᴀʀɢɪɴ:</b>\n\n"
        "ꜱᴀᴍᴇ ᴍᴇʀɢɪɴ ᴋᴇ ʟɪʏᴇ:****\n"
        "ᴀʟᴀɢ-ᴀʟᴀɢ ᴍᴇʀɢɪɴ ᴋᴇ ʟɪʏᴇ:****=**** ****=****"
    )

    msg = bot.send_message(ADMIN_ID, text[:4000], parse_mode="HTML")
    bot.register_next_step_handler(msg, process_new_margin)


def process_new_margin(message):
    if message.chat.id != ADMIN_ID:
        return

    if ADMIN_ID not in admin_state:
        return

    ids = admin_state[ADMIN_ID].get("margin_ids", [])
    raw = message.text.strip()

    updates = {}

    try:
        if "=" in raw:
            parts = raw.replace("\n", " ").split()

            for part in parts:
                if "=" not in part:
                    continue

                sid, margin = part.split("=")
                sid = sid.strip()
                margin = float(margin.strip())

                if sid in ids:
                    updates[sid] = margin
        else:
            margin = float(raw)
            for sid in ids:
                updates[sid] = margin

    except:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴍᴀʀɢɪɴ ꜰᴏʀᴍᴀᴛ</b>", parse_mode="HTML")
        return

    if not updates:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ᴍᴀʀɢɪɴ ᴜᴘᴅᴀᴛᴇᴅ</b>", parse_mode="HTML")
        return

    result = "✅ <b>ᴍᴀʀɢɪɴ ᴜᴘᴅᴀᴛᴇᴅ</b>\n\n"

    for sid, new_margin in updates.items():
        s_info = find_service(sid)

        panel_price = get_panel_price(sid) or 0

        old_margin = get_margin(sid)
        old_price = panel_price * old_margin
        new_price = panel_price * new_margin

        set_margin(sid, new_margin)

        result += (
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{sid}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ »</b> {html.escape(s_info[0])}\n"
            f"💎 <b>ᴍᴀʀɢɪɴ »</b> ×{old_margin:.2f} ➜ ×{new_margin:.2f}\n"
            f"💰 <b>ᴘʀɪᴄᴇ »</b> ₹{old_price:.2f} ➜ ₹{new_price:.2f}\n\n"
        )

    bot.send_message(ADMIN_ID, result[:4000], parse_mode="HTML")
    admin_state.pop(ADMIN_ID, None)

def send_to_all_users(text):
    users = load_json(DB_FILE)
    for uid in users:
        try:
            bot.send_message(uid, text, parse_mode="HTML")
        except:
            pass

# Manual Price Change / Service Update removed.
# Auto Panel Monitor handles price increase/decrease, new service, disabled service and enabled-again alerts.

def low_balance_popup_text(user_id):
    balance = get_balance(user_id)
    return (
        f"⚠️ ʟᴏᴡ ᴡᴀʟʟᴇᴛ ʙᴀʟᴀɴᴄᴇ\n"
        f"💰 ᴄᴜʀʀᴇɴᴛ ʙᴀʟᴀɴᴄᴇ : ₹{balance:.2f}\n"
        f"🚀 ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ ʙᴀʟᴀɴᴄᴇ ɪꜱ ʀᴜɴɴɪɴɢ ʟᴏᴡ.\n"
        f"➕ ᴘʟᴇᴀꜱᴇ ᴀᴅᴅ ꜰᴜɴᴅꜱ ᴛᴏ ᴀᴠᴏɪᴅ ᴏʀᴅᴇʀ ꜰᴀɪʟᴜʀᴇꜱ.\n"
        f"💳 ᴜꜱᴇ \"➕ ᴀᴅᴅ ꜰᴜɴᴅ\" ꜰʀᴏᴍ ᴛʜᴇ ᴍᴇɴᴜ."
    )

def low_balance_popup_keyboard(user_id):
    if get_balance(user_id) >= LOW_BALANCE_LIMIT:
        return None
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ ʟᴏᴡ ᴡᴀʟʟᴇᴛ ʙᴀʟᴀɴᴄᴇ", callback_data="lowbal_popup"))
    return kb

def send_low_balance_alert(user_id):
    # Text message disabled. Low balance alert ab popup button se show hoga.
    return None

def get_selling_price(service_id):
    return get_selling_price_for_user(service_id, None)

def fancy_number(text):
    normal = "0123456789"
    fancy = "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
    return str(text).translate(str.maketrans(normal, fancy))

# Validation buttons
MENU_BUTTONS = [
    "📋 ꜱᴇʀᴠɪᴄᴇꜱ", "📦 ᴏʀᴅᴇʀꜱ", "ᴘᴀʏᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ", "👤 ᴀᴄᴄᴏᴜɴᴛ",
    "📋 ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇ", "📋 ꜱᴇʀᴠɪᴄᴇ ɪᴅ ʟɪꜱᴛ", "👤 ᴘʀᴏꜰɪʟᴇ",
    "💰 ᴡᴀʟʟᴇᴛ", "➕ ᴀᴅᴅ ꜰᴜɴᴅ", "📦 ᴍʏ ᴏʀᴅᴇʀꜱ", "📊 ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ",
    "🎫 ᴀᴘᴘʟʏ ᴄᴏᴜᴘᴏɴ", "🎫 ᴛɪᴄᴋᴇᴛ", "🎁 ʀᴇꜰᴇʀʀᴀʟ", "⚙️ ꜱᴇᴛᴛɪɴɢꜱ", "⚙️ ꜱᴇᴛᴛɪɴɢꜱ & ᴛɪᴄᴋᴇᴛ", "🎫 ᴛɪᴄᴋᴇᴛ & ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ", "⚙️ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ", "ℹ️ ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ", "📖 ʜᴏᴡ ᴛᴏ ᴏʀᴅᴇʀ", "📜 ᴛᴇʀᴍꜱ & ʀᴜʟᴇꜱ", "ℹ️ ᴀʙᴏᴜᴛ ʙᴏᴛ", "📜 ɢᴇɴᴇʀᴀʟ ʀᴜʟᴇꜱ", "🔄 ʀᴇꜰɪʟʟ ᴘᴏʟɪᴄʏ", "💰 ʀᴇꜰᴜɴᴅ ᴘᴏʟɪᴄʏ", "ℹ️ ɪᴍᴘᴏʀᴛᴀɴᴛ ɴᴏᴛᴇꜱ",
    "🔍 ꜱᴇᴀʀᴄʜ ꜱᴇʀᴠɪᴄᴇ", "💳 ᴡᴀʟʟᴇᴛ ʜɪꜱᴛᴏʀʏ", "📜 ꜰᴜɴᴅ ʜɪꜱᴛᴏʀʏ",
    "❌ ᴄᴀɴᴄᴇʟ ᴏʀᴅᴇʀ", "🔄 ʀᴇꜰɪʟʟ ᴏʀᴅᴇʀ", "⭐ ꜰᴀᴠᴏᴜʀɪᴛᴇꜱ",
    "🕒 ʀᴇᴄᴇɴᴛ", "🔥 ᴛᴏᴘ", "📌 ᴘɪɴɴᴇᴅ", "⚙️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ",
    "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"
]

# ================= DATABASE MANAGEMENT =================

def load_json(filename):

    # First try Supabase
    if supabase_enabled():

        remote_data = supabase_get(filename)

        if remote_data is not None:

            # Keep local copy as backup/fallback
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(
                        remote_data,
                        f,
                        indent=4,
                        ensure_ascii=False
                    )
            except Exception:
                pass

            return remote_data

    # Fallback to local JSON
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        # If Supabase doesn't have this file yet,
        # upload the existing local data.
        if supabase_enabled():
            if supabase_get(filename) is None:
                supabase_save(filename, data)

        return data

    except Exception as e:
        print(f"[JSON LOAD ERROR] {filename}: {e}")
        return {}


def save_json(filename, data):

    # Always save local JSON first
    temp_file = filename + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

    os.replace(temp_file, filename)

    # Then save to Supabase
    if supabase_enabled():
        supabase_save(filename, data)


# ================= END DATABASE MANAGEMENT =================

def backup_json_files():
    for filename in [DB_FILE, ORDERS_FILE, FUNDS_FILE, FUNDS_HISTORY_FILE, COUPON_FILE, LAST_PRICE_FILE]:
        if os.path.exists(filename):
            try:
                shutil.copy(filename, filename.replace('.json', '_backup.json'))
            except Exception as e:
                print('Backup error:', filename, e)

def setup_user(user_id, message=None, referrer=None):
    deleted_db = load_json(DELETED_USERS_FILE)
    uid = str(user_id)

    if uid in deleted_db:
        return False

    db = load_json(DB_FILE)

    if uid not in db:
        db[uid] = {
            "balance": 0.0,
            "referred_by": referrer,
            "name": message.from_user.first_name if message else "Unknown",
            "username": message.from_user.username if message and message.from_user.username else "No Username",
            "referrals_count": 0,
            "referral_earnings": 0.0,
            "join_date": datetime.now().strftime("%d-%m-%Y"),
            "active": True,
            "vip": False,
            "date": datetime.now().strftime("%d-%m-%Y %I:%M %p"),
        }

        if referrer and str(referrer) in db and str(referrer) != uid:
            rid = str(referrer)
            db[rid]["referrals_count"] = db[rid].get("referrals_count", 0) + 1
            db[rid]["referral_earnings"] = db[rid].get("referral_earnings", 0.0)

            # Referral complete notification: jab naya user referral link se /start kare
            try:
                new_user_name = message.from_user.first_name if message else "Unknown"
                new_user_username = ("@" + message.from_user.username) if message and message.from_user.username else "No Username"
                bot.send_message(
                    int(rid),
                    "🎉 <b>ʀᴇꜰᴇʀʀᴀʟ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
                    "✅ <b>ᴀᴀᴘᴋᴇ ʀᴇꜰᴇʀ ʟɪɴᴋ ꜱᴇ ɴᴇᴡ ᴜꜱᴇʀ ʙᴏᴛ ꜱᴛᴀʀᴛ ᴋᴀʀ ᴅɪʏᴀ.</b>\n\n"
                    f"👤 <b>ɴᴇᴡ ᴜꜱᴇʀ »</b> {new_user_name}\n"
                    f"🔗 <b>ᴜꜱᴇʀɴᴀᴍᴇ »</b> {new_user_username}\n"
                    f"🆔 <b>ᴜꜱᴇʀ ɪᴅ »</b> <code>{uid}</code>\n"
                    f"👥 <b>ᴛᴏᴛᴀʟ ʀᴇꜰᴇʀʀᴀʟꜱ »</b> {db[rid].get('referrals_count', 0)}\n\n"
                    "💰 <b>ᴊᴀʙ ʏᴇ ᴜꜱᴇʀ ꜰᴜɴᴅ ᴀᴅᴅ ᴋᴀʀᴇɢᴀ, ᴀᴀᴘᴋᴏ ʀᴇꜰᴇʀʀᴀʟ ʙᴏɴᴜꜱ ᴍɪʟᴇɢᴀ.</b>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    else:
        if "active" not in db[uid]:
            db[uid]["active"] = True
        if message:
            db[uid]["name"] = message.from_user.first_name
            db[uid]["username"] = message.from_user.username or "No Username"

    save_json(DB_FILE, db)
    return True

def get_balance(user_id):
    db = load_json(DB_FILE)
    return db.get(str(user_id), {}).get("balance", 0.0)

def update_balance(user_id, amount):
    db = load_json(DB_FILE)
    uid = str(user_id)
    if uid in db:
        db[uid]["balance"] = round(db[uid]["balance"] + amount, 2)
        save_json(DB_FILE, db)

# Function to record fund requests history (approved/rejected)
def log_fund_transaction(user_id, amount, status="approved", utr="", has_photo=False, request_id=""):
    history = load_json(FUNDS_HISTORY_FILE)
    uid = str(user_id)
    if uid not in history:
        history[uid] = []

    current_time = datetime.now().strftime("%d %b %Y • %I:%M %p")
    history[uid].append({
        "amount": float(amount),
        "date": current_time,
        "status": str(status or "approved"),
        "utr": str(utr or ""),
        "has_photo": bool(has_photo),
        "request_id": str(request_id or "")
    })
    save_json(FUNDS_HISTORY_FILE, history)


def create_fund_request(user_id, amount, utr="", has_photo=False):
    """Fund request ko pending state me save karta hai taaki approve button dobara click hone par balance double add na ho."""
    req_db = load_json(FUND_REQUESTS_FILE)
    request_id = uuid.uuid4().hex[:12]
    req_db[request_id] = {
        "user_id": str(user_id),
        "amount": float(amount),
        "utr": str(utr or ""),
        "has_photo": bool(has_photo),
        "status": "pending",
        "created_at": datetime.now().strftime("%d-%m-%Y %I:%M %p")
    }
    save_json(FUND_REQUESTS_FILE, req_db)
    return request_id

def get_pending_fund_request(request_id):
    req_db = load_json(FUND_REQUESTS_FILE)
    req = req_db.get(str(request_id))
    if not req:
        return None, req_db
    if req.get("status") != "pending":
        return None, req_db
    return req, req_db


def give_referral_commission(funded_user_id, amount):
    """Referred user fund approve hone par referrer ko 2% bonus add karta hai."""
    try:
        db = load_json(DB_FILE)
        uid = str(funded_user_id)

        if uid not in db:
            return 0.0

        referrer = db.get(uid, {}).get("referred_by")
        if not referrer:
            return 0.0

        rid = str(referrer)
        if rid == uid or rid not in db:
            return 0.0

        commission = round(float(amount) * 0.02, 2)
        if commission <= 0:
            return 0.0

        db[rid]["balance"] = round(float(db[rid].get("balance", 0)) + commission, 2)
        db[rid]["referral_earnings"] = round(float(db[rid].get("referral_earnings", 0)) + commission, 2)
        save_json(DB_FILE, db)

        try:
            log_wallet(rid, commission, f"ʀᴇꜰᴇʀʀᴀʟ ʙᴏɴᴜꜱ 2% ꜰʀᴏᴍ {uid}")
        except Exception:
            pass

        try:
            bot.send_message(
                int(rid),
                "🎁 <b>ʀᴇꜰᴇʀʀᴀʟ ʙᴏɴᴜꜱ ʀᴇᴄᴇɪᴠᴇᴅ!</b>\n\n"
                f"👤 <b>ʀᴇꜰᴇʀʀᴇᴅ ᴜꜱᴇʀ »</b> <code>{uid}</code>\n"
                f"💰 <b>ꜰᴜɴᴅ ᴀᴅᴅᴇᴅ »</b> ₹{float(amount):.2f}\n"
                f"🎉 <b>ʏᴏᴜʀ 2% ʙᴏɴᴜꜱ »</b> ₹{commission:.2f}\n"
                f"💳 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ »</b> ₹{db[rid]['balance']:.2f}",
                parse_mode="HTML"
            )
        except Exception:
            pass

        return commission

    except Exception as e:
        print("Referral commission error:", e)
        return 0.0


user_orders = {}
user_funds = {}
admin_state = {}
search_results = {}

# Services Mapping
SERVICES = _load_static_json(SERVICES_FILE, {})

def get_service_multiplier(sid):
    sid = str(sid)

    custom = load_json(MARGINS_FILE)

    if sid in custom:
        return float(custom[sid])

    return float(MULTIPLIERS.get(sid, 1))

def find_service(srv_id):
    srv_id = str(srv_id)

    for cat, items in SERVICES.items():
        if srv_id in items:
            return items[srv_id]

    added = load_json(ADDED_SERVICES_FILE)
    if srv_id in added:
        return [added[srv_id].get("name", "Unknown"), float(added[srv_id].get("price", 0))]

    return None


def get_bot_service_ids():
    ids = []

    for category in SERVICES.values():
        for sid in category.keys():
            ids.append(str(sid))

    added = load_json(ADDED_SERVICES_FILE)
    for sid in added.keys():
        ids.append(str(sid))

    return ids

def find_panel_service(sid):
    sid = str(sid)

    for s in get_all_panel_services():
        if str(s.get("service")) == sid:
            return s

    return None

def process_add_service_ids(message):
    if message.chat.id != ADMIN_ID:
        return

    ids = message.text.replace(",", " ").replace("\n", " ").split()
    ids = [str(x).strip() for x in ids if x.strip()]

    if not ids:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return

    added_db = load_json(ADDED_SERVICES_FILE)
    valid = []
    text = "✅ <b>ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏᴜɴᴅ</b>\n\n"

    for sid in ids:
        if find_service(sid):
            text += f"⚠️ <b>{sid}</b> already bot me added hai.\n\n"
            continue

        panel_service = find_panel_service(sid)

        if not panel_service:
            text += f"❌ <b>{sid}</b> panel me nahi mila.\n\n"
            continue

        name = panel_service.get("name", "Unknown")
        rate = float(panel_service.get("rate", 0))

        valid.append({
            "id": sid,
            "panel_name": name,
            "panel_price": rate
        })

        text += (
            f"🆔 <b>{sid}</b>\n"
            f"📦 <b>ᴘᴀɴᴇʟ ɴᴀᴍᴇ »</b> {html.escape(name)}\n"
            f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{rate:.2f}\n\n"
        )

    if not valid:
        bot.send_message(ADMIN_ID, text[:4000], parse_mode="HTML")
        return

    admin_state[ADMIN_ID] = {
        "add_services": valid,
        "add_index": 0,
        "added_result": []
    }

    bot.send_message(ADMIN_ID, text[:4000], parse_mode="HTML")
    ask_add_service_name()


def ask_add_service_name():
    state = admin_state.get(ADMIN_ID)

    if not state:
        return

    services = state.get("add_services", [])
    index = state.get("add_index", 0)

    if index >= len(services):
        finish_add_services()
        return

    item = services[index]

    subcat_key = state.get("current_subcat", "")
    subcat_name = ADD_SERVICE_CATS[state["current_platform"]]["subs"].get(subcat_key, subcat_key)

    msg = bot.send_message(
        ADMIN_ID,
        f"📦 <b>ᴇɴᴛᴇʀ ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ</b>\n\n"
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{item['id']}</code>\n"
        f"📁 <b>ꜱᴜʙ ᴄᴀᴛᴇɢᴏʀʏ »</b> {subcat_name}\n"
        f"📦 <b>ᴘᴀɴᴇʟ ɴᴀᴍᴇ »</b> {html.escape(item['panel_name'])}\n"
        f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{item['panel_price']:.2f}",
        parse_mode="HTML"
    )

    bot.register_next_step_handler(msg, process_add_service_name)

def process_add_service_name(message):
    if message.chat.id != ADMIN_ID:
        return

    state = admin_state.get(ADMIN_ID)
    if not state:
        return

    name = message.text.strip()

    if not name:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴀᴍᴇ ᴇᴍᴘᴛʏ ɴᴀʜɪ ʜᴏ ꜱᴀᴋᴛᴀ</b>", parse_mode="HTML")
        ask_add_service_name()
        return

    state["current_name"] = name
    admin_state[ADMIN_ID] = state

    msg = bot.send_message(
        ADMIN_ID,
        "💎 <b>ᴇɴᴛᴇʀ ᴍᴀʀɢɪɴ:</b>\n\n"
        "ᴇxᴀᴍᴘʟᴇ:\n"
        "<code>2</code>\n"
        "<code>1.5</code>\n"
        "<code>3</code>",
        parse_mode="HTML"
    )

    bot.register_next_step_handler(msg, process_add_service_margin)



def get_platform_prefix_from_subcat(subcat):
    subcat = str(subcat or "")
    key = subcat.split("_")[0]

    platform_names = {
        "ig": "ɪɴꜱᴛᴀɢʀᴀᴍ",
        "yt": "ʏᴏᴜᴛᴜʙᴇ",
        "tg": "ᴛᴇʟᴇɢʀᴀᴍ",
        "fb": "ꜰᴀᴄᴇʙᴏᴏᴋ",
        "tt": "ᴛɪᴋᴛᴏᴋ",
        "tw": "ᴛᴡɪᴛᴛᴇʀ",
        "wa": "ᴡʜᴀᴛꜱᴀᴘᴘ",
        "web": "ᴡᴇʙꜱɪᴛᴇ",
        "sp": "ꜱᴘᴏᴛɪꜰʏ",
        "twitch": "ᴛᴡɪᴛᴄʜ",
        "ln": "ʟɪɴᴋᴇᴅɪɴ",
        "th": "ᴛʜʀᴇᴀᴅꜱ",
        "dc": "ᴅɪꜱᴄᴏʀᴅ",
        "sc": "ꜱɴᴀᴘᴄʜᴀᴛ",
        "rd": "ʀᴇᴅᴅɪᴛ",
        "gg": "ɢᴏᴏɢʟᴇ",
        "oth": "ᴏᴛʜᴇʀ",
    }
    return platform_names.get(key, "")


def ensure_platform_in_service_name(name, subcat):
    name = str(name or "Unknown")
    prefix = get_platform_prefix_from_subcat(subcat)

    if not prefix:
        return name

    known_prefixes = [
        "ɪɴꜱᴛᴀɢʀᴀᴍ", "ʏᴏᴜᴛᴜʙᴇ", "ᴛᴇʟᴇɢʀᴀᴍ", "ꜰᴀᴄᴇʙᴏᴏᴋ",
        "ᴛɪᴋᴛᴏᴋ", "ᴛᴡɪᴛᴛᴇʀ", "ᴡʜᴀᴛꜱᴀᴘᴘ", "ᴡᴇʙꜱɪᴛᴇ",
        "ꜱᴘᴏᴛɪꜰʏ", "ᴛᴡɪᴛᴄʜ", "ʟɪɴᴋᴇᴅɪɴ", "ᴛʜʀᴇᴀᴅꜱ",
        "ᴅɪꜱᴄᴏʀᴅ", "ꜱɴᴀᴘᴄʜᴀᴛ", "ʀᴇᴅᴅɪᴛ", "ɢᴏᴏɢʟᴇ", "ᴏᴛʜᴇʀ",
    ]

    if any(name.startswith(p) for p in known_prefixes):
        return name

    return f"{prefix} {name}"


def process_add_service_margin(message):
    if message.chat.id != ADMIN_ID:
        return

    state = admin_state.get(ADMIN_ID)
    if not state:
        return

    try:
        margin = float(message.text.strip())
        if margin <= 0:
            raise ValueError
    except:
        msg = bot.send_message(
            ADMIN_ID,
            "❌ <b>ɪɴᴠᴀʟɪᴅ ᴍᴀʀɢɪɴ</b>\n\n"
            "Example: <code>2</code> या <code>1.5</code>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_add_service_margin)
        return

    services = state.get("add_services", [])
    index = state.get("add_index", 0)
    item = services[index]

    sid = item["id"]
    subcat = state.get("current_subcat", item.get("subcat", ""))
    bot_name = state.get("current_name", "Unknown")
    bot_name = ensure_platform_in_service_name(bot_name, subcat)
    panel_price = float(item.get("panel_price", 0))
    bot_price = panel_price * margin

    added_db = load_json(ADDED_SERVICES_FILE)
    added_db[sid] = {
        "name": bot_name,
        "subcat": subcat,
        "panel_name": item.get("panel_name", "Unknown"),
        "margin": margin,
        "price": round(bot_price, 4),
        "date": datetime.now().strftime("%d-%m-%Y %I:%M %p")
    }
    save_json(ADDED_SERVICES_FILE, added_db)

    set_margin(sid, margin)

    state["added_result"].append({
        "id": sid,
        "name": bot_name,
        "margin": margin,
        "panel_price": panel_price,
        "bot_price": bot_price
    })

    state["add_index"] = index + 1
    state.pop("current_name", None)
    admin_state[ADMIN_ID] = state

    ask_add_service_name()

ADDED_SERVICES_FILE = "added_services.json"

ADD_SERVICE_CATS = {
    "ig": {
        "title": "ɪɴꜱᴛᴀɢʀᴀᴍ",
        "icon": "📸",
        "subs": {
            "ig_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "ig_views": "👁️ ʀᴇᴇʟ ᴠɪᴇᴡꜱ",
            "ig_likes": "❤️ ʟɪᴋᴇꜱ",
            "ig_votes": "🗳️ ᴘᴏʟʟ ᴠᴏᴛᴇꜱ",
            "ig_story": "📖 ꜱᴛᴏʀʏ ᴠɪᴇᴡꜱ",
            "ig_broadcast": "📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ",
            "ig_comments": "💬 ᴄᴏᴍᴍᴇɴᴛꜱ",
            "ig_comment_likes": "👍 ᴄᴏᴍᴍᴇɴᴛ ʟɪᴋᴇꜱ",
            "ig_shares": "🔄 ꜱʜᴀʀᴇꜱ",
            "ig_reposts": "♻️ ʀᴇᴘᴏꜱᴛꜱ"
        }
    },
    "yt": {
        "title": "ʏᴏᴜᴛᴜʙᴇ",
        "icon": "🎞️",
        "subs": {
            "yt_subscribers": "👥 ꜱᴜʙꜱᴄʀɪʙᴇʀꜱ",
            "yt_views": "👁️ ᴠɪᴇᴡꜱ",
            "yt_live_views": "🎥 ʟɪᴠᴇ ᴠɪᴇᴡꜱ",
            "yt_likes": "❤️ ʟɪᴋᴇꜱ",
            "yt_live_like": "🎥 ʟɪᴠᴇ ʟɪᴋᴇꜱ",
            "yt_watchtime": "⏱️ ᴡᴀᴛᴄʜᴛɪᴍᴇ",
            "yt_comments": "💬 ᴄᴏᴍᴍᴇɴᴛꜱ",
            "yt_comment_likes": "👍 ᴄᴏᴍᴍᴇɴᴛ ʟɪᴋᴇꜱ"
        }
    },
    "tg": {
        "title": "ᴛᴇʟᴇɢʀᴀᴍ",
        "icon": "✈️",
        "subs": {
            "tg_premium": "👑 ᴘʀᴇᴍɪᴜᴍ",
            "tg_members": "👥 ᴍᴇᴍʙᴇʀꜱ",
            "tg_views": "👁️ ᴘᴏꜱᴛ ᴠɪᴇᴡꜱ",
            "tg_reactions": "❤️ ʀᴇᴀᴄᴛɪᴏɴꜱ",
            "tg_bot_start": "🤖 ʙᴏᴛ ꜱᴛᴀʀᴛ",
            "tg_auto_reactions": "⚡ ᴀᴜᴛᴏ ʀᴇᴀᴄᴛɪᴏɴꜱ",
            "tg_auto_post_views": "👁️ ᴀᴜᴛᴏ ᴘᴏꜱᴛ ᴠɪᴇᴡꜱ",
            "tg_poll_votes": "🗳️ ᴘᴏʟʟ ᴠᴏᴛᴇꜱ",
            "tg_shares": "🔄 ꜱʜᴀʀᴇꜱ",
            "tg_boost": "🚀 ʙᴏᴏꜱᴛ"
        }
    },
    "fb": {
        "title": "ꜰᴀᴄᴇʙᴏᴏᴋ",
        "icon": "📘",
        "subs": {
            "fb_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "fb_likes_followers": "👍 ᴘᴀɢᴇ ʟɪᴋᴇꜱ + ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "fb_likes": "❤️ ᴘᴏꜱᴛ ʟɪᴋᴇꜱ",
            "fb_views": "👁️ ᴠɪᴅᴇᴏ ᴠɪᴇᴡꜱ",
            "fb_comments": "💬 ᴄᴏᴍᴍᴇɴᴛꜱ",
            "fb_shares": "🔄 ꜱʜᴀʀᴇꜱ",
            "fb_reactions": "😀 ʀᴇᴀᴄᴛɪᴏɴꜱ",
            "fb_group_members": "👥 ɢʀᴏᴜᴘ ᴍᴇᴍʙᴇʀꜱ"
        }
    },
    "tt": {
        "title": "ᴛɪᴋᴛᴏᴋ",
        "icon": "🎵",
        "subs": {
            "tt_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "tt_views": "👁️ ᴠɪᴇᴡꜱ",
            "tt_likes": "❤️ ʟɪᴋᴇꜱ",
            "tt_comments": "💬 ᴄᴏᴍᴍᴇɴᴛꜱ",
            "tt_shares": "🔄 ꜱʜᴀʀᴇꜱ",
            "tt_saves": "💾 ꜱᴀᴠᴇꜱ",
            "tt_live": "🎥 ʟɪᴠᴇ"
        }
    },
    "tw": {
        "title": "x / ᴛᴡɪᴛᴛᴇʀ",
        "icon": "❌",
        "subs": {
            "tw_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "tw_likes": "❤️ ʟɪᴋᴇꜱ",
            "tw_retweets": "🔁 ʀᴇᴛᴡᴇᴇᴛꜱ",
            "tw_views": "👁️ ᴠɪᴇᴡꜱ",
            "tw_comments": "💬 ᴄᴏᴍᴍᴇɴᴛꜱ",
            "tw_impressions": "📊 ɪᴍᴘʀᴇꜱꜱɪᴏɴꜱ",
            "tw_spaces": "🎙️ ꜱᴘᴀᴄᴇꜱ"
        }
    },
    "wa": {
        "title": "ᴡʜᴀᴛꜱᴀᴘᴘ",
        "icon": "💬",
        "subs": {
            "wa_channel_followers": "👥 ᴄʜᴀɴɴᴇʟ ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "wa_group_members": "👥 ɢʀᴏᴜᴘ ᴍᴇᴍʙᴇʀꜱ",
            "wa_views": "👁️ ᴠɪᴇᴡꜱ",
            "wa_reactions": "❤️ ʀᴇᴀᴄᴛɪᴏɴꜱ"
        }
    },
    "web": {
        "title": "ᴡᴇʙꜱɪᴛᴇ",
        "icon": "🌐",
        "subs": {
            "web_traffic": "🌐 ᴛʀᴀꜰꜰɪᴄ",
            "web_visits": "👁️ ᴠɪꜱɪᴛꜱ",
            "web_seo": "🔎 ꜱᴇᴏ",
            "web_backlinks": "🔗 ʙᴀᴄᴋʟɪɴᴋꜱ"
        }
    },
    "sp": {
        "title": "ꜱᴘᴏᴛɪꜰʏ",
        "icon": "🎧",
        "subs": {
            "sp_plays": "▶️ ᴘʟᴀʏꜱ",
            "sp_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "sp_saves": "💾 ꜱᴀᴠᴇꜱ",
            "sp_playlist": "🎵 ᴘʟᴀʏʟɪꜱᴛ",
            "sp_monthly_listeners": "👂 ᴍᴏɴᴛʜʟʏ ʟɪꜱᴛᴇɴᴇʀꜱ"
        }
    },
    "twitch": {
        "title": "ᴛᴡɪᴛᴄʜ",
        "icon": "🎮",
        "subs": {
            "twitch_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "twitch_views": "👁️ ᴠɪᴇᴡꜱ",
            "twitch_live_views": "🎥 ʟɪᴠᴇ ᴠɪᴇᴡꜱ",
            "twitch_subs": "⭐ ꜱᴜʙꜱ"
        }
    },
    "ln": {
        "title": "ʟɪɴᴋᴇᴅɪɴ",
        "icon": "💼",
        "subs": {
            "ln_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "ln_connections": "🤝 ᴄᴏɴɴᴇᴄᴛɪᴏɴꜱ",
            "ln_likes": "❤️ ʟɪᴋᴇꜱ",
            "ln_views": "👁️ ᴠɪᴇᴡꜱ",
            "ln_comments": "💬 ᴄᴏᴍᴍᴇɴᴛꜱ"
        }
    },
    "th": {
        "title": "ᴛʜʀᴇᴀᴅꜱ",
        "icon": "🧵",
        "subs": {
            "th_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "th_likes": "❤️ ʟɪᴋᴇꜱ",
            "th_views": "👁️ ᴠɪᴇᴡꜱ",
            "th_reposts": "♻️ ʀᴇᴘᴏꜱᴛꜱ"
        }
    },
    "dc": {
        "title": "ᴅɪꜱᴄᴏʀᴅ",
        "icon": "💬",
        "subs": {
            "dc_members": "👥 ᴍᴇᴍʙᴇʀꜱ",
            "dc_online_members": "🟢 ᴏɴʟɪɴᴇ ᴍᴇᴍʙᴇʀꜱ",
            "dc_boosts": "🚀 ʙᴏᴏꜱᴛꜱ",
            "dc_reactions": "❤️ ʀᴇᴀᴄᴛɪᴏɴꜱ"
        }
    },
    "sc": {
        "title": "ꜱɴᴀᴘᴄʜᴀᴛ",
        "icon": "👻",
        "subs": {
            "sc_followers": "👥 ꜰᴏʟʟᴏᴡᴇʀꜱ",
            "sc_views": "👁️ ᴠɪᴇᴡꜱ",
            "sc_spotlight": "✨ ꜱᴘᴏᴛʟɪɢʜᴛ",
            "sc_likes": "❤️ ʟɪᴋᴇꜱ"
        }
    },
    "rd": {
        "title": "ʀᴇᴅᴅɪᴛ",
        "icon": "👽",
        "subs": {
            "rd_upvotes": "⬆️ ᴜᴘᴠᴏᴛᴇꜱ",
            "rd_comments": "💬 ᴄᴏᴍᴍᴇɴᴛꜱ",
            "rd_members": "👥 ᴍᴇᴍʙᴇʀꜱ",
            "rd_views": "👁️ ᴠɪᴇᴡꜱ"
        }
    },
    "gg": {
        "title": "ɢᴏᴏɢʟᴇ",
        "icon": "🔍",
        "subs": {
            "gg_reviews": "⭐ ʀᴇᴠɪᴇᴡꜱ",
            "gg_maps": "🗺️ ᴍᴀᴘꜱ",
            "gg_seo": "🔎 ꜱᴇᴏ",
            "gg_app_reviews": "📱 ᴀᴘᴘ ʀᴇᴠɪᴇᴡꜱ"
        }
    },
    "oth": {
        "title": "ᴏᴛʜᴇʀ",
        "icon": "📦",
        "subs": {
            "oth_mixed": "📦 ᴍɪxᴇᴅ",
            "oth_custom": "🛠️ ᴄᴜꜱᴛᴏᴍ",
            "oth_misc": "✨ ᴍɪꜱᴄ"
        }
    }
}


def find_panel_service(sid):
    sid = str(sid)
    for s in get_all_panel_services():
        if str(s.get("service")) == sid:
            return s
    return None


def start_add_service(message):
    msg = bot.send_message(
        ADMIN_ID,
        "🆔 <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ:</b>\n\n"
        "<code>6150</code>\n"
        "<code>6150 6152</code>\n"
        "<code>6150,6152,6154</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_add_service_ids)


def process_add_service_ids(message):
    ids = message.text.replace(",", " ").replace("\n", " ").split()
    ids = [str(x).strip() for x in ids if x.strip()]

    valid = []
    text = "✅ <b>ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏᴜɴᴅ</b>\n\n"

    for sid in ids:
        if find_service(sid):
            text += f"⚠️ <b>{sid}</b> already bot me added hai.\n\n"
            continue

        p = find_panel_service(sid)
        if not p:
            text += f"❌ <b>{sid}</b> panel me nahi mila.\n\n"
            continue

        valid.append({
            "id": sid,
            "panel_name": p.get("name", "Unknown"),
            "panel_price": float(p.get("rate", 0))
        })

        text += (
            f"🆔 <b>{sid}</b>\n"
            f"📦 <b>ᴘᴀɴᴇʟ ɴᴀᴍᴇ »</b> {html.escape(p.get('name', 'Unknown'))}\n"
            f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{float(p.get('rate', 0)):.2f}\n\n"
        )

    if not valid:
        bot.send_message(ADMIN_ID, text[:4000], parse_mode="HTML")
        return

    admin_state[ADMIN_ID] = {
        "add_services": valid,
        "add_index": 0,
        "added_result": []
    }

    ask_add_service_category()


def ask_add_service_category():
    state = admin_state.get(ADMIN_ID)
    if not state:
        return
    item = state["add_services"][state["add_index"]]
    state["add_mode"] = "platform"
    admin_state[ADMIN_ID] = state

    bot.send_message(
        ADMIN_ID,
        f"📂 <b>ᴘʟᴀᴛꜰᴏʀᴍ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ</b>\n\n"
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{item['id']}</code>\n"
        f"📦 <b>ᴘᴀɴᴇʟ ɴᴀᴍᴇ »</b> {html.escape(item['panel_name'])}\n"
        f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{item['panel_price']:.2f}",
        parse_mode="HTML",
        reply_markup=_admin_platform_keyboard()
    )


def show_add_service_subcategories(platform):
    state = admin_state.get(ADMIN_ID)
    item = state["add_services"][state["add_index"]]

    state["current_platform"] = platform
    state["add_mode"] = "subcat"
    admin_state[ADMIN_ID] = state

    bot.send_message(
        ADMIN_ID,
        f"📁 <b>ꜱᴜʙ-ᴄᴀᴛᴇɢᴏʀʏ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ</b>\n\n"
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{item['id']}</code>\n"
        f"📂 <b>ᴄᴀᴛᴇɢᴏʀʏ »</b> {ADD_SERVICE_CATS[platform]['title']}",
        parse_mode="HTML",
        reply_markup=_admin_subcat_keyboard(platform)
    )


def show_add_ig_follower_type():
    state = admin_state.get(ADMIN_ID)
    if not state:
        return

    item = state["add_services"][state["add_index"]]
    state["current_subcat"] = "ig_followers"
    state["add_mode"] = "igft"
    admin_state[ADMIN_ID] = state

    bot.send_message(
        ADMIN_ID,
        f"👥 <b>ꜱᴇʟᴇᴄᴛ ꜰᴏʟʟᴏᴡᴇʀꜱ ᴛʏᴘᴇ</b>\n\n"
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{item['id']}</code>\n"
        f"📂 <b>ᴄᴀᴛᴇɢᴏʀʏ »</b> ɪɴꜱᴛᴀɢʀᴀᴍ / ꜰᴏʟʟᴏᴡᴇʀꜱ",
        parse_mode="HTML",
        reply_markup=_admin_ig_follow_keyboard()
    )


_IG_FOLLOW_TYPE_LABELS = {
    "normal": "👥 ɴᴏʀᴍᴀʟ ꜰᴏʟʟᴏᴡᴇʀꜱ",
    "low_drop": "💧 ʟᴏᴡ ᴅʀᴏᴘ ꜰᴏʟʟᴏᴡᴇʀꜱ",
    "india": "🇮🇳 ɪɴᴅɪᴀ ꜰᴏʟʟᴏᴡᴇʀꜱ",
    "non_drop": "🛡️ ɴᴏɴ ᴅʀᴏᴘ ꜰᴏʟʟᴏᴡᴇʀꜱ",
}


def ask_add_service_name(subcat_key, ig_follow_type=None):
    state = admin_state.get(ADMIN_ID)
    item = state["add_services"][state["add_index"]]

    state["current_subcat"] = subcat_key
    if ig_follow_type:
        state["current_ig_follow_type"] = ig_follow_type
    state.pop("add_mode", None)
    admin_state[ADMIN_ID] = state

    subcat_label = ADD_SERVICE_CATS[state["current_platform"]]["subs"][subcat_key]
    if subcat_key == "ig_followers" and ig_follow_type:
        subcat_label = f"{subcat_label} / {_IG_FOLLOW_TYPE_LABELS.get(ig_follow_type, ig_follow_type)}"

    msg = bot.send_message(
        ADMIN_ID,
        f"📦 <b>ᴇɴᴛᴇʀ ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ</b>\n\n"
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{item['id']}</code>\n"
        f"📁 <b>ꜱᴜʙ ᴄᴀᴛᴇɢᴏʀʏ »</b> {subcat_label}\n"
        f"📦 <b>ᴘᴀɴᴇʟ ɴᴀᴍᴇ »</b> {html.escape(item['panel_name'])}\n"
        f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{item['panel_price']:.2f}",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_add_service_name)


def process_add_service_name(message):
    text = (message.text or "").strip()
    if text in ["⬅️ ʙᴀᴄᴋ", "⬅️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ"]:
        _handle_add_flow_back(message)
        return
    if text in ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
        admin_state.pop(ADMIN_ID, None)
        bot.send_message(ADMIN_ID, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(ADMIN_ID))
        return
    name = text
    if not name:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴀᴍᴇ ᴇᴍᴘᴛʏ ɴᴀʜɪ ʜᴏ ꜱᴀᴋᴛᴀ</b>", parse_mode="HTML")
        ask_add_service_name(admin_state.get(ADMIN_ID, {}).get("current_subcat", ""), admin_state.get(ADMIN_ID, {}).get("current_ig_follow_type") or None)
        return

    state = admin_state.get(ADMIN_ID)
    state["current_name"] = name
    admin_state[ADMIN_ID] = state

    msg = bot.send_message(
        ADMIN_ID,
        "💎 <b>ᴇɴᴛᴇʀ ᴍᴀʀɢɪɴ:</b>\n\n"
        "<code>2</code>\n<code>1.5</code>\n<code>3</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_add_service_margin)


def process_add_service_margin(message):
    text = (message.text or "").strip()
    if text in ["⬅️ ʙᴀᴄᴋ", "⬅️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ"]:
        state = admin_state.get(ADMIN_ID, {})
        subcat = state.get("current_subcat")
        igft = state.get("current_ig_follow_type") or None
        if subcat:
            ask_add_service_name(subcat, igft)
        else:
            _handle_add_flow_back(message)
        return
    if text in ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
        admin_state.pop(ADMIN_ID, None)
        bot.send_message(ADMIN_ID, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(ADMIN_ID))
        return
    try:
        margin = float(text)
        if margin <= 0:
            raise ValueError
    except:
        msg = bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴍᴀʀɢɪɴ</b>\n\n<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>2</code> ᴏʀ <code>1.5</code>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_add_service_margin)
        return

    state = admin_state.get(ADMIN_ID)
    item = state["add_services"][state["add_index"]]

    sid = item["id"]
    subcat = state["current_subcat"]
    ig_follow_type = state.get("current_ig_follow_type", "")
    bot_name = state["current_name"]
    panel_price = float(item["panel_price"])
    bot_price = panel_price * margin

    added_db = load_json(ADDED_SERVICES_FILE)
    added_db[sid] = {
        "name": bot_name,
        "subcat": subcat,
        "ig_follow_type": ig_follow_type,
        "panel_name": item["panel_name"],
        "margin": margin,
        "price": round(bot_price, 4),
        "date": datetime.now().strftime("%d-%m-%Y %I:%M %p")
    }
    save_json(ADDED_SERVICES_FILE, added_db)

    set_margin(sid, margin)

    state["added_result"].append({
        "id": sid,
        "name": bot_name,
        "subcat": subcat,
        "ig_follow_type": ig_follow_type,
        "margin": margin,
        "panel_price": panel_price,
        "bot_price": bot_price
    })

    state["add_index"] += 1
    state.pop("current_name", None)
    state.pop("current_subcat", None)
    state.pop("current_ig_follow_type", None)
    state.pop("current_platform", None)
    admin_state[ADMIN_ID] = state

    if state["add_index"] >= len(state["add_services"]):
        finish_add_services()
    else:
        ask_add_service_category()



def _show_admin_service_management(chat_id=ADMIN_ID):
    send_admin_category_message(chat_id, "📦 ꜱᴇʀᴠɪᴄᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ")


def _handle_add_flow_back(message=None):
    state = admin_state.get(ADMIN_ID, {})
    mode = state.get("add_mode")
    if mode == "platform":
        admin_state.pop(ADMIN_ID, None)
        _show_admin_service_management()
        return True
    if mode == "subcat":
        ask_add_service_category()
        return True
    if mode == "igft":
        show_add_service_subcategories(state.get("current_platform", "ig"))
        return True
    subcat = state.get("current_subcat")
    if subcat:
        platform = state.get("current_platform", "ig")
        state["add_mode"] = "subcat"
        admin_state[ADMIN_ID] = state
        show_add_service_subcategories(platform)
        return True
    return False


def _handle_shift_flow_back(message=None):
    state = admin_state.get(ADMIN_ID, {})
    mode = state.get("shift_mode")
    if mode == "source_platform":
        admin_state.pop(ADMIN_ID, None)
        _show_admin_service_management()
        return True
    if mode == "source_subcat":
        start_service_shift_flow(message)
        return True
    if mode == "source_igft":
        show_shift_source_subcategories(message, state.get("shift_source_platform", "ig"))
        return True
    if mode == "service_select":
        subcat = state.get("shift_source_subcat", "")
        if subcat == "ig_followers":
            show_shift_source_ig_follow_types(message)
        else:
            show_shift_source_subcategories(message, state.get("shift_source_platform", "ig"))
        return True
    if mode == "dest_platform":
        show_shift_service_list(message, state.get("shift_source_subcat", ""), state.get("shift_source_ig_follow_type") or None)
        return True
    if mode == "dest_subcat":
        choose_shift_destination_platform(message, state.get("shift_sid", ""))
        return True
    if mode == "dest_igft":
        show_shift_destination_subcategories(message, state.get("shift_destination_platform", "ig"))
        return True
    return False

def finish_add_services():
    results = admin_state.get(ADMIN_ID, {}).get("added_result", [])

    admin_msg = (
        "✅ <b>ꜱᴇʀᴠɪᴄᴇ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ</b>\n\n"
        if len(results) == 1 else
        "✅ <b>ꜱᴇʀᴠɪᴄᴇꜱ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ</b>\n\n"
    )

    user_msg = (
        "🆕 <b>ɴᴇᴡ ꜱᴇʀᴠɪᴄᴇ ᴀᴅᴅᴇᴅ</b>\n\n"
        if len(results) == 1 else
        "🆕 <b>ɴᴇᴡ ꜱᴇʀᴠɪᴄᴇꜱ ᴀᴅᴅᴇᴅ</b>\n\n"
    )

    for r in results:
        admin_msg += (
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{r['id']}</code>\n"
            f"📁 <b>ꜱᴜʙ ᴄᴀᴛᴇɢᴏʀʏ »</b> {r['subcat']}\n"
            + (f"👥 <b>ꜰᴏʟʟᴏᴡᴇʀꜱ ᴛʏᴘᴇ »</b> {_IG_FOLLOW_TYPE_LABELS.get(r.get('ig_follow_type'), r.get('ig_follow_type'))}\n" if r.get('ig_follow_type') else "")
            + f"📦 <b>ʙᴏᴛ ɴᴀᴍᴇ »</b> {html.escape(r['name'])}\n"
            f"💎 <b>ᴍᴀʀɢɪɴ »</b> ×{r['margin']:.2f}\n"
            f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{r['panel_price']:.2f}\n"
            f"💰 <b>ʙᴏᴛ ᴘʀɪᴄᴇ »</b> ₹{r['bot_price']:.2f}\n\n"
        )

        user_msg += (
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{r['id']}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(r['name'])}\n"
            f"💰 <b>ᴘʀɪᴄᴇ »</b> ₹{r['bot_price']:.2f}\n\n"
        )

    admin_msg += "🎉 <b>ꜱᴇʀᴠɪᴄᴇ ɪꜱ ɴᴏᴡ ʟɪᴠᴇ ɪɴ ᴛʜᴇ ʙᴏᴛ.</b>"
    user_msg += "✅ <b>ɴᴏᴡ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ᴛʜᴇ ʙᴏᴛ.</b>\n\n💡 <b>ᴏʀᴅᴇʀ ɴᴏᴡ ᴀɴᴅ ᴇɴᴊᴏʏ ꜰᴀꜱᴛ ᴅᴇʟɪᴠᴇʀʏ.</b>"

    bot.send_message(ADMIN_ID, admin_msg[:4000], parse_mode="HTML")
    send_to_all_users(user_msg[:4000])
    try:
        for r in results:
            _pending_remove("new", str(r.get("id")))
            _pending_remove("enabled", str(r.get("id")))
    except Exception:
        pass
    admin_state.pop(ADMIN_ID, None)


def _bot_service_name(sid):
    try:
        info = find_service(str(sid))
        if info:
            return str(info[0])
    except Exception:
        pass
    return "Unknown"


def _remove_service_from_bot(sid):
    global SERVICES
    sid = str(sid).strip()
    services_db = load_json(SERVICES_FILE)
    if not isinstance(services_db, dict):
        services_db = {}
    added_db = load_json(ADDED_SERVICES_FILE)
    if not isinstance(added_db, dict):
        added_db = {}
    margins_db = load_json(MARGINS_FILE)
    if not isinstance(margins_db, dict):
        margins_db = {}

    removed = False
    removed_name = "Unknown"
    removed_from = ""

    removed_row = None
    removed_source = ""
    for subcat, items in list(services_db.items()):
        if isinstance(items, dict) and sid in items:
            val = items.pop(sid, None)
            removed_row = val
            removed_source = "services.json"
            removed_name = val[0] if isinstance(val, list) and val else "Unknown"
            removed_from = subcat
            removed = True
            break

    if sid in added_db:
        row = added_db.pop(sid, {})
        removed_row = row
        removed_source = "added_services.json"
        removed_name = row.get("name", removed_name)
        removed_from = row.get("subcat", removed_from)
        removed = True

    margins_db.pop(sid, None)
    save_json(SERVICES_FILE, services_db)
    save_json(ADDED_SERVICES_FILE, added_db)
    save_json(MARGINS_FILE, margins_db)
    SERVICES = services_db
    if removed:
        try:
            _recent_removed_add(sid, removed_name, removed_from, removed_source, removed_row)
        except Exception as e:
            print("recent removed save error:", e)
    return removed, removed_name, removed_from



# --- PENDING ADMIN ACTIONS ---
def _pending_actions_load():
    data = load_json(PENDING_ACTIONS_FILE)
    return data if isinstance(data, dict) else {}


def _pending_actions_save(data):
    save_json(PENDING_ACTIONS_FILE, data if isinstance(data, dict) else {})


def _pending_key(kind, sid):
    return f"{kind}_{str(sid).strip()}"


def _pending_add(kind, sid, name="Unknown", rate=None):
    data = _pending_actions_load()
    data[_pending_key(kind, sid)] = {
        "kind": str(kind),
        "sid": str(sid),
        "name": str(name or "Unknown"),
        "rate": rate,
        "time": datetime.now().strftime("%d-%m-%Y %I:%M %p"),
        "status": "pending"
    }
    _pending_actions_save(data)


def _pending_remove(kind, sid):
    data = _pending_actions_load()
    data.pop(_pending_key(kind, sid), None)
    _pending_actions_save(data)


def _pending_action_markup(kind, sid):
    mk = types.InlineKeyboardMarkup(row_width=2)
    sid = str(sid)
    if kind == "new":
        mk.add(
            types.InlineKeyboardButton("➕ ᴀᴅᴅ ꜱᴇʀᴠɪᴄᴇ", callback_data=f"autoadd_service_{sid}"),
            types.InlineKeyboardButton("❌ ɪɢɴᴏʀᴇ", callback_data=f"autoignore_new_{sid}")
        )
    elif kind == "disabled":
        mk.add(
            types.InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ꜰʀᴏᴍ ʙᴏᴛ", callback_data=f"autoremove_service_{sid}"),
            types.InlineKeyboardButton("❌ ɪɢɴᴏʀᴇ", callback_data=f"autoignore_disabled_{sid}")
        )
    elif kind == "enabled":
        return mk
    return mk


def _pending_message(row):
    kind = row.get("kind")
    sid = str(row.get("sid", ""))
    name = html.escape(str(row.get("name", "Unknown")))
    rate = row.get("rate")
    t = html.escape(str(row.get("time", "")))
    if kind == "new":
        price_line = f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{float(rate):.4f}\n" if rate not in (None, "") else ""
        return (
            "🆕 <b>ɴᴇᴡ ꜱᴇʀᴠɪᴄᴇ</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(sid)}</code>\n"
            f"📦 <b>ɴᴀᴍᴇ »</b> {name}\n"
            f"{price_line}"
            f"🕒 <b>ᴛɪᴍᴇ »</b> {t}"
        )
    if kind == "disabled":
        return (
            "🚫 <b>ᴅɪꜱᴀʙʟᴇᴅ ꜱᴇʀᴠɪᴄᴇ</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(sid)}</code>\n"
            f"📦 <b>ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇ »</b> {name}\n"
            f"🕒 <b>ᴛɪᴍᴇ »</b> {t}"
        )
    if kind == "enabled":
        return (
            "✅ <b>ꜱᴇʀᴠɪᴄᴇ ᴇɴᴀʙʟᴇᴅ ᴀɢᴀɪɴ</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(sid)}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {name}\n"
            f"🕒 <b>ᴛɪᴍᴇ »</b> {t}"
        )
    return f"📌 <b>ᴘᴇɴᴅɪɴɢ ᴀᴄᴛɪᴏɴ</b>\n\n🆔 <code>{html.escape(sid)}</code>"


def show_pending_actions():
    data = _pending_actions_load()
    rows = [r for r in data.values() if isinstance(r, dict) and r.get("status", "pending") == "pending"]
    if not rows:
        bot.send_message(ADMIN_ID, "📌 <b>ᴘᴇɴᴅɪɴɢ ᴀᴄᴛɪᴏɴꜱ ᴇᴍᴘᴛʏ</b>", parse_mode="HTML")
        return
    bot.send_message(ADMIN_ID, f"📌 <b>ᴘᴇɴᴅɪɴɢ ᴀᴄᴛɪᴏɴꜱ</b>\n\n📦 <b>ᴛᴏᴛᴀʟ »</b> {len(rows)}", parse_mode="HTML")
    for row in rows[-50:]:
        bot.send_message(
            ADMIN_ID,
            _pending_message(row),
            parse_mode="HTML",
            reply_markup=_pending_action_markup(row.get("kind"), row.get("sid"))
        )


def _send_panel_enabled_alert(sid, item=None):
    try:
        name = item.get("name", _bot_service_name(sid)) if isinstance(item, dict) else _bot_service_name(sid)
        msg = (
            "✅ <b>ꜱᴇʀᴠɪᴄᴇ ɪꜱ ʙᴀᴄᴋ ᴏɴʟɪɴᴇ</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(str(sid))}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(name))}\n\n"
            "✅ <b>ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴀᴄᴛɪᴠᴇ ᴀɢᴀɪɴ.</b>"
        )
        bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
        _pending_remove("enabled", sid)
    except Exception as e:
        print("enabled service alert error:", e)
# --- END PENDING ADMIN ACTIONS ---

def _auto_alert_markup(kind, sid):
    # Backward compatible wrapper
    return _pending_action_markup(kind, sid)


def _send_panel_price_alert(sid, name, old_rate, new_rate):
    try:
        old_rate = float(old_rate or 0)
        new_rate = float(new_rate or 0)
        direction = "📈 ᴘʀɪᴄᴇ ɪɴᴄʀᴇᴀꜱᴇᴅ" if new_rate > old_rate else "📉 ᴘʀɪᴄᴇ ᴅᴇᴄʀᴇᴀꜱᴇᴅ"
        multi = get_service_multiplier(sid)
        msg = (
            f"🔔 <b>{direction}</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(str(sid))}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(name))}\n"
            f"📊 <b>ᴘᴀɴᴇʟ »</b> ₹{old_rate:.4f} ➜ ₹{new_rate:.4f}\n"
            f"💎 <b>ʙᴏᴛ »</b> ₹{old_rate * multi:.4f} ➜ ₹{new_rate * multi:.4f}\n\n"
            f"⚡ <b>ᴀᴜᴛᴏ ᴘᴀɴᴇʟ ᴀʟᴇʀᴛ</b>"
        )
        bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
    except Exception as e:
        print("panel price alert error:", e)


def _send_panel_new_service_alert(sid, item):
    try:
        name = item.get("name", "Unknown") if isinstance(item, dict) else "Unknown"
        rate = float(item.get("rate", 0) or 0) if isinstance(item, dict) else 0
        _pending_add("new", sid, name=name, rate=rate)
        msg = (
            "🆕 <b>ɴᴇᴡ ᴘᴀɴᴇʟ ꜱᴇʀᴠɪᴄᴇ ᴀᴅᴅᴇᴅ</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(str(sid))}</code>\n"
            f"📦 <b>ɴᴀᴍᴇ »</b> {html.escape(str(name))}\n"
            f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{rate:.4f}\n\n"
            "➕ <b>ᴀᴅᴅ ᴛᴏ ʙᴏᴛ ᴋᴀʀɴᴀ ʜᴏ ᴛᴏ ɴɪᴄʜᴇ ʙᴜᴛᴛᴏɴ ᴅᴀʙᴀᴏ.</b>"
        )
        bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=_pending_action_markup("new", sid))
    except Exception as e:
        print("new service alert error:", e)


def _send_panel_disabled_alert(sid):
    try:
        name = _bot_service_name(sid)
        _pending_add("disabled", sid, name=name)
        msg = (
            "⚠️ <b>ᴘᴀɴᴇʟ ꜱᴇʀᴠɪᴄᴇ ᴅɪꜱᴀʙʟᴇᴅ / ɴᴏᴛ ꜰᴏᴜɴᴅ</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(str(sid))}</code>\n"
            f"📦 <b>ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(name))}\n\n"
            "🗑️ <b>ʙᴏᴛ ꜱᴇ ʀᴇᴍᴏᴠᴇ ᴋᴀʀɴᴀ ʜᴏ ᴛᴏ ɴɪᴄʜᴇ ʙᴜᴛᴛᴏɴ ᴅᴀʙᴀᴏ.</b>"
        )
        bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=_pending_action_markup("disabled", sid))
    except Exception as e:
        print("disabled service alert error:", e)


def auto_panel_service_alert_checker(interval_seconds=60):
    """Panel price/new/disabled services ko background me check karke admin ko notification bhejta hai."""
    time.sleep(8)
    while True:
        try:
            services = get_all_panel_services()
            if not isinstance(services, list) or not services:
                time.sleep(interval_seconds)
                continue

            panel_map = {str(x.get("service")): x for x in services if isinstance(x, dict) and x.get("service") is not None}
            current_ids = set(panel_map.keys())
            current_names = {sid: str(item.get("name", "Unknown")) for sid, item in panel_map.items()}
            current_prices = {sid: float(item.get("rate", 0) or 0) for sid, item in panel_map.items()}

            # New panel services alert
            known_services = load_json(KNOWN_SERVICES_FILE)
            if not isinstance(known_services, dict) or not known_services:
                save_json(KNOWN_SERVICES_FILE, current_names)
            else:
                old_ids = set(str(x) for x in known_services.keys())
                new_ids = sorted(current_ids - old_ids, key=lambda x: int(x) if str(x).isdigit() else x)
                for sid in new_ids[:30]:
                    _send_panel_new_service_alert(sid, panel_map[sid])
                save_json(KNOWN_SERVICES_FILE, current_names)

            # Price increase/decrease alert for bot services only
            old_prices = load_json(LAST_PRICE_FILE)
            if not isinstance(old_prices, dict) or not old_prices:
                save_json(LAST_PRICE_FILE, current_prices)
            else:
                bot_ids = set(str(x) for x in get_bot_service_ids())
                history_changed = False
                history = load_json(PRICE_HISTORY_FILE)
                if not isinstance(history, dict):
                    history = {}
                now = datetime.now().strftime("%d-%m-%Y %I:%M %p")
                for sid in sorted(bot_ids & current_ids, key=lambda x: int(x) if str(x).isdigit() else x):
                    if sid not in old_prices:
                        continue
                    old_rate = float(old_prices.get(sid, 0) or 0)
                    new_rate = float(current_prices.get(sid, 0) or 0)
                    if old_rate <= 0 or new_rate <= 0 or old_rate == new_rate:
                        continue
                    _send_panel_price_alert(sid, current_names.get(sid, _bot_service_name(sid)), old_rate, new_rate)
                    if new_rate < old_rate:
                        try:
                            notify_favorite_price_drop(sid, old_rate, new_rate)
                        except Exception as e:
                            print("user price drop notify error:", e)
                    history.setdefault(now, []).append(f"{sid}: ₹{old_rate:.4f} ➜ ₹{new_rate:.4f}")
                    history_changed = True
                if history_changed:
                    save_json(PRICE_HISTORY_FILE, history)
                save_json(LAST_PRICE_FILE, current_prices)

            # Disabled panel service alert for services already in bot
            settings = load_json(SETTINGS_FILE)
            if not isinstance(settings, dict):
                settings = {}
            notified = set(str(x) for x in settings.get("panel_disabled_notified", []))
            bot_ids = set(str(x) for x in get_bot_service_ids())
            disabled_ids = sorted(bot_ids - current_ids, key=lambda x: int(x) if str(x).isdigit() else x)
            for sid in disabled_ids:
                if sid not in notified:
                    _send_panel_disabled_alert(sid)
                    notified.add(sid)
            # Service wapas panel me aa jaye to enabled-again alert bhejo, phir notification lock clear
            back_online_ids = sorted(notified & current_ids, key=lambda x: int(x) if str(x).isdigit() else x)
            enabled_notified = set(str(x) for x in settings.get("panel_enabled_notified", []))
            for sid in back_online_ids:
                if sid not in enabled_notified:
                    _send_panel_enabled_alert(sid, panel_map.get(sid, {}))
                    try:
                        notify_service_back_users(sid)
                    except Exception as e:
                        print("user service back notify error:", e)
                    enabled_notified.add(sid)
            notified = notified & set(disabled_ids)
            enabled_notified = enabled_notified & current_ids
            settings["panel_disabled_notified"] = sorted(notified, key=lambda x: int(x) if str(x).isdigit() else x)
            settings["panel_enabled_notified"] = sorted(enabled_notified, key=lambda x: int(x) if str(x).isdigit() else x)
            save_json(SETTINGS_FILE, settings)

        except Exception as e:
            print("auto panel service alert checker error:", e)
        time.sleep(interval_seconds)

def get_all_panel_services(force=False):
    now = time.monotonic()
    with _PANEL_CACHE_LOCK:
        valid = (
            not force
            and _PANEL_SERVICES_CACHE["data"]
            and now - _PANEL_SERVICES_CACHE["time"] < PANEL_SERVICES_CACHE_TTL
            and _PANEL_SERVICES_CACHE["url"] == SMM_API_URL
            and _PANEL_SERVICES_CACHE["key"] == SMM_API_KEY
        )
        if valid:
            return list(_PANEL_SERVICES_CACHE["data"])
    try:
        payload = _api_post(
            {"key": SMM_API_KEY, "action": "services"},
            timeout=(4, 10)
        ).json()
        if not isinstance(payload, list):
            raise ValueError(str(payload))
        with _PANEL_CACHE_LOCK:
            _PANEL_SERVICES_CACHE.update({
                "data": list(payload), "time": now,
                "url": SMM_API_URL, "key": SMM_API_KEY
            })
        return payload
    except Exception as e:
        print("Panel services fetch error:", e)
        # If panel is temporarily slow, serve the most recent cache instead of hanging/blank response.
        with _PANEL_CACHE_LOCK:
            return list(_PANEL_SERVICES_CACHE["data"])

def start_service_price_checker(message=None):
    msg = bot.send_message(
        ADMIN_ID,
        "💹 <b>ꜱᴇʀᴠɪᴄᴇ ᴘʀɪᴄᴇ ᴄʜᴇᴄᴋᴇʀ</b>\n\n"
        "🆔 <b>ᴇᴋ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ʏᴀ ᴍᴜʟᴛɪᴘʟᴇ ɪᴅꜱ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>\n"
        "<code>567</code> ᴏʀ <code>567 3975 3976</code>\n\n"
        "📋 <b>ꜱᴀʙʜɪ ꜱᴇʀᴠɪᴄᴇꜱ ᴋᴇ ʟɪʏᴇ:</b> <code>ALL</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_service_price_checker)


def process_service_price_checker(message):
    if message.chat.id != ADMIN_ID:
        return

    raw = str(message.text or "").strip()
    if raw in ["⬅️ ʙᴀᴄᴋ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ", "🏠 ᴍᴇɴᴜ"]:
        if raw == "⬅️ ʙᴀᴄᴋ":
            send_admin_category_message(ADMIN_ID, "📊 ᴘʀɪᴄᴇ & ᴍᴀʀɢɪɴ")
        else:
            bot.send_message(ADMIN_ID, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(ADMIN_ID))
        return

    bot_map = get_all_bot_services_map()
    if raw.upper() == "ALL":
        ids = list(bot_map.keys())
    else:
        ids = [x for x in re.split(r"[\s,]+", raw) if x]

    if not ids:
        bot.send_message(ADMIN_ID, "❌ <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ ᴇɴᴛᴇʀ ᴋᴀʀᴏ.</b>", parse_mode="HTML")
        return

    panel_services = get_all_panel_services()
    panel_map = {str(x.get("service")): x for x in panel_services if x.get("service") is not None}
    blocks = []
    missing = []

    def _sort_key(v):
        return (0, int(v)) if str(v).isdigit() else (1, str(v))

    for sid in sorted(dict.fromkeys(map(str, ids)), key=_sort_key):
        s_info = find_service(sid)
        if not s_info:
            missing.append(sid)
            continue
        panel_item = panel_map.get(sid)
        if not panel_item:
            missing.append(sid)
            continue
        try:
            panel_price = float(panel_item.get("rate", 0) or 0)
        except Exception:
            panel_price = 0.0
        normal_margin = float(get_margin(sid))
        vip_margin = float(get_vip_margin(sid))
        normal_price = panel_price * normal_margin
        vip_price = panel_price * vip_margin
        service_name = html.escape(str(s_info[0]))
        blocks.append(
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{sid}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {service_name}\n"
            f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{panel_price:.2f}\n"
            f"👤 <b>ɴᴏʀᴍᴀʟ ᴍᴀʀɢɪɴ »</b> ×{normal_margin:.2f}\n"
            f"💰 <b>ɴᴏʀᴍᴀʟ ᴘʀɪᴄᴇ »</b> ₹{normal_price:.2f}\n"
            f"👑 <b>ᴠɪᴘ ᴍᴀʀɢɪɴ »</b> ×{vip_margin:.2f}\n"
            f"💎 <b>ᴠɪᴘ ᴘʀɪᴄᴇ »</b> ₹{vip_price:.2f}\n"
        )

    if not blocks:
        bot.send_message(ADMIN_ID, "❌ <b>ᴠᴀʟɪᴅ ᴀᴄᴛɪᴠᴇ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ᴍɪʟɪ.</b>", parse_mode="HTML")
        return

    current = "💹 <b>ꜱᴇʀᴠɪᴄᴇ ᴘʀɪᴄᴇꜱ</b>\n\n"
    for block in blocks:
        addition = block + "\n"
        if len(current) + len(addition) > 3900:
            bot.send_message(ADMIN_ID, current, parse_mode="HTML")
            current = "💹 <b>ꜱᴇʀᴠɪᴄᴇ ᴘʀɪᴄᴇꜱ</b>\n\n" + addition
        else:
            current += addition
    if current.strip():
        bot.send_message(ADMIN_ID, current, parse_mode="HTML")

    if missing:
        bot.send_message(
            ADMIN_ID,
            "⚠️ <b>ɴᴏᴛ ꜰᴏᴜɴᴅ / ᴅɪꜱᴀʙʟᴇᴅ ɪᴅꜱ:</b>\n<code>" + html.escape(" ".join(missing[:100])) + "</code>",
            parse_mode="HTML"
        )


def show_panel_prices():
    all_services = get_all_panel_services()
    bot_ids = set(get_bot_service_ids())
    lines = []

    for s in all_services:
        sid = str(s.get("service"))
        if sid not in bot_ids:
            continue

        rate = float(s.get("rate", 0))
        multi = get_service_multiplier(sid)
        selling = rate * multi
        vip_selling = rate * get_vip_margin(sid)
        s_info = find_service(sid)
        service_name = html.escape(s_info[0]) if s_info else "ᴜɴᴋɴᴏᴡɴ ꜱᴇʀᴠɪᴄᴇ"

        lines.append(
            f"🆔 <code>{sid}</code>: <b>{service_name}</b>\n"
            f"📊<b>ᴘᴀɴᴇʟ :</b> ₹{rate:.2f}\n"
            f"💎<b>ɴᴏʀᴍᴀʟ ᴘʀɪᴄᴇ :</b> ₹{selling:.2f}\n"
            f"👑<b>ᴠɪᴘ ᴘʀɪᴄᴇ :</b> ₹{vip_selling:.2f}\n\n"
        )

    if not lines:
        bot.send_message(ADMIN_ID, "❌ ᴘᴀɴᴇʟ ᴘʀɪᴄᴇꜱ ɴᴀʜɪ ᴍɪʟᴀ")
        return

    for i in range(0, len(lines), 24):
        msg = "📊<b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇꜱ</b>\n\n" + "".join(lines[i:i+50])
        if len(msg) > 3900:
            for j in range(i, min(i+24, len(lines)), 24):
                small_msg = "📊<b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇꜱ</b>\n\n" + "".join(lines[j:j+24])
                bot.send_message(ADMIN_ID, small_msg, parse_mode="HTML")
        else:
            bot.send_message(ADMIN_ID, msg, parse_mode="HTML")


# --- INFO CENTER TEXTS ---
HOW_TO_ORDER_TEXT = """📖 ʜᴏᴡ ᴛᴏ ᴏʀᴅᴇʀ

① ᴏᴘᴇɴ ꜱᴇʀᴠɪᴄᴇꜱ
ᴍᴀɪɴ ᴍᴇɴᴜ ꜱᴇ 📋 ꜱᴇʀᴠɪᴄᴇꜱ ᴘᴀʀ ᴄʟɪᴄᴋ ᴋᴀʀᴇɪɴ.

② ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇ
📋 ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇ ᴘᴀʀ ᴄʟɪᴄᴋ ᴋᴀʀᴇɪɴ.

③ ᴘʟᴀᴛꜰᴏʀᴍ ꜱᴇʟᴇᴄᴛ
ɪɴꜱᴛᴀɢʀᴀᴍ, ʏᴏᴜᴛᴜʙᴇ, ᴛᴇʟᴇɢʀᴀᴍ, ꜰᴀᴄᴇʙᴏᴏᴋ ᴇᴛᴄ. ᴍᴇɪɴ ꜱᴇ ᴘʟᴀᴛꜰᴏʀᴍ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴇɪɴ.

④ ᴄᴀᴛᴇɢᴏʀʏ ꜱᴇʟᴇᴄᴛ
ꜰᴏʟʟᴏᴡᴇʀꜱ, ʟɪᴋᴇꜱ, ᴠɪᴇᴡꜱ, ᴄᴏᴍᴍᴇɴᴛꜱ ᴊᴏ ᴄʜᴀʜɪʏᴇ ᴜꜱᴇ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴇɪɴ.

⑤ ꜱᴇʀᴠɪᴄᴇ ꜱᴇʟᴇᴄᴛ
ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ, ʀᴀᴛᴇ, ᴍɪɴ/ᴍᴀx, ʀᴇꜰɪʟʟ ᴀᴜʀ ꜱᴘᴇᴇᴅ ᴅᴇᴋʜ ᴋᴀʀ ꜱᴇʀᴠɪᴄᴇ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴇɪɴ.

⑥ ʟɪɴᴋ ᴅᴇɪɴ
ᴘᴏꜱᴛ/ʀᴇᴇʟ/ᴄʜᴀɴɴᴇʟ/ᴘʀᴏꜰɪʟᴇ ᴋᴀ ꜱᴀʜɪ ʟɪɴᴋ ᴅᴇɪɴ.

⑦ Qᴜᴀɴᴛɪᴛʏ ᴅᴇɪɴ
ꜱᴇʀᴠɪᴄᴇ ᴋɪ ᴍɪɴ/ᴍᴀx Qᴜᴀɴᴛɪᴛʏ ᴋᴇ ʜɪꜱᴀʙ ꜱᴇ Qᴜᴀɴᴛɪᴛʏ ᴇɴᴛᴇʀ ᴋᴀʀᴇɪɴ.

⑧ ᴄᴏɴꜰɪʀᴍ ᴏʀᴅᴇʀ
ʙᴏᴛ ᴀᴀᴘᴋᴏ ᴏʀᴅᴇʀ ᴅᴇᴛᴀɪʟꜱ ᴅɪᴋʜᴀʏᴇɢᴀ. ꜱᴀʙ ꜱᴀʜɪ ʜᴏ ᴛᴏ ✅ ᴄᴏɴꜰɪʀᴍ ᴋᴀʀᴇɪɴ. ɢᴀʟᴀᴛ ʜᴏ ᴛᴏ ❌ ᴄᴀɴᴄᴇʟ ᴋᴀʀᴇɪɴ.

⑨ ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ
ᴏʀᴅᴇʀ ɪᴅ ꜱᴇ 📊 ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ ᴍᴇɪɴ ꜱᴛᴀᴛᴜꜱ ᴄʜᴇᴄᴋ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ.

ɴᴏᴛᴇ:
ᴏʀᴅᴇʀ ᴋᴀʀɴᴇ ꜱᴇ ᴘᴇʜʟᴇ ʟɪɴᴋ, Qᴜᴀɴᴛɪᴛʏ ᴀᴜʀ ʙᴀʟᴀɴᴄᴇ ᴢᴀʀᴏᴏʀ ᴄʜᴇᴄᴋ ᴋᴀʀᴇɪɴ."""

ABOUT_BOT_TEXT = """ℹ️ ᴀʙᴏᴜᴛ ʙᴏᴛ

🤖 ʙᴏᴛ ɴᴀᴍᴇ : ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ

ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ ᴇᴋ ꜱᴍᴍ ʀᴇꜱᴇʟʟᴇʀ ʙᴏᴛ ʜᴀɪ ᴊᴀʜᴀɴ ᴜꜱᴇʀꜱ ᴡᴀʟʟᴇᴛ ʙᴀʟᴀɴᴄᴇ ꜱᴇ ꜱᴏᴄɪᴀʟ ᴍᴇᴅɪᴀ ꜱᴇʀᴠɪᴄᴇꜱ ᴏʀᴅᴇʀ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ.

ᴀᴠᴀɪʟᴀʙʟᴇ ꜰᴇᴀᴛᴜʀᴇꜱ:
📋 ꜱᴇʀᴠɪᴄᴇꜱ
💰 ᴡᴀʟʟᴇᴛ
➕ ᴀᴅᴅ ꜰᴜɴᴅ
📜 ꜰᴜɴᴅ ʜɪꜱᴛᴏʀʏ
📦 ᴍʏ ᴏʀᴅᴇʀꜱ
📊 ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ
🔄 ʀᴇꜰɪʟʟ ᴏʀᴅᴇʀ
❌ ᴄᴀɴᴄᴇʟ ᴏʀᴅᴇʀ
🎫 ᴛɪᴄᴋᴇᴛ ꜱᴜᴘᴘᴏʀᴛ

ᴘʟᴀᴛꜰᴏʀᴍꜱ:
ɪɴꜱᴛᴀɢʀᴀᴍ, ʏᴏᴜᴛᴜʙᴇ, ᴛᴇʟᴇɢʀᴀᴍ, ꜰᴀᴄᴇʙᴏᴏᴋ ᴀᴜʀ ᴏᴛʜᴇʀ ꜱᴇʀᴠɪᴄᴇꜱ.

ɴᴏᴛᴇ:
ʙᴏᴛ ᴍᴜʟᴛɪ-ᴠᴇɴᴅᴏʀ/ʀᴇꜱᴇʟʟᴇʀ ꜱʏꜱᴛᴇᴍ ᴘᴀʀ ʙᴀꜱᴇᴅ ʜᴀɪ. ꜱᴘᴇᴇᴅ, ʀᴇꜰɪʟʟ, ᴄᴀɴᴄᴇʟ ᴀᴜʀ ᴘᴀʀᴛɪᴀʟ ᴘʀᴏᴠɪᴅᴇʀ ᴋᴇ ʜɪꜱᴀʙ ꜱᴇ ᴅᴇᴘᴇɴᴅ ᴋᴀʀᴛᴀ ʜᴀɪ.

ᴀɴʏ ɪꜱꜱᴜᴇ?
🎫 ᴛɪᴄᴋᴇᴛ ᴄʀᴇᴀᴛᴇ ᴋᴀʀᴇɪɴ ʏᴀ ᴀᴅᴍɪɴ ꜱᴇ ᴄᴏɴᴛᴀᴄᴛ ᴋᴀʀᴇɪɴ."""

TERMS_GENERAL_TEXT = """📜 ɢᴇɴᴇʀᴀʟ ʀᴜʟᴇꜱ

ɪᴍᴘᴏʀᴛᴀɴᴛ ʀᴜʟᴇꜱ:

✅ ᴀᴘɴᴀ ᴀᴄᴄᴏᴜɴᴛ, ᴘᴏꜱᴛ, ʀᴇᴇʟ, ᴠɪᴅᴇᴏ ʏᴀ ᴄʜᴀɴɴᴇʟ ᴘᴜʙʟɪᴄ ʀᴀᴋʜᴇɪɴ.

✅ ꜰᴏʟʟᴏᴡᴇʀꜱ, ꜱᴜʙꜱᴄʀɪʙᴇʀꜱ, ʟɪᴋᴇꜱ, ᴄᴏᴍᴍᴇɴᴛꜱ, ᴠɪᴇᴡꜱ ᴀᴜʀ ᴄᴏᴜɴᴛᴇʀꜱ ʜɪᴅᴅᴇɴ ɴᴀʜɪɴ ʜᴏɴᴇ ᴄʜᴀʜɪʏᴇ.

✅ ᴘʀɪᴠᴀᴛᴇ/ʜɪᴅᴅᴇɴ/ᴅᴇʟᴇᴛᴇᴅ ᴘᴏꜱᴛ ʏᴀ ᴡʀᴏɴɢ ʟɪɴᴋ ᴘᴀʀ ᴏʀᴅᴇʀ ᴍᴀʀᴋᴇᴅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ ᴀᴜʀ ʀᴇꜰᴜɴᴅ ɴᴀʜɪɴ ᴍɪʟᴇɢᴀ.

✅ ᴇᴋ ʜɪ ʟɪɴᴋ ᴘᴀʀ ᴇᴋ ꜱᴀᴍᴀʏ ᴍᴇɪɴ ᴅᴏ ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇ ɴᴀ ᴋᴀʀᴇɪɴ.

✅ ᴘᴏʀɴᴏɢʀᴀᴘʜʏ, ᴘᴏʟɪᴛɪᴄꜱ, ᴇxᴛʀᴇᴍɪꜱᴍ, ʜᴀᴛᴇ, ꜰʀᴀᴜᴅ ʏᴀ ᴘᴜʙʟɪᴄ ᴏᴘɪɴɪᴏɴ ʙʜᴀᴅᴋᴀɴᴇ ᴡᴀʟᴇ ᴄᴏɴᴛᴇɴᴛ ᴘᴀʀ ᴏʀᴅᴇʀ ɴᴀ ᴋᴀʀᴇɪɴ.

✅ ꜰᴜɴᴅ ᴀᴅᴅ ʜᴏɴᴇ ᴋᴇ ʙᴀᴀᴅ ʙᴀɴᴋ ʀᴇꜰᴜɴᴅ ɴᴀʜɪɴ ʜᴏɢᴀ. ꜰᴜɴᴅ ʙᴏᴛ ᴡᴀʟʟᴇᴛ ᴍᴇɪɴ ꜱᴇʀᴠɪᴄᴇ ᴜꜱᴇ ᴋᴇ ʟɪʏᴇ ʀᴀʜᴇɢᴀ.

✅ ꜰʀᴀᴜᴅ, ꜰᴜɴᴅ ᴍᴀɴɪᴘᴜʟᴀᴛɪᴏɴ, ᴀʙᴜꜱᴇ, ꜱᴘᴀᴍ, ᴛʜʀᴇᴀᴛ ʏᴀ ꜱᴜᴘᴘᴏʀᴛ ᴛᴇᴀᴍ ꜱᴇ ᴍɪꜱʙᴇʜᴀᴠɪᴏʀ ᴘᴀʀ ᴀᴄᴄᴏᴜɴᴛ ꜱᴜꜱᴘᴇɴᴅ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ.

✅ ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇ ᴋᴀʀɴᴇ ᴋᴇ ʙᴀᴀᴅ ᴀᴄᴄᴏᴜɴᴛ ᴘʀɪᴠᴀᴛᴇ ɴᴀ ᴋᴀʀᴇɪɴ."""

TERMS_REFILL_TEXT = """🔄 ʀᴇꜰɪʟʟ ᴘᴏʟɪᴄʏ

ʀᴇꜰɪʟʟ ꜱɪʀꜰ ᴜɴ ꜱᴇʀᴠɪᴄᴇꜱ ᴘᴀʀ ᴍɪʟᴇɢᴀ ᴊɪɴᴍᴇɪɴ ʀᴇꜰɪʟʟ ᴀᴠᴀɪʟᴀʙʟᴇ ʜᴏ. ɴᴏ ʀᴇꜰɪʟʟ ꜱᴇʀᴠɪᴄᴇ ᴘᴀʀ ᴋɪꜱɪ ʙʜɪ ᴄᴀꜱᴇ ᴍᴇɪɴ ʀᴇꜰɪʟʟ ɴᴀʜɪɴ ᴅɪʏᴀ ᴊᴀʏᴇɢᴀ.

ɴᴏ ʀᴇꜰɪʟʟ ᴄᴀꜱᴇꜱ:

❌ ᴜꜱᴇʀɴᴀᴍᴇ ᴄʜᴀɴɢᴇ ᴋᴀʀɴᴇ ᴘᴀʀ ʀᴇꜰɪʟʟ ɴᴀʜɪɴ.
❌ ᴀᴄᴄᴏᴜɴᴛ ᴘʀɪᴠᴀᴛᴇ ᴋᴀʀɴᴇ ᴘᴀʀ ʀᴇꜰɪʟʟ ɴᴀʜɪɴ.
❌ ʟɪɴᴋ ᴅᴇʟᴇᴛᴇ/ʙʀᴏᴋᴇɴ/ɴᴏᴛ ᴡᴏʀᴋɪɴɢ ʜᴏɴᴇ ᴘᴀʀ ʀᴇꜰɪʟʟ ɴᴀʜɪɴ.
❌ ᴘʀᴏꜰɪʟᴇ ꜰʟᴀɢɢᴇᴅ ꜰᴏʀ ʀᴇᴠɪᴇᴡ ʜᴏ ʏᴀ ᴘᴏꜱᴛꜱ ɴᴀ ʜᴏɴ ᴛᴏ ʀᴇꜰɪʟʟ ɴᴀʜɪɴ.
❌ ᴅʀᴏᴘ 10% ꜱᴇ ᴋᴀᴍ ʜᴏɴᴇ ᴘᴀʀ ʀᴇꜰɪʟʟ ʀᴇᴊᴇᴄᴛ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ.
❌ ᴏᴛʜᴇʀ ᴘʀᴏᴠɪᴅᴇʀ/ᴘᴀɴᴇʟ ꜱᴇ ꜰᴏʟʟᴏᴡᴇʀꜱ ᴍɪx ʜᴏɴᴇ ᴘᴀʀ ʀᴇꜰɪʟʟ ɢᴜᴀʀᴀɴᴛᴇᴇ ɴᴀʜɪɴ.

ʀᴇꜰɪʟʟ ᴄᴀʟᴄᴜʟᴀᴛɪᴏɴ:
ꜱᴛᴀʀᴛ ᴄᴏᴜɴᴛ + ᴏʀᴅᴇʀ Qᴜᴀɴᴛɪᴛʏ = ᴇɴᴅ ᴄᴏᴜɴᴛ

ᴇxᴀᴍᴘʟᴇ:
ꜱᴛᴀʀᴛ ᴄᴏᴜɴᴛ 1000 ʜᴀɪ ᴀᴜʀ ᴀᴀᴘɴᴇ 1000 ꜰᴏʟʟᴏᴡᴇʀꜱ ᴏʀᴅᴇʀ ᴋɪʏᴀ. ᴇxᴘᴇᴄᴛᴇᴅ ᴇɴᴅ ᴄᴏᴜɴᴛ 2000 ʜᴏɢᴀ. ᴀɢᴀʀ ᴄᴏᴜɴᴛ 2000 ꜱᴇ ɴɪᴄʜᴇ ᴅʀᴏᴘ ʜᴏᴛᴀ ʜᴀɪ ᴀᴜʀ ᴏʀɪɢɪɴᴀʟ 1000 ꜱᴇ ᴜᴘᴀʀ ʜᴀɪ, ᴛᴏ ʀᴇꜰɪʟʟ ᴇʟɪɢɪʙɪʟɪᴛʏ ʜᴏ ꜱᴀᴋᴛɪ ʜᴀɪ.

✅ ʀᴇꜰɪʟʟ ᴏʀᴅᴇʀ ɪᴅ ᴋᴇ ʙᴀꜱɪꜱ ᴘᴀʀ ʜᴏᴛᴀ ʜᴀɪ, ʟɪɴᴋ ᴋᴇ ʙᴀꜱɪꜱ ᴘᴀʀ ɴᴀʜɪɴ.
✅ ʀᴇꜰɪʟʟ ʀᴇQᴜᴇꜱᴛ ᴋᴀʀᴛᴇ ꜱᴀᴍᴀʏ ᴏʀᴅᴇʀ ɪᴅ ᴢᴀʀᴏᴏʀ ʀᴀᴋʜᴇɪɴ.
✅ ᴘᴇʜʟᴇ ᴏʀᴅᴇʀ ᴋᴀ ʀᴇꜰɪʟʟ ᴄᴏᴍᴘʟᴇᴛᴇ/ᴘᴀʀᴛɪᴀʟ ʜᴏɴᴇ ꜱᴇ ᴘᴇʜʟᴇ ᴜꜱɪ ʟɪɴᴋ ᴘᴀʀ ɴᴀʏᴀ ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇ ɴᴀ ᴋᴀʀᴇɪɴ.
✅ ʀᴇꜰɪʟʟ ᴛɪᴍᴇ 24–72 ʜᴏᴜʀꜱ ʏᴀ ᴘʀᴏᴠɪᴅᴇʀ/ᴘʟᴀᴛꜰᴏʀᴍ ᴜᴘᴅᴀᴛᴇ ᴋᴇ ʜɪꜱᴀʙ ꜱᴇ ᴢʏᴀᴅᴀ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ.

ʟᴀʀɢᴇ ʙᴀꜱᴇ ᴀᴄᴄᴏᴜɴᴛꜱ:
100K–1M+ ʙᴀꜱᴇ ᴀᴄᴄᴏᴜɴᴛꜱ ᴘᴀʀ ᴀɢᴀʀ ᴏʀᴅᴇʀ ᴇxɪꜱᴛɪɴɢ ꜰᴏʟʟᴏᴡᴇʀꜱ ᴋᴀ 30% ꜱᴇ ᴋᴀᴍ ʜᴀɪ, ᴛᴏ ʀᴇꜰɪʟʟ/ᴘᴀʀᴛɪᴀʟ ɢᴜᴀʀᴀɴᴛᴇᴇ ɴᴀʜɪɴ.

100K ᴀᴄᴄᴏᴜɴᴛ → ᴍɪɴɪᴍᴜᴍ 30K ᴏʀᴅᴇʀ
500K ᴀᴄᴄᴏᴜɴᴛ → ᴍɪɴɪᴍᴜᴍ 150K ᴏʀᴅᴇʀ
1M ᴀᴄᴄᴏᴜɴᴛ → ᴍɪɴɪᴍᴜᴍ 300K ᴏʀᴅᴇʀ"""

TERMS_REFUND_TEXT = """💰 ʀᴇꜰᴜɴᴅ ᴘᴏʟɪᴄʏ

ʀᴇꜰᴜɴᴅ ꜱɪʀꜰ ʙᴏᴛ ᴡᴀʟʟᴇᴛ ᴍᴇɪɴ ᴅɪʏᴀ ᴊᴀʏᴇɢᴀ. ʙᴀɴᴋ/ᴜᴘɪ ʀᴇꜰᴜɴᴅ ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴀʜɪɴ ʜᴀɪ.

ᴄᴀɴᴄᴇʟᴇᴅ:
ᴀɢᴀʀ ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟᴇᴅ ʜᴏᴛᴀ ʜᴀɪ, ᴛᴏ ꜰᴜʟʟ ᴀᴍᴏᴜɴᴛ ᴀᴀᴘᴋᴇ ʙᴏᴛ ᴡᴀʟʟᴇᴛ ᴍᴇɪɴ ʀᴇꜰᴜɴᴅ ʜᴏɢᴀ.

ᴘᴀʀᴛɪᴀʟ:
ᴀɢᴀʀ ᴏʀᴅᴇʀ ᴘᴀʀᴛɪᴀʟ ʜᴏᴛᴀ ʜᴀɪ, ᴛᴏ ᴊɪᴛɴᴀ ᴘᴏʀᴛɪᴏɴ ᴅᴇʟɪᴠᴇʀ ɴᴀʜɪɴ ʜᴜᴀ ᴜꜱᴋᴀ ʀᴇꜰᴜɴᴅ ᴡᴀʟʟᴇᴛ ᴍᴇɪɴ ᴀᴀʏᴇɢᴀ.

ᴇxᴀᴍᴘʟᴇ:
ᴀᴀᴘɴᴇ 1000 Qᴜᴀɴᴛɪᴛʏ ᴏʀᴅᴇʀ ᴋɪʏᴀ ᴀᴜʀ 500 ᴅᴇʟɪᴠᴇʀ ʜᴜᴀ, ᴛᴏ ʙᴀᴄʜᴀ ʜᴜᴀ 50% ᴀᴍᴏᴜɴᴛ ᴡᴀʟʟᴇᴛ ᴍᴇɪɴ ʀᴇꜰᴜɴᴅ ʜᴏɢᴀ.

✅ ᴡʀᴏɴɢ ʏᴀ ɴᴏɴ-ᴡᴏʀᴋɪɴɢ ʟɪɴᴋ ᴘᴀʀ ᴏʀᴅᴇʀ ᴀᴜᴛᴏ ᴄᴀɴᴄᴇʟ ʜᴏɴᴇ ᴘᴀʀ ᴀᴍᴏᴜɴᴛ ᴡᴀʟʟᴇᴛ ᴍᴇɪɴ ᴀᴀ ꜱᴀᴋᴛᴀ ʜᴀɪ.
✅ ʀᴜɴɴɪɴɢ ᴏʀᴅᴇʀ ᴋᴀ ʀᴇꜰᴜɴᴅ ꜱᴇʀᴠɪᴄᴇ/ᴘʀᴏᴠɪᴅᴇʀ ᴘᴀʀ ᴅᴇᴘᴇɴᴅ ᴋᴀʀᴛᴀ ʜᴀɪ.
✅ ꜰᴀꜱᴛ-ᴡᴏʀᴋɪɴɢ ꜱᴇʀᴠɪᴄᴇꜱ ᴍᴇɪɴ ʀᴜɴɴɪɴɢ ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟ/ʀᴇꜰᴜɴᴅ ᴘᴏꜱꜱɪʙʟᴇ ɴᴀʜɪɴ ʜᴏ ꜱᴀᴋᴛᴀ.
✅ ᴏʀᴅᴇʀ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴍᴀʀᴋ ʜᴏɴᴇ ᴋᴇ ʙᴀᴀᴅ ᴀɢᴀʀ ɪꜱꜱᴜᴇ ʜᴀɪ ᴛᴏ 24 ʜᴏᴜʀꜱ ᴋᴇ ᴀɴᴅᴀʀ ʀᴇᴘᴏʀᴛ ᴋᴀʀᴇɪɴ.

❌ ꜱᴀᴍᴇ ʟɪɴᴋ ᴘᴀʀ ᴅᴜꜱʀᴇ ᴘᴀɴᴇʟ/ᴘʀᴏᴠɪᴅᴇʀ ꜱᴇ ᴏʀᴅᴇʀ ʟᴀɢᴀɴᴇ ᴘᴀʀ ʀᴇꜰᴜɴᴅ/ʀᴇꜰɪʟʟ ɢᴜᴀʀᴀɴᴛᴇᴇ ɴᴀʜɪɴ.
❌ ɴᴏ ʀᴇꜰɪʟʟ ꜱᴇʀᴠɪᴄᴇ ᴘᴀʀ ᴅᴇʟɪᴠᴇʀᴇᴅ, ᴘᴀʀᴛɪᴀʟ ʏᴀ ᴄᴏᴍᴘʟᴇᴛᴇ ᴄᴀꜱᴇ ᴍᴇɪɴ ʀᴇꜰɪʟʟ/ʀᴇꜰᴜɴᴅ ᴀʟʟᴏᴡᴇᴅ ɴᴀʜɪɴ.
❌ ᴜꜱᴇʀɴᴀᴍᴇ ꜱᴡɪᴛᴄʜɪɴɢ, ʟɪɴᴋ ᴛʀɪᴄᴋꜱ ʏᴀ ꜰᴀᴋᴇ ᴘʀᴏᴏꜰ ꜱᴇ ʀᴇꜰᴜɴᴅ/ʀᴇꜰɪʟʟ ᴄʟᴀɪᴍ ᴋᴀʀɴᴇ ᴘᴀʀ ᴀᴄᴄᴏᴜɴᴛ ʙᴀɴ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ.

ꜰᴜɴᴅ ᴘᴏʟɪᴄʏ:
ᴀᴅᴅᴇᴅ ꜰᴜɴᴅꜱ ʙᴏᴛ ᴡᴀʟʟᴇᴛ ᴍᴇɪɴ ʀᴀʜᴇɴɢᴇ. ᴡᴀʟʟᴇᴛ ʙᴀʟᴀɴᴄᴇ ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇꜱ ᴋᴇ ʟɪʏᴇ ᴜꜱᴇ ʜᴏɢᴀ. ʙᴀɴᴋ/ᴄᴀꜱʜ/ᴜᴘɪ ᴡɪᴛʜᴅʀᴀᴡᴀʟ ɴᴀʜɪɴ ʜᴏɢᴀ."""

TERMS_NOTES_TEXT = """ℹ️ ɪᴍᴘᴏʀᴛᴀɴᴛ ɴᴏᴛᴇꜱ & ᴀʙᴏᴜᴛ ʙᴏᴛ

ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ ᴇᴋ ᴍᴜʟᴛɪ-ᴠᴇɴᴅᴏʀ/ʀᴇꜱᴇʟʟᴇʀ ꜱʏꜱᴛᴇᴍ ʜᴀɪ. ʜᴜᴍ ᴅɪꜰꜰᴇʀᴇɴᴛ ᴘʀᴏᴠɪᴅᴇʀꜱ ᴋɪ ꜱᴇʀᴠɪᴄᴇꜱ ʙᴏᴛ ᴍᴇɪɴ ᴘʀᴏᴠɪᴅᴇ ᴋᴀʀᴛᴇ ʜᴀɪɴ.

ʜᴜᴍ ᴍᴇᴅɪᴀᴛᴏʀ/ʀᴇꜱᴇʟʟᴇʀ ᴋɪ ᴛᴀʀᴀʜ ᴄᴀᴍ ᴋᴀʀᴛᴇ ʜᴀɪɴ. ꜱᴘᴇᴇᴅ, ᴅʀᴏᴘ, ʀᴇꜰɪʟʟ, ᴄᴀɴᴄᴇʟ ᴀᴜʀ ᴘᴀʀᴛɪᴀʟ ᴘʀᴏᴠɪᴅᴇʀ ᴋᴇ ꜱʏꜱᴛᴇᴍ ᴘᴀʀ ᴅᴇᴘᴇɴᴅ ᴋᴀʀᴛᴀ ʜᴀɪ.

📌 ɪɴꜱᴛᴀɢʀᴀᴍ ʏᴀ ᴏᴛʜᴇʀ ᴘʟᴀᴛꜰᴏʀᴍ ᴋᴇ ꜱᴘᴀᴍ/ꜰᴀᴋᴇ ᴀᴄᴄᴏᴜɴᴛ ʀᴇᴍᴏᴠᴇ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ᴘᴀʀ ᴄʟɪᴄᴋ ɴᴀ ᴋᴀʀᴇɪɴ. ᴀɢᴀʀ ᴜꜱᴋɪ ᴡᴀᴊᴀʜ ꜱᴇ ᴅʀᴏᴘ ʜᴏᴛᴀ ʜᴀɪ ᴛᴏ ʀᴇꜰɪʟʟ ʀᴇꜱᴘᴏɴꜱɪʙɪʟɪᴛʏ ʜᴀᴍᴀʀɪ ɴᴀʜɪɴ ʜᴏɢɪ.

📌 ʀᴇꜰɪʟʟ ᴋᴇ ʟɪʏᴇ ᴏʀᴅᴇʀ ɪᴅ, ʟɪɴᴋ, ꜱᴛᴀʀᴛ ᴄᴏᴜɴᴛ ᴀᴜʀ ᴘʀᴏᴏꜰ ʀᴇᴀᴅʏ ʀᴀᴋʜᴇɪɴ.

📌 ʟɪᴠᴇ ᴠɪᴇᴡꜱ ʏᴀ ᴛɪᴍᴇ-ʙᴀꜱᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ ᴍᴇɪɴ ᴛɪᴍᴇ, ᴜꜱᴇʀɴᴀᴍᴇ ᴀᴜʀ ᴄᴏᴜɴᴛ ᴄʟᴇᴀʀ ᴅɪᴋʜᴛᴀ ʜᴜᴀ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ ʀᴀᴋʜᴇɪɴ.

📌 ꜰᴀᴋᴇ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ, ꜰᴀᴋᴇ ᴅᴏᴄᴜᴍᴇɴᴛ ʏᴀ ᴍᴀɴɪᴘᴜʟᴀᴛᴇᴅ ᴘʀᴏᴏꜰ ᴘᴀʀ ᴀᴄᴄᴏᴜɴᴛ ꜱᴜꜱᴘᴇɴᴅ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ.

📌 ᴘʀᴏᴠɪᴅᴇʀ ᴅᴇᴛᴀɪʟꜱ ꜱᴇᴄᴜʀɪᴛʏ ʀᴇᴀꜱᴏɴꜱ ꜱᴇ ꜱʜᴀʀᴇ ɴᴀʜɪɴ ᴋɪʏᴇ ᴊᴀᴛᴇ.

📌 ʜᴜᴍ ꜱᴏᴄɪᴀʟ ᴍᴇᴅɪᴀ ᴀᴄᴄᴏᴜɴᴛ ᴄʀᴇᴀᴛᴇ ʏᴀ ᴍᴀɴᴀɢᴇ ɴᴀʜɪɴ ᴋᴀʀᴛᴇ. ᴜꜱᴇʀ ᴀᴘɴᴇ ᴀᴄᴄᴏᴜɴᴛ, ᴄᴏɴᴛᴇɴᴛ ᴀᴜʀ ʟɪɴᴋ ᴋᴇ ʟɪʏᴇ ʀᴇꜱᴘᴏɴꜱɪʙʟᴇ ʜᴀɪ.

ʙᴇʜᴀᴠɪᴏʀ ᴘᴏʟɪᴄʏ:
ꜱᴜᴘᴘᴏʀᴛ ᴛᴇᴀᴍ/ᴀᴅᴍɪɴ ᴋᴇ ꜱᴀᴛʜ ᴀʙᴜꜱᴇ, ᴛʜʀᴇᴀᴛ, ᴍɪꜱʙᴇʜᴀᴠɪᴏʀ ʏᴀ ꜱᴘᴀᴍ ᴋᴀʀɴᴇ ᴘᴀʀ ᴀᴄᴄᴏᴜɴᴛ ᴘᴇʀᴍᴀɴᴇɴᴛ ꜱᴜꜱᴘᴇɴᴅ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ.

ᴘᴀʏᴍᴇɴᴛ ɪꜱꜱᴜᴇ:
ᴀɢᴀʀ ᴘᴀʏᴍᴇɴᴛ/ꜰᴜɴᴅ ᴀᴅᴅ ᴍᴇɪɴ ɪꜱꜱᴜᴇ ᴀᴀᴛᴀ ʜᴀɪ ᴛᴏ ᴘᴀɴɪᴄ ɴᴀ ᴋᴀʀᴇɪɴ. ᴀᴘɴᴀ ᴘʀᴏᴏꜰ, ᴀᴍᴏᴜɴᴛ, ᴅᴀᴛᴇ ᴀᴜʀ ᴛɪᴍᴇ ᴋᴇ ꜱᴀᴛʜ 🎫 ᴛɪᴄᴋᴇᴛ ᴄʀᴇᴀᴛᴇ ᴋᴀʀᴇɪɴ.

ꜰɪɴᴀʟ ɴᴏᴛᴇ:
ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ ᴛʀᴀɴꜱᴘᴀʀᴇɴᴛ ᴀᴜʀ ꜰᴀɪʀ ꜱᴇʀᴠɪᴄᴇ ᴅᴇɴᴇ ᴋɪ ᴋᴏꜱʜɪꜱʜ ᴋᴀʀᴛᴀ ʜᴀɪ. ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇ ᴋᴀʀɴᴇ ꜱᴇ ᴘᴇʜʟᴇ ʀᴜʟᴇꜱ ᴢᴀʀᴏᴏʀ ᴘᴀᴅʜᴇɪɴ."""

# --- KEYBOARDS ---
def main_menu_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    markup.add(
        types.KeyboardButton("📋 ꜱᴇʀᴠɪᴄᴇꜱ"),
        types.KeyboardButton("📦 ᴏʀᴅᴇʀꜱ")
    )
    markup.add(
        types.KeyboardButton("ᴘᴀʏᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ"),
        types.KeyboardButton("👤 ᴀᴄᴄᴏᴜɴᴛ")
    )

    # Settings single line
    markup.add(types.KeyboardButton("🎫 ᴛɪᴄᴋᴇᴛ & ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ"))

    # Admin panel only admin ke liye, settings ke niche
    if int(user_id) == ADMIN_ID:
        markup.add(types.KeyboardButton("⚙️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ"))

    return markup


def submenu_nav_keyboard(buttons, row_width=2):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=row_width)
    for i in range(0, len(buttons), row_width):
        markup.add(*[types.KeyboardButton(btn) for btn in buttons[i:i+row_width]])
    markup.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return markup


def services_menu_keyboard():
    return submenu_nav_keyboard([
        "📋 ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇ",
        "🔍 ꜱᴇᴀʀᴄʜ ꜱᴇʀᴠɪᴄᴇ",
        "📋 ꜱᴇʀᴠɪᴄᴇ ɪᴅ ʟɪꜱᴛ",
        "⭐ ꜰᴀᴠᴏᴜʀɪᴛᴇꜱ",
        "🕒 ʀᴇᴄᴇɴᴛ",
        "🔥 ᴛᴏᴘ",
        "📌 ᴘɪɴɴᴇᴅ",
    ], row_width=2)


def orders_menu_keyboard():
    return submenu_nav_keyboard([
        "📦 ᴍʏ ᴏʀᴅᴇʀꜱ",
        "📊 ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ",
        "❌ ᴄᴀɴᴄᴇʟ ᴏʀᴅᴇʀ",
        "🔄 ʀᴇꜰɪʟʟ ᴏʀᴅᴇʀ",
    ], row_width=2)


def wallet_menu_keyboard():
    return submenu_nav_keyboard([
        "💰 ᴡᴀʟʟᴇᴛ",
        "➕ ᴀᴅᴅ ꜰᴜɴᴅ",
        "📜 ꜰᴜɴᴅ ʜɪꜱᴛᴏʀʏ",
        "💳 ᴡᴀʟʟᴇᴛ ʜɪꜱᴛᴏʀʏ",
    ], row_width=2)


def account_menu_keyboard():
    return submenu_nav_keyboard([
        "👤 ᴘʀᴏꜰɪʟᴇ",
        "💎 ᴠɪᴘ ᴘʀᴏɢʀᴇꜱꜱ",
        "🏆 ᴀᴄʜɪᴇᴠᴇᴍᴇɴᴛꜱ",
        "📊 ᴍᴏɴᴛʜʟʏ ʀᴇᴘᴏʀᴛ",
        "🥇 ᴍʏ ʀᴀɴᴋ",
        "🎁 ʀᴇꜰᴇʀʀᴀʟ",
        "🎫 ᴀᴘᴘʟʏ ᴄᴏᴜᴘᴏɴ",
    ], row_width=2)


def settings_menu_keyboard():
    # Ticket button/function same rakha gaya hai. Sirf Bot Settings ki jagah Info Center add hai.
    return submenu_nav_keyboard([
        "🎫 ᴛɪᴄᴋᴇᴛ",
        "ℹ️ ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ",
    ], row_width=2)


def info_center_keyboard():
    return submenu_nav_keyboard([
        "📖 ʜᴏᴡ ᴛᴏ ᴏʀᴅᴇʀ",
        "📜 ᴛᴇʀᴍꜱ & ʀᴜʟᴇꜱ",
        "ℹ️ ᴀʙᴏᴜᴛ ʙᴏᴛ",
    ], row_width=2)


def terms_rules_keyboard():
    return submenu_nav_keyboard([
        "📜 ɢᴇɴᴇʀᴀʟ ʀᴜʟᴇꜱ",
        "🔄 ʀᴇꜰɪʟʟ ᴘᴏʟɪᴄʏ",
        "💰 ʀᴇꜰᴜɴᴅ ᴘᴏʟɪᴄʏ",
        "ℹ️ ɪᴍᴘᴏʀᴛᴀɴᴛ ɴᴏᴛᴇꜱ",
    ], row_width=2)


def show_info_center_menu(user_id):
    USER_NAV_STATE[user_id] = {"main_section": "settings", "mode": "info_center"}
    bot.send_message(
        user_id,
        "🟢 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ",
        reply_markup=info_center_keyboard()
    )


def show_terms_rules_menu(user_id):
    USER_NAV_STATE[user_id] = {"main_section": "settings", "mode": "terms_menu"}
    bot.send_message(
        user_id,
        "📜 ᴛᴇʀᴍꜱ & ʀᴜʟᴇꜱ\n\nʜᴇʟʟᴏ ᴅᴇᴀʀ ᴄᴜꜱᴛᴏᴍᴇʀꜱ,\n\nᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ.\n\nʏᴇ ʙᴏᴛ ᴀᴜᴛᴏᴍᴀᴛɪᴄ ꜱʏꜱᴛᴇᴍ ᴘᴀʀ ᴄᴀᴍ ᴋᴀʀᴛᴀ ʜᴀɪ. ᴋᴀʙʜɪ-ᴋᴀʙʜɪ ᴘᴀɴᴇʟ, ᴘʀᴏᴠɪᴅᴇʀ, ᴀᴘɪ ʏᴀ ꜱᴏᴄɪᴀʟ ᴘʟᴀᴛꜰᴏʀᴍ ᴜᴘᴅᴀᴛᴇꜱ ᴋɪ ᴡᴀᴊᴀʜ ꜱᴇ ꜱʏꜱᴛᴇᴍ ᴇʀʀᴏʀ, ᴅᴇʟᴀʏ, ᴘᴀʀᴛɪᴀʟ ʏᴀ ᴄᴀɴᴄᴇʟ ʜᴏ ꜱᴀᴋᴛᴀ ʜᴀɪ.\n\nʜᴜᴍ ᴀᴄᴄᴏᴜɴᴛ ᴄʀᴇᴀᴛᴇ ɴᴀʜɪɴ ᴋᴀʀᴛᴇ. ʏᴇ ʙᴏᴛ ꜱɪʀꜰ ꜱᴍᴍ ꜱᴇʀᴠɪᴄᴇꜱ ᴏʀᴅᴇʀ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.\n\nʙᴏᴛ ᴜꜱᴇ ᴋᴀʀɴᴇ, ᴀᴄᴄᴏᴜɴᴛ ꜱᴛᴀʀᴛ ᴋᴀʀɴᴇ ʏᴀ ɴᴇᴡ ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇ ᴋᴀʀɴᴇ ᴘᴀʀ ᴀᴀᴘ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʜᴀᴍᴀʀᴇ ᴛᴇʀᴍꜱ & ʀᴜʟᴇꜱ ᴀᴄᴄᴇᴘᴛ ᴋᴀʀᴛᴇ ʜᴀɪɴ.\n\n👇 ᴄʜᴏᴏꜱᴇ ᴀ ꜱᴇᴄᴛɪᴏɴ",
        reply_markup=terms_rules_keyboard()
    )


def send_info_text(user_id, text):
    bot.send_message(user_id, text, disable_web_page_preview=True)


def show_how_to_order(user_id):
    USER_NAV_STATE[user_id] = {"main_section": "settings", "mode": "info_center"}
    send_info_text(user_id, HOW_TO_ORDER_TEXT)


def show_about_bot(user_id):
    USER_NAV_STATE[user_id] = {"main_section": "settings", "mode": "info_center"}
    send_info_text(user_id, ABOUT_BOT_TEXT)


def show_terms_section(user_id, section_key):
    USER_NAV_STATE[user_id] = {"main_section": "settings", "mode": "terms_menu"}
    texts = {
        "general": TERMS_GENERAL_TEXT,
        "refill": TERMS_REFILL_TEXT,
        "refund": TERMS_REFUND_TEXT,
        "notes": TERMS_NOTES_TEXT,
    }
    send_info_text(user_id, texts.get(section_key, TERMS_GENERAL_TEXT))


def open_main_section(user_id, section):
    USER_NAV_STATE[user_id] = {"main_section": section}
    if section == "services":
        bot.send_message(user_id, "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ꜱᴇʀᴠɪᴄᴇꜱ</b>", parse_mode="HTML", reply_markup=services_menu_keyboard())
    elif section == "orders":
        bot.send_message(user_id, "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴏʀᴅᴇʀꜱ</b>", parse_mode="HTML", reply_markup=orders_menu_keyboard())
    elif section == "wallet":
        bot.send_message(user_id, "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴘᴀʏᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ</b>", parse_mode="HTML", reply_markup=wallet_menu_keyboard())
    elif section == "account":
        bot.send_message(user_id, "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴀᴄᴄᴏᴜɴᴛ</b>", parse_mode="HTML", reply_markup=account_menu_keyboard())
    elif section == "settings":
        bot.send_message(user_id, "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛɪᴄᴋᴇᴛ & ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ</b>", parse_mode="HTML", reply_markup=settings_menu_keyboard())

def admin_inline_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👥 ᴜꜱᴇʀ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ", callback_data="admin_cat_users"),
        types.InlineKeyboardButton("💰 ᴡᴀʟʟᴇᴛ & ꜰᴜɴᴅꜱ", callback_data="admin_cat_wallet"),
        types.InlineKeyboardButton("📦 ꜱᴇʀᴠɪᴄᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ", callback_data="admin_cat_services"),
        types.InlineKeyboardButton("📊 ᴘʀɪᴄᴇ & ᴍᴀʀɢɪɴ", callback_data="admin_cat_pricing"),
        types.InlineKeyboardButton("👑 ᴠɪᴘ & ᴄᴏᴜᴘᴏɴ", callback_data="admin_cat_vip"),
        types.InlineKeyboardButton("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ & ꜱʏꜱᴛᴇᴍ", callback_data="admin_cat_system"),
        types.InlineKeyboardButton("⚙️ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="admin_cat_bot_settings"),
        types.InlineKeyboardButton("🔗 ɪɴʟɪɴᴇ ᴍᴀᴋᴇʀ", callback_data="admin_inline_maker"),
    )
    return markup


# --- REPLY KEYBOARD NAVIGATION PATCH ---
ADMIN_TEXT_ACTIONS = {
    "👥 ᴜꜱᴇʀꜱ": "admin_users",
    "🔍 ꜱᴇᴀʀᴄʜ ᴜꜱᴇʀ": "admin_search_user",
    "🚫 ʙᴀɴ ᴜꜱᴇʀ": "admin_ban_user",
    "✅ ᴜɴʙᴀɴ ᴜꜱᴇʀ": "admin_unban_user",
    "📈 ᴛᴏᴘ ᴜꜱᴇʀꜱ": "admin_top_users",
    "📩 ᴍꜱɢ ᴜꜱᴇʀ": "admin_msg_user",
    "🎁 ᴍᴀꜱꜱ ᴀᴅᴅ": "admin_mass_add",
    "🗑️ ᴅᴇʟᴇᴛᴇ ᴜꜱᴇʀ": "admin_delete_user",
    "♻️ ʀᴇꜱᴛᴏʀᴇ ᴜꜱᴇʀ": "admin_restore_user",
    "📄 ᴇxᴘᴏʀᴛ ᴄꜱᴠ": "admin_export_csv",
    "⭐ ᴀᴅᴅ ᴠɪᴘ": "admin_add_vip",
    "❌ ʀᴇᴍᴏᴠᴇ ᴠɪᴘ": "admin_remove_vip",
    "📋 ʟɪꜱᴛ ᴄᴏᴜᴘᴏɴꜱ": "admin_list_coupons",
    "📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴍꜱɢ": "admin_broadcast",
    "📊 ᴘᴀɴᴇʟ ᴘʀɪᴄᴇꜱ": "admin_panel_prices",
    "💹 ꜱᴇʀᴠɪᴄᴇ ᴘʀɪᴄᴇꜱ": "admin_service_price_checker",
    "🎯 ᴄᴜꜱᴛᴏᴍ ᴍᴀʀɢɪɴ": "custom_margin",
    "👑 ᴠɪᴘ ᴍᴀʀɢɪɴ": "vip_margin",
    "👑 ᴠɪᴘ % ᴍᴀʀɢɪɴ": "vip_percent_margin",
    "📈 ᴘʀɪᴄᴇ ʜɪꜱᴛᴏʀʏ": "price_history",
    "🛠️ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ": "maintenance",
    "🔑 ᴀᴘɪ ꜱᴇᴛᴛɪɴɢꜱ": "admin_api_settings",
    "🌐 ᴄʜᴀɴɢᴇ ᴀᴘɪ ᴜʀʟ": "admin_change_api_url",
    "🔐 ᴄʜᴀɴɢᴇ ᴀᴘɪ ᴋᴇʏ": "admin_change_api_key",
    "🧪 ᴛᴇꜱᴛ ᴀᴘɪ": "admin_test_api",
    "📤 ꜱᴄʜᴇᴅᴜʟᴇᴅ ʙᴄ": "schedule_bc",
    "📁 ᴇxᴘᴏʀᴛ ᴏʀᴅᴇʀꜱ": "export_orders",
    "📁 ᴇxᴘᴏʀᴛ ꜰᴜɴᴅꜱ": "export_funds",
    "🏆 ᴛᴏᴘ ꜱᴇʀᴠɪᴄᴇꜱ": "top_services",
    "➕ ᴀᴅᴅ ʙᴀʟᴀɴᴄᴇ": "add_balance",
    "➖ ᴅᴇᴅᴜᴄᴛ ʙᴀʟᴀɴᴄᴇ": "deduct_balance",
    "🎁 ᴇxᴛʀᴀ ʙᴏɴᴜꜱ": "admin_extra_bonus",
    "➕ ᴀᴅᴅ ꜱᴇʀᴠɪᴄᴇ": "add_service",
    "📦 ʙᴀᴄᴋᴜᴘ ᴢɪᴘ": "admin_backup_zip",
    "🧹 ᴀᴜᴛᴏ ʜɪᴅᴇ": "admin_auto_hide_disabled",
    "🧾 ʀᴇᴘᴏʀᴛꜱ": "admin_reports",
    "ᴅᴜᴘʟɪᴄᴀᴛᴇ ꜱᴇʀᴠɪᴄᴇꜱ": "admin_duplicate_services",
    "🔁 ꜱᴇʀᴠɪᴄᴇ ꜱʜɪꜰᴛ": "admin_shift_service_category",
    "🗑️ ᴅᴇʟᴇᴛᴇ ꜱᴇʀᴠɪᴄᴇ": "admin_delete_service",
    "💳 ᴘᴀɴᴇʟ ʙᴀʟᴀɴᴄᴇ": "admin_panel_balance",
    "🧮 ʙᴜʟᴋ ᴍᴀʀɢɪɴ": "admin_bulk_margin",
    "🩺 ꜱᴇʀᴠɪᴄᴇ ʜᴇᴀʟᴛʜ": "admin_service_health",
    "📤 ᴇxᴘᴏʀᴛ ꜱᴇʀᴠɪᴄᴇꜱ": "admin_export_services",
    "📝 ᴀᴅᴍɪɴ ʟᴏɢꜱ": "admin_action_logs",
    "📝 ᴀᴄᴛɪᴠɪᴛʏ ʟᴏɢ": "admin_action_logs",
    "🧹 ᴄʟᴇᴀɴ ʟᴏɢꜱ": "admin_clean_logs",
    "🗂️ ᴇxᴄʜᴀɴɢᴇ ꜰɪʟᴇꜱ": "admin_exchange_files",
    "📦 ᴜᴘᴅᴀᴛᴇ ᴢɪᴘ": "admin_exchange_update_zip",
    "🐍 ᴜᴘᴅᴀᴛᴇ ʙᴏᴛ.ᴘʏ": "admin_exchange_update_botpy",
    "📄 ᴜᴘᴅᴀᴛᴇ ᴊꜱᴏɴ": "admin_exchange_update_json",
    "📌 ᴘɪɴ ꜱᴇʀᴠɪᴄᴇ": "admin_pin_service",
    "🗑️ ʀᴇᴍᴏᴠᴇ ᴘɪɴ": "admin_remove_pin_service",
    "📌 ᴘᴇɴᴅɪɴɢ ᴀᴄᴛɪᴏɴꜱ": "admin_pending_actions",
    "🧹 ᴄʟᴇᴀʀ ᴘᴇɴᴅɪɴɢ": "admin_clear_pending_actions",
    "📄 ʙᴀᴄᴋᴜᴘ ᴊꜱᴏɴ": "admin_backup_json_menu",
    "🐍 ʙᴀᴄᴋᴜᴘ ʙᴏᴛ.ᴘʏ": "admin_backup_botpy",
    "💾 ʙᴀᴄᴋᴜᴘ": "admin_backup_menu",
    "♻️ ʀᴇꜱᴛᴏʀᴇ ʟᴀꜱᴛ ʙᴀᴄᴋᴜᴘ": "admin_restore_last_backup",
    "❌ ᴅᴇʟᴇᴛᴇ ᴄᴏᴜᴘᴏɴ": "admin_delete_coupon",
    "🎲 ɢᴇɴᴇʀᴀᴛᴇ ᴄᴏᴜᴘᴏɴ": "admin_generate_coupon",
    "➕ ᴄʀᴇᴀᴛᴇ ᴄᴏᴜᴘᴏɴ": "admin_create_coupon",
    "🗑️ ʀᴇᴄᴇɴᴛʟʏ ʀᴇᴍᴏᴠᴇᴅ": "admin_recent_removed",
    "🤖 ꜱᴍᴀʀᴛ ᴀꜱꜱɪꜱᴛᴀɴᴛ": "admin_smart_assistant",
    "🔗 ɪɴʟɪɴᴇ ᴍᴀᴋᴇʀ": "admin_inline_maker",
}

ADMIN_CATEGORY_ACTIONS = {
    "👥 ᴜꜱᴇʀ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ": [
        ("👥 ᴜꜱᴇʀꜱ", "admin_users"),
        ("🔍 ꜱᴇᴀʀᴄʜ ᴜꜱᴇʀ", "admin_search_user"),
        ("🚫 ʙᴀɴ ᴜꜱᴇʀ", "admin_ban_user"),
        ("✅ ᴜɴʙᴀɴ ᴜꜱᴇʀ", "admin_unban_user"),
        ("📈 ᴛᴏᴘ ᴜꜱᴇʀꜱ", "admin_top_users"),
        ("📩 ᴍꜱɢ ᴜꜱᴇʀ", "admin_msg_user"),
        ("🎁 ᴍᴀꜱꜱ ᴀᴅᴅ", "admin_mass_add"),
        ("🗑️ ᴅᴇʟᴇᴛᴇ ᴜꜱᴇʀ", "admin_delete_user"),
        ("♻️ ʀᴇꜱᴛᴏʀᴇ ᴜꜱᴇʀ", "admin_restore_user"),
        ("📄 ᴇxᴘᴏʀᴛ ᴄꜱᴠ", "admin_export_csv"),
    ],
    "💰 ᴡᴀʟʟᴇᴛ & ꜰᴜɴᴅꜱ": [
        ("➕ ᴀᴅᴅ ʙᴀʟᴀɴᴄᴇ", "add_balance"),
        ("➖ ᴅᴇᴅᴜᴄᴛ ʙᴀʟᴀɴᴄᴇ", "deduct_balance"),
        ("🎁 ᴇxᴛʀᴀ ʙᴏɴᴜꜱ", "admin_extra_bonus"),
        ("📁 ᴇxᴘᴏʀᴛ ꜰᴜɴᴅꜱ", "export_funds"),
        ("💳 ᴘᴀɴᴇʟ ʙᴀʟᴀɴᴄᴇ", "admin_panel_balance"),
    ],
    "📦 ꜱᴇʀᴠɪᴄᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ": [
        ("➕ ᴀᴅᴅ ꜱᴇʀᴠɪᴄᴇ", "add_service"),
        ("🗑️ ᴅᴇʟᴇᴛᴇ ꜱᴇʀᴠɪᴄᴇ", "admin_delete_service"),
        ("🔁 ꜱᴇʀᴠɪᴄᴇ ꜱʜɪꜰᴛ", "admin_shift_service_category"),
        ("ᴅᴜᴘʟɪᴄᴀᴛᴇ ꜱᴇʀᴠɪᴄᴇꜱ", "admin_duplicate_services"),
        ("📌 ᴘɪɴ ꜱᴇʀᴠɪᴄᴇ", "admin_pin_service"),
        ("🗑️ ʀᴇᴍᴏᴠᴇ ᴘɪɴ", "admin_remove_pin_service"),
        ("🧹 ᴀᴜᴛᴏ ʜɪᴅᴇ", "admin_auto_hide_disabled"),
        ("🩺 ꜱᴇʀᴠɪᴄᴇ ʜᴇᴀʟᴛʜ", "admin_service_health"),
        ("📤 ᴇxᴘᴏʀᴛ ꜱᴇʀᴠɪᴄᴇꜱ", "admin_export_services"),
        ("🏆 ᴛᴏᴘ ꜱᴇʀᴠɪᴄᴇꜱ", "top_services"),
        ("🤖 ꜱᴍᴀʀᴛ ᴀꜱꜱɪꜱᴛᴀɴᴛ", "admin_smart_assistant"),
        ("📌 ᴘᴇɴᴅɪɴɢ ᴀᴄᴛɪᴏɴꜱ", "admin_pending_actions"),
        ("🧹 ᴄʟᴇᴀʀ ᴘᴇɴᴅɪɴɢ", "admin_clear_pending_actions"),
        ("🗑️ ʀᴇᴄᴇɴᴛʟʏ ʀᴇᴍᴏᴠᴇᴅ", "admin_recent_removed"),
    ],
    "📊 ᴘʀɪᴄᴇ & ᴍᴀʀɢɪɴ": [
        ("📊 ᴘᴀɴᴇʟ ᴘʀɪᴄᴇꜱ", "admin_panel_prices"),
        ("💹 ꜱᴇʀᴠɪᴄᴇ ᴘʀɪᴄᴇꜱ", "admin_service_price_checker"),
        ("🎯 ᴄᴜꜱᴛᴏᴍ ᴍᴀʀɢɪɴ", "custom_margin"),
        ("👑 ᴠɪᴘ ᴍᴀʀɢɪɴ", "vip_margin"),
        ("👑 ᴠɪᴘ % ᴍᴀʀɢɪɴ", "vip_percent_margin"),
        ("📈 ᴘʀɪᴄᴇ ʜɪꜱᴛᴏʀʏ", "price_history"),
        ("🧮 ʙᴜʟᴋ ᴍᴀʀɢɪɴ", "admin_bulk_margin"),
    ],
    "👑 ᴠɪᴘ & ᴄᴏᴜᴘᴏɴ": [
        ("⭐ ᴀᴅᴅ ᴠɪᴘ", "admin_add_vip"),
        ("❌ ʀᴇᴍᴏᴠᴇ ᴠɪᴘ", "admin_remove_vip"),
        ("➕ ᴄʀᴇᴀᴛᴇ ᴄᴏᴜᴘᴏɴ", "admin_create_coupon"),
        ("🎲 ɢᴇɴᴇʀᴀᴛᴇ ᴄᴏᴜᴘᴏɴ", "admin_generate_coupon"),
        ("📋 ʟɪꜱᴛ ᴄᴏᴜᴘᴏɴꜱ", "admin_list_coupons"),
        ("❌ ᴅᴇʟᴇᴛᴇ ᴄᴏᴜᴘᴏɴ", "admin_delete_coupon"),
    ],
    "📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ & ꜱʏꜱᴛᴇᴍ": [
        ("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴍꜱɢ", "admin_broadcast"),
        ("📤 ꜱᴄʜᴇᴅᴜʟᴇᴅ ʙᴄ", "schedule_bc"),
        ("🧾 ʀᴇᴘᴏʀᴛꜱ", "admin_reports"),
        ("📁 ᴇxᴘᴏʀᴛ ᴏʀᴅᴇʀꜱ", "export_orders"),
        ("📝 ᴀᴄᴛɪᴠɪᴛʏ ʟᴏɢ", "admin_action_logs"),
        ("🧹 ᴄʟᴇᴀɴ ʟᴏɢꜱ", "admin_clean_logs"),
    ],
    "⚙️ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ": [
        ("🔑 ᴀᴘɪ ꜱᴇᴛᴛɪɴɢꜱ", "admin_api_settings"),
        ("🗂️ ᴇxᴄʜᴀɴɢᴇ ꜰɪʟᴇꜱ", "admin_exchange_files"),
        ("💾 ʙᴀᴄᴋᴜᴘ", "admin_backup_menu"),
        ("🛠️ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ", "maintenance"),
    ],
}

ADMIN_CATEGORY_CALLBACKS = {
    "admin_cat_users": "👥 ᴜꜱᴇʀ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ",
    "admin_cat_wallet": "💰 ᴡᴀʟʟᴇᴛ & ꜰᴜɴᴅꜱ",
    "admin_cat_services": "📦 ꜱᴇʀᴠɪᴄᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ",
    "admin_cat_pricing": "📊 ᴘʀɪᴄᴇ & ᴍᴀʀɢɪɴ",
    "admin_cat_vip": "👑 ᴠɪᴘ & ᴄᴏᴜᴘᴏɴ",
    "admin_cat_system": "📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ & ꜱʏꜱᴛᴇᴍ",
    "admin_cat_bot_settings": "⚙️ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ",
}

PLATFORM_TEXT_MAP = {}
SUBCAT_TEXT_MAP = {}
USER_NAV_STATE = {}

IG_FOLLOWER_FILTER_TEXT = {
    "👥 ɴᴏʀᴍᴀʟ ꜰᴏʟʟᴏᴡᴇʀꜱ": "normal",
    "💧 ʟᴏᴡ ᴅʀᴏᴘ ꜰᴏʟʟᴏᴡᴇʀꜱ": "low_drop",
    "🇮🇳 ɪɴᴅɪᴀ ꜰᴏʟʟᴏᴡᴇʀꜱ": "india",
    "🛡️ ɴᴏɴ ᴅʀᴏᴘ ꜰᴏʟʟᴏᴡᴇʀꜱ": "non_drop",
}

# Extra keyboard buttons also stop old step-handlers.
MENU_BUTTONS.extend(
    ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ", "⬅️ ʙᴀᴄᴋ"]
    + list(ADMIN_CATEGORY_ACTIONS.keys())
    + list(ADMIN_TEXT_ACTIONS.keys())
    + list(IG_FOLLOWER_FILTER_TEXT.keys())
)


def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Admin Panel ke saare action buttons har row me exactly 2 rahenge.
    labels = list(ADMIN_CATEGORY_ACTIONS.keys()) + ["🔗 ɪɴʟɪɴᴇ ᴍᴀᴋᴇʀ"]
    for i in range(0, len(labels), 2):
        kb.add(*[types.KeyboardButton(x) for x in labels[i:i+2]])
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb


def admin_sub_keyboard(category):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    actions = ADMIN_CATEGORY_ACTIONS.get(category, [])
    for i in range(0, len(actions), 2):
        kb.add(*[types.KeyboardButton(label) for label, _ in actions[i:i+2]])
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb


def admin_sub_inline_keyboard(category):
    markup = types.InlineKeyboardMarkup(row_width=2)
    actions = ADMIN_CATEGORY_ACTIONS.get(category, [])
    for i in range(0, len(actions), 2):
        markup.add(*[
            types.InlineKeyboardButton(label, callback_data=cb)
            for label, cb in actions[i:i+2]
        ])
    markup.add(types.InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin_panel_home"))
    return markup



def admin_category_welcome_title(category):
    try:
        return category.split(" ", 1)[1]
    except Exception:
        return category

# ✅ Admin Add/Shift flows now use Reply Keyboard (not inline buttons)
def _admin_flow_keyboard(labels, row_width=2, back_admin=True):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=row_width)
    for i in range(0, len(labels), row_width):
        kb.add(*[types.KeyboardButton(str(x)) for x in labels[i:i+row_width]])
    if back_admin:
        kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb

def _platform_label(platform_key):
    cfg = ADD_SERVICE_CATS.get(platform_key, {})
    return f"{cfg.get('icon', '📦')} {cfg.get('title', platform_key)}"

def _platform_from_label(label):
    label = str(label).strip()
    for key in ADD_SERVICE_CATS:
        if label == _platform_label(key):
            return key
    return None

def _subcat_from_label(platform, label):
    label = str(label).strip()
    for key, title in ADD_SERVICE_CATS.get(platform, {}).get("subs", {}).items():
        if label == str(title):
            return key
    return None

def _admin_platform_keyboard():
    return _admin_flow_keyboard([_platform_label(k) for k in ADD_SERVICE_CATS.keys()], row_width=2)

def _admin_subcat_keyboard(platform):
    return _admin_flow_keyboard(list(ADD_SERVICE_CATS.get(platform, {}).get("subs", {}).values()), row_width=2)

def _admin_ig_follow_keyboard():
    return _admin_flow_keyboard(list(IG_FOLLOWER_FILTER_TEXT.keys()), row_width=2)




try:
    MENU_BUTTONS.extend([_platform_label(k) for k in ADD_SERVICE_CATS.keys()])
    for _cfg in ADD_SERVICE_CATS.values():
        MENU_BUTTONS.extend([str(x) for x in _cfg.get("subs", {}).values()])
except Exception:
    pass




# --- API SETTINGS FEATURE ---
API_SETTINGS_LABEL = "🔑 ᴀᴘɪ ꜱᴇᴛᴛɪɴɢꜱ"
API_CHANGE_URL_LABEL = "🌐 ᴄʜᴀɴɢᴇ ᴀᴘɪ ᴜʀʟ"
API_CHANGE_KEY_LABEL = "🔐 ᴄʜᴀɴɢᴇ ᴀᴘɪ ᴋᴇʏ"
API_TEST_LABEL = "🧪 ᴛᴇꜱᴛ ᴀᴘɪ"

def api_settings_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(types.KeyboardButton(API_CHANGE_URL_LABEL), types.KeyboardButton(API_CHANGE_KEY_LABEL))
    kb.add(types.KeyboardButton(API_TEST_LABEL))
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb

def _masked_api_key(value):
    value = str(value or "")
    if len(value) <= 8:
        return "•" * len(value)
    return value[:4] + ("•" * max(4, len(value) - 8)) + value[-4:]

def show_api_settings_menu(chat_id=ADMIN_ID):
    USER_NAV_STATE[chat_id] = {"mode": "api_settings", "main_section": "admin", "admin_category": "⚙️ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ"}
    bot.send_message(
        chat_id,
        "🔑 <b>ᴀᴘɪ ꜱᴇᴛᴛɪɴɢꜱ</b>\n\n"
        f"🌐 <b>ᴀᴘɪ ᴜʀʟ :</b> <code>{html.escape(str(SMM_API_URL))}</code>\n"
        f"🔐 <b>ᴀᴘɪ ᴋᴇʏ :</b> <code>{html.escape(_masked_api_key(SMM_API_KEY))}</code>",
        parse_mode="HTML",
        reply_markup=api_settings_keyboard()
    )

def start_change_api_url():
    admin_state[ADMIN_ID] = {"api_setting_step": "url"}
    msg = bot.send_message(ADMIN_ID, "🌐 <b>ɴᴇᴡ ᴀᴘɪ ᴜʀʟ ꜱᴇɴᴅ ᴋᴀʀᴏ</b>\n\n<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>https://example.com/api/v2</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_change_api_url)

def process_change_api_url(message):
    global SMM_API_URL
    if message.chat.id != ADMIN_ID:
        return
    value = str(message.text or "").strip()
    if value in ["⬅️ ʙᴀᴄᴋ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
        admin_state.pop(ADMIN_ID, None)
        show_api_settings_menu()
        return
    if not (value.startswith("http://") or value.startswith("https://")):
        msg = bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴜʀʟ. http:// ʏᴀ https:// ꜱᴇ ꜱᴛᴀʀᴛ ʜᴏɴᴀ ᴄʜᴀʜɪʏᴇ.</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_change_api_url)
        return
    settings = load_json(SETTINGS_FILE)
    if not isinstance(settings, dict):
        settings = {}
    settings["smm_api_url"] = value
    save_json(SETTINGS_FILE, settings)
    SMM_API_URL = value
    _clear_panel_cache()
    admin_state.pop(ADMIN_ID, None)
    bot.send_message(ADMIN_ID, f"✅ <b>ᴀᴘɪ ᴜʀʟ ᴜᴘᴅᴀᴛᴇᴅ</b>\n\n<code>{html.escape(value)}</code>", parse_mode="HTML", reply_markup=api_settings_keyboard())

def start_change_api_key():
    admin_state[ADMIN_ID] = {"api_setting_step": "key"}
    msg = bot.send_message(ADMIN_ID, "🔐 <b>ɴᴇᴡ ᴀᴘɪ ᴋᴇʏ ꜱᴇɴᴅ ᴋᴀʀᴏ</b>\n\n⚠️ <b>ᴋᴇʏ ᴄʜᴀᴛ ᴍᴇ ᴅɪᴋʜᴇɢɪ, ꜱᴇɴᴅ ᴋᴀʀɴᴇ ᴋᴇ ʙᴀᴀᴅ ᴍᴇꜱꜱᴀɢᴇ ᴅᴇʟᴇᴛᴇ ᴋᴀʀ ᴅᴇɴᴀ.</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_change_api_key)

def process_change_api_key(message):
    global SMM_API_KEY
    if message.chat.id != ADMIN_ID:
        return
    value = str(message.text or "").strip()
    if value in ["⬅️ ʙᴀᴄᴋ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
        admin_state.pop(ADMIN_ID, None)
        show_api_settings_menu()
        return
    if len(value) < 5 or " " in value:
        msg = bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴘɪ ᴋᴇʏ. ᴅᴜʙᴀʀᴀ ꜱᴇɴᴅ ᴋᴀʀᴏ.</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_change_api_key)
        return
    settings = load_json(SETTINGS_FILE)
    if not isinstance(settings, dict):
        settings = {}
    settings["smm_api_key"] = value
    save_json(SETTINGS_FILE, settings)
    SMM_API_KEY = value
    _clear_panel_cache()
    admin_state.pop(ADMIN_ID, None)
    bot.send_message(ADMIN_ID, f"✅ <b>ᴀᴘɪ ᴋᴇʏ ᴜᴘᴅᴀᴛᴇᴅ</b>\n\n🔐 <code>{html.escape(_masked_api_key(value))}</code>", parse_mode="HTML", reply_markup=api_settings_keyboard())

def test_current_api():
    try:
        response = _api_post({"key": SMM_API_KEY, "action": "services"}, timeout=(4, 10))
        payload = response.json()
        if isinstance(payload, list):
            bot.send_message(ADMIN_ID, f"✅ <b>ᴀᴘɪ ᴄᴏɴɴᴇᴄᴛᴇᴅ</b>\n\n📦 <b>ꜱᴇʀᴠɪᴄᴇꜱ :</b> {len(payload)}", parse_mode="HTML", reply_markup=api_settings_keyboard())
        else:
            error = payload.get("error", str(payload)) if isinstance(payload, dict) else str(payload)
            bot.send_message(ADMIN_ID, f"❌ <b>ᴀᴘɪ ᴇʀʀᴏʀ</b>\n\n<code>{html.escape(str(error))}</code>", parse_mode="HTML", reply_markup=api_settings_keyboard())
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>ᴀᴘɪ ᴛᴇꜱᴛ ꜰᴀɪʟᴇᴅ</b>\n\n<code>{html.escape(str(e))}</code>", parse_mode="HTML", reply_markup=api_settings_keyboard())

try:
    MENU_BUTTONS.extend([API_SETTINGS_LABEL, API_CHANGE_URL_LABEL, API_CHANGE_KEY_LABEL, API_TEST_LABEL])
except Exception:
    pass

# --- EXCHANGE FILES FEATURE ---
EXCHANGE_MENU_LABEL = "🗂️ ᴇxᴄʜᴀɴɢᴇ ꜰɪʟᴇꜱ"
EXCHANGE_UPDATE_ZIP = "📦 ᴜᴘᴅᴀᴛᴇ ᴢɪᴘ"
EXCHANGE_UPDATE_BOT = "🐍 ᴜᴘᴅᴀᴛᴇ ʙᴏᴛ.ᴘʏ"
EXCHANGE_UPDATE_JSON = "📄 ᴜᴘᴅᴀᴛᴇ ᴊꜱᴏɴ"
EXCHANGE_CONFIRM = "✅ ᴄᴏɴꜰɪʀᴍ"
EXCHANGE_CANCEL = "❌ ᴄᴀɴᴄᴇʟ"

EXCHANGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".exchange_pending")
EXCHANGE_EXTRACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".exchange_extract")

def _restart_bot_after_exchange(delay=2):
    def _do_restart():
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception as e:
            try:
                bot.send_message(ADMIN_ID, f"❌ <b>ᴀᴜᴛᴏ ʀᴇꜱᴛᴀʀᴛ ᴇʀʀᴏʀ:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")
            except Exception:
                pass
    threading.Timer(delay, _do_restart).start()

def _base_dir():
    return os.path.dirname(os.path.abspath(__file__))

def _safe_basename(name):
    return os.path.basename(str(name or "").replace("\\", "/"))

def _json_files_list():
    try:
        files = [x for x in os.listdir(_base_dir()) if x.endswith(".json") and os.path.isfile(os.path.join(_base_dir(), x))]
        files.sort()
        return files
    except Exception:
        return [
            "users.json", "services.json", "added_services.json", "orders.json", "funds.json",
            "fund_requests.json", "funds_history.json", "wallet_history.json", "tickets.json",
            "coupons.json", "margins.json", "default_margins.json", "vip_margins.json",
            "favorites.json", "pinned_services.json", "recent_services.json", "known_services.json",
            "last_prices.json", "price_history.json", "settings.json", "scheduled_broadcasts.json",
            "admin_logs.json", "deleted_users.json"
        ]

def exchange_files_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(types.KeyboardButton(EXCHANGE_UPDATE_ZIP), types.KeyboardButton(EXCHANGE_UPDATE_BOT))
    kb.add(types.KeyboardButton(EXCHANGE_UPDATE_JSON))
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb

def exchange_json_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    files = _json_files_list()
    for i in range(0, len(files), 2):
        kb.add(*[types.KeyboardButton(x) for x in files[i:i+2]])
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb

def exchange_confirm_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(types.KeyboardButton(EXCHANGE_CONFIRM), types.KeyboardButton(EXCHANGE_CANCEL))
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb

def send_exchange_files_menu(chat_id=ADMIN_ID):
    admin_state[ADMIN_ID] = {"exchange_mode": "menu"}
    bot.send_message(
        chat_id,
        "🗂️ <b>ᴇxᴄʜᴀɴɢᴇ ꜰɪʟᴇꜱ</b>\n\n"
        "📦 <b>ᴜᴘᴅᴀᴛᴇ ᴢɪᴘ</b> » ᴘᴜʀᴀ ʙᴏᴛ.ᴘʏ + ᴊꜱᴏɴ ʀᴇᴘʟᴀᴄᴇ\n"
        "🐍 <b>ᴜᴘᴅᴀᴛᴇ ʙᴏᴛ.ᴘʏ</b> » ꜱɪʀꜰ ʙᴏᴛ.ᴘʏ ʀᴇᴘʟᴀᴄᴇ\n"
        "📄 <b>ᴜᴘᴅᴀᴛᴇ ᴊꜱᴏɴ</b> » ᴇᴋ ꜱᴘᴇᴄɪꜰɪᴄ ᴊꜱᴏɴ ʀᴇᴘʟᴀᴄᴇ",
        parse_mode="HTML",
        reply_markup=exchange_files_keyboard()
    )

def start_exchange_zip():
    os.makedirs(EXCHANGE_DIR, exist_ok=True)
    admin_state[ADMIN_ID] = {"exchange_mode": "await_zip"}
    bot.send_message(
        ADMIN_ID,
        "📦 <b>ᴜᴘᴅᴀᴛᴇ ᴢɪᴘ</b>\n\n📤 <b>ɴᴇᴡ ᴢɪᴘ ꜰɪʟᴇ ꜱᴇɴᴅ ᴋᴀʀᴏ.</b>",
        parse_mode="HTML",
        reply_markup=_admin_flow_keyboard([], row_width=2)
    )

def start_exchange_botpy():
    os.makedirs(EXCHANGE_DIR, exist_ok=True)
    admin_state[ADMIN_ID] = {"exchange_mode": "await_botpy"}
    bot.send_message(
        ADMIN_ID,
        "🐍 <b>ᴜᴘᴅᴀᴛᴇ ʙᴏᴛ.ᴘʏ</b>\n\n📤 <b>ɴᴇᴡ bot.py ꜰɪʟᴇ ꜱᴇɴᴅ ᴋᴀʀᴏ.</b>",
        parse_mode="HTML",
        reply_markup=_admin_flow_keyboard([], row_width=2)
    )

def start_exchange_json():
    admin_state[ADMIN_ID] = {"exchange_mode": "select_json"}
    bot.send_message(
        ADMIN_ID,
        "📄 <b>ᴜᴘᴅᴀᴛᴇ ᴊꜱᴏɴ</b>\n\n📌 <b>ᴊɪꜱ ᴊꜱᴏɴ ᴋᴏ ʀᴇᴘʟᴀᴄᴇ ᴋᴀʀɴᴀ ʜᴀɪ ᴜꜱᴇ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ.</b>",
        parse_mode="HTML",
        reply_markup=exchange_json_keyboard()
    )

def _download_admin_document(message, expected_name=None, allowed_ext=None):
    doc = message.document
    filename = _safe_basename(getattr(doc, "file_name", "") or "")
    if expected_name and filename != expected_name:
        raise ValueError(f"ᴘʟᴇᴀꜱᴇ ꜱᴇɴᴅ ᴇxᴀᴄᴛ ꜰɪʟᴇ: {expected_name}")
    if allowed_ext and not filename.lower().endswith(tuple(allowed_ext)):
        raise ValueError("ɪɴᴠᴀʟɪᴅ ꜰɪʟᴇ ᴛʏᴘᴇ")
    os.makedirs(EXCHANGE_DIR, exist_ok=True)
    file_info = bot.get_file(doc.file_id)
    downloaded = bot.download_file(file_info.file_path)
    pending_path = os.path.join(EXCHANGE_DIR, f"{int(time.time())}_{filename}")
    with open(pending_path, "wb") as f:
        f.write(downloaded)
    return filename, pending_path

def _validate_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        json.load(f)
    return True

def _validate_botpy(path):
    import py_compile
    py_compile.compile(path, doraise=True)
    return True

def _validate_zip_file(path):
    import zipfile
    with zipfile.ZipFile(path, "r") as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        base_names = [_safe_basename(n) for n in names]
        if "bot.py" not in base_names:
            raise ValueError("ZIP ᴍᴇ bot.py ɴᴀʜɪ ᴍɪʟᴀ")
        if not any(x.endswith(".json") for x in base_names):
            raise ValueError("ZIP ᴍᴇ ᴊꜱᴏɴ ꜰɪʟᴇꜱ ɴᴀʜɪ ᴍɪʟɪ")
    return True

def _prepare_pending_exchange(action, pending_path, original_filename, target_json=None):
    admin_state[ADMIN_ID] = {
        "exchange_mode": "confirm",
        "exchange_action": action,
        "pending_path": pending_path,
        "original_filename": original_filename,
        "target_json": target_json or ""
    }
    target_line = f"\n📄 <b>ᴛᴀʀɢᴇᴛ »</b> <code>{html.escape(str(target_json))}</code>" if target_json else ""
    bot.send_message(
        ADMIN_ID,
        "⚠️ <b>ᴛʜɪꜱ ꜰɪʟᴇ ᴡɪʟʟ ʙᴇ ʀᴇᴘʟᴀᴄᴇᴅ.</b>\n\n"
        f"📥 <b>ʀᴇᴄᴇɪᴠᴇᴅ »</b> <code>{html.escape(str(original_filename))}</code>"
        f"{target_line}\n\n"
        "✅ <b>ᴄᴏɴꜰɪʀᴍ</b> / ❌ <b>ᴄᴀɴᴄᴇʟ</b>",
        parse_mode="HTML",
        reply_markup=exchange_confirm_keyboard()
    )

def _copy_replace_file(src_path, dest_name):
    dest_name = _safe_basename(dest_name)
    dest_path = os.path.join(_base_dir(), dest_name)
    if os.path.exists(dest_path):
        os.remove(dest_path)
    shutil.copy2(src_path, dest_path)

def _apply_zip_exchange(zip_path):
    import zipfile
    base = _base_dir()
    if os.path.exists(EXCHANGE_EXTRACT_DIR):
        shutil.rmtree(EXCHANGE_EXTRACT_DIR, ignore_errors=True)
    os.makedirs(EXCHANGE_EXTRACT_DIR, exist_ok=True)

    extracted_files = []
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            if member.endswith("/"):
                continue
            bn = _safe_basename(member)
            if bn == "bot.py" or bn.endswith(".json"):
                target_tmp = os.path.join(EXCHANGE_EXTRACT_DIR, bn)
                with open(target_tmp, "wb") as f:
                    f.write(z.read(member))
                extracted_files.append(bn)

    if "bot.py" not in extracted_files:
        raise ValueError("ZIP ᴍᴇ bot.py ɴᴀʜɪ ᴍɪʟᴀ")
    if not any(x.endswith(".json") for x in extracted_files):
        raise ValueError("ZIP ᴍᴇ ᴊꜱᴏɴ ꜰɪʟᴇꜱ ɴᴀʜɪ ᴍɪʟɪ")

    for fn in os.listdir(base):
        if fn == "bot.py" or fn.endswith(".json"):
            fp = os.path.join(base, fn)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass

    for fn in extracted_files:
        shutil.copy2(os.path.join(EXCHANGE_EXTRACT_DIR, fn), os.path.join(base, fn))

def _apply_pending_exchange():
    st = admin_state.get(ADMIN_ID, {})
    action = st.get("exchange_action")
    pending = st.get("pending_path")
    if not pending or not os.path.exists(pending):
        raise ValueError("ᴘᴇɴᴅɪɴɢ ꜰɪʟᴇ ɴᴀʜɪ ᴍɪʟɪ")

    if action == "zip":
        _apply_zip_exchange(pending)
        return "📦 ᴢɪᴘ"
    if action == "botpy":
        _copy_replace_file(pending, "bot.py")
        return "🐍 bot.py"
    if action == "json":
        target = st.get("target_json")
        _copy_replace_file(pending, target)
        return f"📄 {target}"
    raise ValueError("ɪɴᴠᴀʟɪᴅ ᴇxᴄʜᴀɴɢᴇ ᴀᴄᴛɪᴏɴ")

def cancel_exchange_files():
    st = admin_state.get(ADMIN_ID, {})
    pending = st.get("pending_path")
    try:
        if pending and os.path.exists(pending):
            os.remove(pending)
    except Exception:
        pass
    admin_state.pop(ADMIN_ID, None)
    bot.send_message(ADMIN_ID, "❌ <b>ᴇxᴄʜᴀɴɢᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>", parse_mode="HTML", reply_markup=admin_keyboard())

try:
    MENU_BUTTONS.extend([
        EXCHANGE_MENU_LABEL, EXCHANGE_UPDATE_ZIP, EXCHANGE_UPDATE_BOT, EXCHANGE_UPDATE_JSON,
        EXCHANGE_CONFIRM, EXCHANGE_CANCEL
    ])
    MENU_BUTTONS.extend(_json_files_list())
except Exception:
    pass


def send_admin_panel_message(chat_id=ADMIN_ID):
    USER_NAV_STATE[chat_id] = {"mode": "admin_home", "main_section": "admin"}
    bot.send_message(
        chat_id,
        "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


def send_admin_category_message(chat_id, category):
    USER_NAV_STATE[chat_id] = {"mode": "admin_category", "main_section": "admin", "admin_category": category}
    bot.send_message(
        chat_id,
        f"🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ {admin_category_welcome_title(category)}</b>",
        parse_mode="HTML",
        reply_markup=admin_sub_keyboard(category)
    )

# --- ADMIN SPECIAL: INLINE MESSAGE MAKER ---
def _inline_maker_convert_quotes_to_code(text):
    """Double quotes ke andar jo bhi text ho, use Telegram <code> style me convert karta hai."""
    safe = html.escape(str(text or ""), quote=False)
    return re.sub(r'"([^"]+)"', r'<code>\1</code>', safe)


def _inline_maker_start(chat_id=ADMIN_ID):
    admin_state[ADMIN_ID] = {
        "inline_maker": True,
        "inline_step": "message",
        "inline_message_text": "",
        "inline_buttons": []
    }
    bot.send_message(
        chat_id,
        "<b>🔗 𝗜𝗡𝗟𝗜𝗡𝗘 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗠𝗔𝗞𝗘𝗥</b>\n\n"
        "<b>📩 ᴊᴏ ᴍᴇꜱꜱᴀɢᴇ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴ ᴋᴇ ꜱᴀᴛʜ ʙʜᴇᴊɴᴀ ʜᴀɪ, ᴡᴏ ᴀʙ ʙʜᴇᴊᴏ.</b>\n\n"
        "<b>ɴᴏᴛᴇ:</b> <code>\"RHN3GNCF\"</code> ᴊᴀɪꜱᴀ ᴛᴇxᴛ ᴀᴜᴛᴏ ᴄᴏᴅᴇ ꜱᴛʏʟᴇ ʙᴀɴᴇɢᴀ.",
        parse_mode="HTML",
        reply_markup=_admin_flow_keyboard([], row_width=2)
    )


def _inline_maker_handle_message(message):
    if message.chat.id != ADMIN_ID:
        return False
    st = admin_state.get(ADMIN_ID, {})
    if not st.get("inline_maker"):
        return False

    text = message.text or ""
    clean = text.strip()

    if clean in ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
        admin_state.pop(ADMIN_ID, None)
        USER_NAV_STATE.pop(ADMIN_ID, None)
        bot.send_message(ADMIN_ID, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(ADMIN_ID))
        return True
    if clean == "⬅️ ʙᴀᴄᴋ":
        admin_state.pop(ADMIN_ID, None)
        send_admin_panel_message(ADMIN_ID)
        return True

    step = st.get("inline_step")

    if step == "message":
        st["inline_message_text"] = text
        st["inline_step"] = "button_text"
        admin_state[ADMIN_ID] = st
        bot.send_message(
            ADMIN_ID,
            "<b>🔘 𝗦𝗘𝗡𝗗 𝗕𝗨𝗧𝗧𝗢𝗡 𝗧𝗘𝗫𝗧</b>\n\n"
            "<b>ᴊᴏ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴ ᴘᴀʀ ᴅɪᴋʜᴀɴᴀ ʜᴀɪ, ᴡᴏ ʙʜᴇᴊᴏ.</b>",
            parse_mode="HTML",
            reply_markup=_admin_flow_keyboard([], row_width=2)
        )
        return True

    if step == "button_text":
        if not clean:
            bot.send_message(ADMIN_ID, "<b>❌ ʙᴜᴛᴛᴏɴ ᴛᴇxᴛ ᴇᴍᴘᴛʏ ɴᴀʜɪ ʜᴏ ꜱᴀᴋᴛᴀ.</b>", parse_mode="HTML")
            return True
        st["current_button_text"] = clean
        st["inline_step"] = "button_link"
        admin_state[ADMIN_ID] = st
        bot.send_message(
            ADMIN_ID,
            "<b>🔗 𝗦𝗘𝗡𝗗 𝗕𝗨𝗧𝗧𝗢𝗡 𝗟𝗜𝗡𝗞</b>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> https://t.me/rehansmmbot",
            parse_mode="HTML",
            reply_markup=_admin_flow_keyboard([], row_width=2)
        )
        return True

    if step == "button_link":
        if not clean.startswith(("http://", "https://")):
            bot.send_message(ADMIN_ID, "<b>❌ ʟɪɴᴋ http:// ʏᴀ https:// ꜱᴇ ꜱᴛᴀʀᴛ ʜᴏɴᴀ ᴄʜᴀʜɪʏᴇ.</b>", parse_mode="HTML")
            return True
        st.setdefault("inline_buttons", []).append({
            "text": bold_unicode(st.get("current_button_text", "BUTTON")),
            "url": clean
        })
        st["inline_step"] = "more_button"
        admin_state[ADMIN_ID] = st
        bot.send_message(
            ADMIN_ID,
            "<b>✅ ʙᴜᴛᴛᴏɴ ᴀᴅᴅ ʜᴏ ɢᴀʏᴀ.</b>\n\n"
            "<b>➕ ᴀᴜʀ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴ ᴀᴅᴅ ᴋᴀʀɴᴀ ʜᴀɪ?</b>\n\n"
            "<b>yes / no</b>",
            parse_mode="HTML",
            reply_markup=_admin_flow_keyboard([], row_width=2)
        )
        return True

    if step == "more_button":
        if clean.lower() == "yes":
            st["inline_step"] = "button_text"
            admin_state[ADMIN_ID] = st
            bot.send_message(ADMIN_ID, "<b>🔘 𝗦𝗘𝗡𝗗 𝗡𝗘𝗫𝗧 𝗕𝗨𝗧𝗧𝗢𝗡 𝗧𝗘𝗫𝗧</b>", parse_mode="HTML", reply_markup=_admin_flow_keyboard([], row_width=2))
            return True

        if clean.lower() == "no":
            markup = types.InlineKeyboardMarkup(row_width=1)
            for btn in st.get("inline_buttons", []):
                markup.add(types.InlineKeyboardButton(btn["text"], url=btn["url"]))

            final_text = _inline_maker_convert_quotes_to_code(st.get("inline_message_text", ""))
            bot.send_message(
                ADMIN_ID,
                final_text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True
            )
            admin_state.pop(ADMIN_ID, None)
            bot.send_message(
                ADMIN_ID,
                "<b>✅ 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗖𝗥𝗘𝗔𝗧𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬</b>\n\n"
                "<b>📌 𝗦𝗘𝗟𝗘𝗖𝗧 𝗔𝗡 𝗢𝗣𝗧𝗜𝗢𝗡.</b>",
                parse_mode="HTML",
                reply_markup=admin_keyboard()
            )
            return True

        bot.send_message(ADMIN_ID, "<b>❌ ꜱɪʀꜰ yes ʏᴀ no ʟɪᴋʜᴏ.</b>", parse_mode="HTML")
        return True

    return False

def bold_unicode(text):
    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    bold = (
        "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭"
        "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"
        "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    )
    table = str.maketrans(normal, bold)
    return str(text).translate(table)

def run_callback_from_keyboard(message, callback_data):
    class FakeChat:
        pass
    class FakeMessage:
        pass
    class FakeCall:
        pass

    fake_msg = FakeMessage()
    fake_msg.chat = message.chat
    fake_msg.message_id = getattr(message, "message_id", 0)

    fake = FakeCall()
    fake.message = fake_msg
    fake.data = callback_data
    fake.id = "keyboard_action"

    original_answer = bot.answer_callback_query
    try:
        bot.answer_callback_query = lambda *args, **kwargs: None
        handle_callbacks(fake)
    finally:
        bot.answer_callback_query = original_answer


def platform_reply_keyboard():
    global PLATFORM_TEXT_MAP
    PLATFORM_TEXT_MAP = {}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    row = []
    for key, cfg in ADD_SERVICE_CATS.items():
        label = f"{cfg.get('icon', '📦')} {cfg['title']}"
        PLATFORM_TEXT_MAP[label] = key
        row.append(types.KeyboardButton(label))
        if len(row) == 3:
            kb.add(*row)
            row = []
    if row:
        kb.add(*row)
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb


def subcat_reply_keyboard(platform):
    global SUBCAT_TEXT_MAP
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    cfg = ADD_SERVICE_CATS.get(platform, {})
    subs = cfg.get("subs", {})
    all_services = get_all_bot_services_map()
    row = []
    for key, title in subs.items():
        has_service = any(item.get("subcat") == key for item in all_services.values())
        if not has_service:
            continue
        label = str(title)
        SUBCAT_TEXT_MAP[label] = key
        row.append(types.KeyboardButton(label))
        if len(row) == 3:
            kb.add(*row)
            row = []
    if row:
        kb.add(*row)
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb



def ig_follower_filter_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(types.KeyboardButton("👥 ɴᴏʀᴍᴀʟ ꜰᴏʟʟᴏᴡᴇʀꜱ"), types.KeyboardButton("💧 ʟᴏᴡ ᴅʀᴏᴘ ꜰᴏʟʟᴏᴡᴇʀꜱ"))
    kb.add(types.KeyboardButton("🇮🇳 ɪɴᴅɪᴀ ꜰᴏʟʟᴏᴡᴇʀꜱ"), types.KeyboardButton("🛡️ ɴᴏɴ ᴅʀᴏᴘ ꜰᴏʟʟᴏᴡᴇʀꜱ"))
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    return kb


def _match_ig_follower_filter(name, details, filter_key):
    text = (str(name or "") + " " + str(details or "")).lower()
    if filter_key == "low_drop":
        return "low drop" in text or "ʟᴏᴡ ᴅʀᴏᴘ" in text
    if filter_key == "india":
        return "india" in text or "indian" in text or "ɪɴᴅɪᴀ" in text or "🇮🇳" in text
    if filter_key == "non_drop":
        return "non drop" in text or "non-drop" in text or "ɴᴏɴ" in text
    # normal followers = followers without special low drop/india/non-drop tags
    return not _match_ig_follower_filter(name, details, "low_drop") and not _match_ig_follower_filter(name, details, "india") and not _match_ig_follower_filter(name, details, "non_drop")


# Generic ASCII -> mini/small-cap converter.
# Panel se aane wala koi bhi English text fixed word-list par depend nahi karega.
_MINI_ASCII_TABLE = str.maketrans({
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
    "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
    "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
    "s": "ꜱ", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
    "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ꜰ",
    "G": "ɢ", "H": "ʜ", "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ",
    "M": "ᴍ", "N": "ɴ", "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ",
    "S": "ꜱ", "T": "ᴛ", "U": "ᴜ", "V": "ᴠ", "W": "ᴡ", "X": "x",
    "Y": "ʏ", "Z": "ᴢ",
})


def to_mini_text(text):
    """Convert every ASCII English letter to mini font; keep digits/symbols unchanged."""
    return str(text or "").translate(_MINI_ASCII_TABLE)


def format_relay_text_html(text):
    """Mini-convert relayed user/admin text and render paired double-quoted text as Telegram code.

    Visible double quotes are preserved. Raw input is HTML-escaped, so user text cannot
    break parse_mode=HTML. Example: hello "ABC" -> ʜᴇʟʟᴏ "<code>ABC</code>".
    """
    raw = str(text or "")
    parts = raw.split('"')
    out = []
    for index, part in enumerate(parts):
        if index % 2 == 1 and index < len(parts) - 1:
            # Inside a complete pair of quotes: preserve exact text and show as mono/code.
            out.append('"<code>' + html.escape(part) + '</code>"')
        else:
            # Outside quotes (or after an unmatched quote): normal mini conversion.
            if index > 0 and index == len(parts) - 1 and len(parts) % 2 == 0:
                out.append('"')
            out.append(html.escape(to_mini_text(part)))
    return ''.join(out)


def mini_service_detail(text):
    # Convert before HTML escaping, otherwise &amp; jaise entities bhi alter ho sakti hain.
    return html.escape(to_mini_text(html.unescape(str(text or ""))))


def _clean_panel_text(text):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _mini_value(text):
    # Ab fixed words ki list nahi: panel ka jo bhi response aaye, sab ASCII letters mini banenge.
    value = str(text if text not in (None, "") else "ɴ/ᴀ").strip()
    return to_mini_text(value)


def _first_match(patterns, text, default="ɴ/ᴀ"):
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return default


def _normalized_bool(value, default="ɴᴏ"):
    raw = str(value or "").strip().lower()
    if raw in ("true", "1", "yes", "available", "enabled"):
        return "ʏᴇꜱ"
    if raw in ("false", "0", "no", "none", "null", "not available", "unavailable", "disabled"):
        return "ɴᴏ"
    return default


def _extract_labeled_value(text, label):
    """Read one label only; stop before next emoji/known label/sentence block."""
    stop_labels = r"refill|cancel|speedup|speed|start(?:\s*time)?|average(?:\s*time)?|avg(?:\s*time)?|min|max|supports?|notes?|quality|drop"
    pat = rf"\b{label}\b\s*[:\-]?\s*(.*?)(?=\s*(?:[♻️❌🚫🎥⚠️⚡🚀⏱️📉📈⭐💧📝]|\b(?:{stop_labels})\b\s*[:\-])|$)"
    m = re.search(pat, text, re.I | re.S)
    return m.group(1).strip(" |,;.-") if m else ""


def _split_extra_details(description):
    """Return clean separate detail lines without mixing main fields."""
    text = _clean_panel_text(description)
    if not text:
        return []

    # Put every emoji/known label and normal sentence on its own candidate line.
    text = re.sub(r"\s*(?=[♻️❌🚫🎥⚠️⚡🚀⏱️📉📈⭐💧📝])", "\n", text)
    text = re.sub(r"\s+(?=(?:refill|cancel|speedup|supports?|notes?)\s*[:\-])", "\n", text, flags=re.I)
    candidates = []
    for chunk in text.splitlines():
        chunk = chunk.strip(" |")
        if not chunk:
            continue
        # Main refill/cancel values already have their own dedicated rows.
        if re.match(r"^[♻️]?\s*refill\b", chunk, re.I):
            continue
        if re.match(r"^[❌]?\s*cancel\b", chunk, re.I):
            continue
        # Break long prose into readable one-information-per-line sentences.
        parts = re.split(r"(?<=[.!?])\s+", chunk)
        for part in parts:
            part = part.strip(" |")
            if part and part not in candidates:
                candidates.append(part)
    return candidates


def parse_panel_service_details(panel_item=None, fallback_detail=""):
    panel_item = panel_item or {}
    name_text = str(panel_item.get("name", "") or "")
    description = " | ".join(filter(None, [
        str(panel_item.get("description", "") or ""),
        str(panel_item.get("desc", "") or ""),
        str(fallback_detail or "")
    ]))
    api_refill_raw = str(panel_item.get("refill", "") or "").strip()
    api_cancel_raw = str(panel_item.get("cancel", "") or "").strip()

    # Some panels incorrectly return a whole combined report inside `refill`.
    # Keep it for parsing, but never print the entire report on the refill row.
    combined_report = " | ".join(filter(None, [description, api_refill_raw]))
    text = _clean_panel_text(" | ".join(filter(None, [name_text, combined_report])))
    low = text.lower()

    if re.search(r"high\s*quality|\bhq\b", low):
        quality = "ʜɪɢʜ ǫᴜᴀʟɪᴛʏ"
    elif "real" in low:
        quality = "ʀᴇᴀʟ"
    elif "premium" in low:
        quality = "ᴘʀᴇᴍɪᴜᴍ"
    else:
        quality = "ɴ/ᴀ"

    if re.search(r"non[\s-]*drop|no\s*drop|100%\s*stable", low):
        drop = "ɴᴏɴ-ᴅʀᴏᴘ"
    elif "low drop" in low:
        drop = "ʟᴏᴡ ᴅʀᴏᴘ"
    elif "high drop" in low:
        drop = "ʜɪɢʜ ᴅʀᴏᴘ"
    elif "stable" in low:
        drop = "ꜱᴛᴀʙʟᴇ"
    else:
        drop = "ɴ/ᴀ"

    refill_source = api_refill_raw
    # Only first refill value, stopping before Cancel/Speedup/Supports/Notes etc.
    labeled_refill = _extract_labeled_value(text, "refill")
    if labeled_refill:
        refill_source = labeled_refill
    else:
        refill_source = re.split(
            r"\s*(?:[❌🚫🎥⚠️]|\b(?:cancel|speedup|supports?|notes?)\b\s*[:\-])",
            refill_source, maxsplit=1, flags=re.I
        )[0].strip(" |,;.-")

    refill_low = refill_source.lower()
    if refill_low in ("false", "0", "no", "none", "null", "not available", "unavailable") or "no refill" in low:
        refill = "ɴᴏ"
    elif refill_low in ("true", "1", "yes", "available"):
        refill = "ʏᴇꜱ"
    elif refill_source:
        refill = _mini_value(refill_source)
    elif "lifetime refill" in low:
        refill = "ʟɪꜰᴇᴛɪᴍᴇ ʀᴇꜰɪʟʟ"
    else:
        refill = "ɴᴏ"

    # Prefer explicit Cancel label from report; otherwise use API boolean.
    cancel_source = _extract_labeled_value(text, "cancel")
    cancel_low = cancel_source.lower()
    if cancel_source:
        if re.search(r"\b(?:no|not available|unavailable|false|0)\b", cancel_low):
            cancel = "ɴᴏ"
        elif re.search(r"\b(?:yes|available|true|1)\b", cancel_low):
            cancel = "ʏᴇꜱ"
        else:
            cancel = _mini_value(cancel_source)
    else:
        cancel = _normalized_bool(api_cancel_raw, "ɴᴏ")

    if "instant" in low:
        start = "ɪɴꜱᴛᴀɴᴛ"
    else:
        start_raw = _first_match([
            r"start(?:\s*time)?\s*[:\-]?\s*([0-9]+\s*[-–]\s*[0-9]+\s*(?:min|minutes|hour|hours))",
            r"start\s*[:\-]?\s*([0-9]+\s*(?:min|minutes|hour|hours))",
            r"([0-9]+\s*[-–]\s*[0-9]+\s*(?:min|minutes|hour|hours))"
        ], text, "ɴ/ᴀ")
        start = _mini_value(start_raw)

    speed_raw = _first_match([
        r"speed\s*[:\-]?\s*([0-9]+\s*[kKmM]?\s*[-–]?\s*[0-9]*\s*[kKmM]?\+?\s*/\s*day)",
        r"([0-9]+\s*[kKmM]?\s*[-–]\s*[0-9]+\s*[kKmM]?\s*/\s*day)",
        r"([0-9]+\s*[kKmM]\+?\s*/\s*day)"
    ], text, "ɴ/ᴀ")
    speed = _mini_value(speed_raw)

    avg = str(panel_item.get("average_time") or panel_item.get("avg_time") or panel_item.get("average") or "").strip()
    avg_time = _mini_value(avg) if avg else "ɴ/ᴀ"

    min_qty = str(panel_item.get("min") or "").strip()
    max_qty = str(panel_item.get("max") or "").strip()
    if not min_qty:
        min_qty = _first_match([r"min\s*[:\-]?\s*([0-9]+[kKmM]?)"], text, "ɴ/ᴀ")
    if not max_qty:
        max_qty = _first_match([r"max\s*[:\-]?\s*([0-9]+[kKmM]?)"], text, "ɴ/ᴀ")

    # Extra report is shown separately, one fact per line, never inside refill/cancel.
    extra_source = " | ".join(filter(None, [description, api_refill_raw if len(api_refill_raw) > len(refill_source) else ""]))
    extras = _split_extra_details(extra_source)

    return {
        "quality": quality, "drop": drop, "refill": refill, "cancel": cancel,
        "start": start, "speed": speed, "avg_time": avg_time,
        "min": _mini_value(min_qty), "max": _mini_value(max_qty),
        "extras": extras
    }


def _fast_user_price(sid, user_id, panel_price, fallback_price=0):
    try:
        panel_price = float(panel_price or 0)
    except Exception:
        panel_price = 0
    if panel_price <= 0:
        return float(fallback_price or 0)
    if is_vip_user(user_id):
        return round(panel_price * get_vip_margin(sid), 4)
    return round(panel_price * get_margin(sid), 4)


def _panel_field_label(key):
    labels = {
        "name": "📋 ᴘᴀɴᴇʟ ᴅᴇᴛᴀɪʟ", "description": "📝 ᴅᴇꜱᴄʀɪᴘᴛɪᴏɴ", "desc": "📝 ᴅᴇꜱᴄʀɪᴘᴛɪᴏɴ",
        "type": "⚙️ ᴛʏᴘᴇ", "min": "📉 ᴍɪɴ", "max": "📈 ᴍᴀx", "refill": "♻️ ʀᴇꜰɪʟʟ",
        "cancel": "❌ ᴄᴀɴᴄᴇʟ", "average_time": "⏱️ ᴀᴠɢ ᴛɪᴍᴇ", "avg_time": "⏱️ ᴀᴠɢ ᴛɪᴍᴇ",
        "dripfeed": "💧 ᴅʀɪᴘꜰᴇᴇᴅ", "category": "📂 ᴄᴀᴛᴇɢᴏʀʏ",
    }
    return labels.get(str(key).lower(), mini_service_detail(str(key).replace("_", " ")))


def _clean_raw_panel_lines(value):
    text = _clean_panel_text(value)
    if not text:
        return []
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = text.replace(" | ", "\n").replace("\r", "\n")
    text = re.sub(r"\s*(?=[⏱🚀⭐💧♻❌🚫⚠📩🎥🔓🚦⛔👤📝📉📈⚡])", "\n", text)
    output = []
    for chunk in text.splitlines():
        chunk = re.sub(r"\s+", " ", chunk).strip(" |•▫️")
        visible = re.sub(r"[\ufe0f\u200d\s|•▫️]", "", chunk)
        if not chunk or len(visible) <= 1:
            continue
        for part in re.split(r"(?<=[.!?])\s+", chunk):
            part = part.strip(" |•▫️")
            visible_part = re.sub(r"[\ufe0f\u200d\s|•▫️]", "", part)
            if part and len(visible_part) > 1 and part not in output:
                output.append(part)
    return output


def get_panel_raw_detail_lines(panel_item=None, fallback_detail=""):
    panel_item = panel_item if isinstance(panel_item, dict) else {}
    result, seen = [], set()
    for key, value in panel_item.items():
        if str(key).lower() in {"service", "rate"} or value is None or value == "":
            continue
        key_low = str(key).lower()
        if isinstance(value, (dict, list)):
            try:
                value = json.dumps(value, ensure_ascii=False)
            except Exception:
                value = str(value)
        if key_low in {"name", "description", "desc"}:
            for raw in _clean_raw_panel_lines(str(value)):
                mini = mini_service_detail(raw)
                token = re.sub(r"\s+", " ", mini).strip().lower()
                if token and token not in seen:
                    result.append(f"▫️ {mini}")
                    seen.add(token)
        else:
            label = _panel_field_label(key)
            mini = mini_service_detail(str(value))
            token = f"{label}:{mini}".lower()
            if token not in seen:
                result.append(f"{label} : {mini}")
                seen.add(token)
    if fallback_detail:
        for raw in _clean_raw_panel_lines(fallback_detail):
            mini = mini_service_detail(raw)
            token = re.sub(r"\s+", " ", mini).strip().lower()
            if token and token not in seen:
                result.append(f"▫️ {mini}")
                seen.add(token)
    return result


def format_service_details_block(sid, name, price, panel_item=None, fallback_detail=""):
    block = (
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ :</b> <code>{sid}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ :</b> {html.escape(str(name))}\n"
        f"💰 <b>ᴘʀɪᴄᴇ :</b> ₹{float(price):.2f}/1000\n"
    )
    details = get_panel_raw_detail_lines(panel_item, fallback_detail)
    if details:
        block += "\n📝 <b>ᴘᴀɴᴇʟ ᴅᴇᴛᴀɪʟꜱ :</b>\n" + "\n".join(details)
    else:
        block += "\n📝 <b>ᴘᴀɴᴇʟ ᴅᴇᴛᴀɪʟꜱ :</b> ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ"
    return block

def show_services_for_subcat_keyboard(user_id, cat_key, ig_follow_filter=None):
    lines = []
    valid_ids = []

    # ✅ Panel API sirf 1 baar call hoga; saari service details/price isi map se niklenge.
    panel_services = get_all_panel_services()
    panel_map = {str(s.get("service")): s for s in panel_services if s.get("service") is not None}

    if cat_key in SERVICES:
        for s_id, s_info in SERVICES[cat_key].items():
            sid = str(s_id)
            panel_item = panel_map.get(sid, {})
            panel_price = panel_item.get("rate", 0)
            fallback_price = s_info[1] if isinstance(s_info, list) and len(s_info) > 1 else 0
            price = _fast_user_price(sid, user_id, panel_price, fallback_price)
            name = str(s_info[0]) if isinstance(s_info, list) else str(s_info)
            detail_text = panel_item.get("name", "") if isinstance(panel_item, dict) else ""
            if cat_key == "ig_followers" and ig_follow_filter and not _match_ig_follower_filter(name, detail_text, ig_follow_filter):
                continue
            valid_ids.append(sid)
            lines.append((sid, format_service_details_block(sid, name, price, panel_item, "")))

    added_db = load_json(ADDED_SERVICES_FILE)
    for s_id, item in added_db.items():
        item_subcat = item.get("subcat")
        if cat_key == "ig_followers":
            # New added Instagram followers can be placed directly into one of the
            # four follower types using ig_follow_type. Old entries still work by
            # matching the panel/name text.
            if item_subcat != "ig_followers" and not str(item_subcat).startswith("ig_followers_"):
                continue
            saved_follow_type = item.get("ig_follow_type", "")
            if not saved_follow_type and str(item_subcat).startswith("ig_followers_"):
                saved_follow_type = str(item_subcat).replace("ig_followers_", "", 1)
            if ig_follow_filter and saved_follow_type and saved_follow_type != ig_follow_filter:
                continue
        elif item_subcat != cat_key:
            continue
        sid = str(s_id)
        panel_item = panel_map.get(sid, {})
        panel_price = panel_item.get("rate", 0)
        fallback_price = float(item.get("price", 0))
        price = _fast_user_price(sid, user_id, panel_price, fallback_price)
        name = item.get("name", "Unknown")
        detail = item.get("panel_name", "")
        saved_follow_type = item.get("ig_follow_type", "")
        if cat_key == "ig_followers" and ig_follow_filter and not saved_follow_type:
            if not _match_ig_follower_filter(name, detail, ig_follow_filter):
                continue
        valid_ids.append(sid)
        lines.append((sid, format_service_details_block(sid, name, price, panel_item, detail)))

    if not lines:
        bot.send_message(user_id, "❌ <b>ɴᴏ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏᴜɴᴅ ɪɴ ᴛʜɪꜱ ᴄᴀᴛᴇɢᴏʀʏ</b>", parse_mode="HTML")
        return

    search_results[user_id] = valid_ids
    bot.send_message(user_id, "📦 <b>ꜱᴇʀᴠɪᴄᴇꜱ ʟɪꜱᴛ</b>", parse_mode="HTML")

    for sid, card in lines:
        chunks = []
        remaining = card
        while len(remaining) > 3800:
            cut = remaining.rfind("\n", 0, 3800)
            if cut < 500:
                cut = 3800
            chunks.append(remaining[:cut])
            remaining = remaining[cut:].lstrip("\n")
        if remaining:
            chunks.append(remaining)

        for index, chunk in enumerate(chunks):
            markup = None
            if index == len(chunks) - 1:
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(types.InlineKeyboardButton("🛒 ʙᴜʏ ɴᴏᴡ", callback_data=f"srv_{sid}"))
            bot.send_message(user_id, chunk, parse_mode="HTML", reply_markup=markup)

# --- END REPLY KEYBOARD NAVIGATION PATCH ---

def ensure_json_files():
    for filename in [
        DB_FILE, ORDERS_FILE, FUNDS_FILE, FUNDS_HISTORY_FILE,
        COUPON_FILE, LAST_PRICE_FILE, PRICE_HISTORY_FILE,
        WALLET_HISTORY_FILE, KNOWN_SERVICES_FILE, SETTINGS_FILE,
        SCHEDULED_FILE, MARGINS_FILE, ADDED_SERVICES_FILE, SERVICES_FILE, DEFAULT_MARGINS_FILE,
        ADMIN_LOG_FILE, PINNED_SERVICES_FILE, RECENT_SERVICES_FILE, FAVORITES_FILE, TICKETS_FILE, VIP_MARGINS_FILE, FUND_REQUESTS_FILE, PENDING_ACTIONS_FILE, REMOVED_SERVICES_FILE, ACHIEVEMENTS_FILE, SERVICE_NOTIFY_FILE, MONTHLY_REPORT_FILE
    ]:
        if not os.path.exists(filename):
            save_json(filename, {})

def show_user_service_id_list(user_id):
    services = []

    all_services = get_all_bot_services_map()

    for sid, item in all_services.items():
        services.append(
            f"🆔 <code>{sid}</code> » <b>{html.escape(item.get('name', 'Unknown'))}</b>"
        )

    chunk_size = 49

    for i in range(0, len(services), chunk_size):
        msg = "📋 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ ʟɪꜱᴛ</b>\n\n"
        msg += "\n".join(services[i:i + chunk_size])

        bot.send_message(
            user_id,
            msg,
            parse_mode="HTML"
        )


def platforms_keyboard():
    return platform_reply_keyboard()

def subcat_keyboard(platform):
    return subcat_reply_keyboard(platform)

def handle_menu_redirection(message):
    user_orders.pop(message.chat.id, None)
    handle_text(message)


# --- FORCE JOIN + ORDER LOG CHANNEL ---
def is_user_joined_order_channel(user_id):
    if int(user_id) == int(ADMIN_ID):
        return True
    try:
        member = bot.get_chat_member(ORDER_LOG_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print("Force join check error:", e)
        return False


def force_join_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ", url=ORDER_LOG_CHANNEL_LINK))
    kb.add(types.InlineKeyboardButton("✅ ꜱᴛᴀʀᴛ", callback_data="start_after_join"))
    return kb


def _force_join_text():
    return (
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>\n\n"
        "📢 <b>ᴘʜʟᴇ ʜᴀᴍᴀʀᴀ ᴏꜰꜰɪᴄɪᴀʟ ᴄʜᴀɴɴᴇʟ ᴊᴏɪɴ ᴋᴀʀᴏ.</b>\n\n"
        "✅ <b>ᴊᴏɪɴ ᴋᴀʀɴᴇ ᴋᴇ ʙᴀᴀᴅ ɴɪᴄʜᴇ ᴡᴀʟᴀ ꜱᴛᴀʀᴛ ʙᴜᴛᴛᴏɴ ᴅᴀʙᴀᴏ.</b>"
    )


def _save_force_join_msg_id(user_id, message_id):
    """Force-join ka sirf latest ek message id save rakho."""
    try:
        db = load_json(DB_FILE)
        uid = str(user_id)
        if uid in db:
            db[uid]["force_join_msg_id"] = message_id
            save_json(DB_FILE, db)
    except Exception as e:
        print("Save force join msg id error:", e)


def _get_force_join_msg_id(user_id):
    try:
        db = load_json(DB_FILE)
        return db.get(str(user_id), {}).get("force_join_msg_id")
    except Exception:
        return None


def _clear_force_join_msg_id(user_id):
    try:
        db = load_json(DB_FILE)
        uid = str(user_id)
        if uid in db and "force_join_msg_id" in db[uid]:
            db[uid].pop("force_join_msg_id", None)
            save_json(DB_FILE, db)
    except Exception as e:
        print("Clear force join msg id error:", e)


def _safe_delete_message(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
        return True
    except Exception:
        return False


def send_force_join_message(user_id, incoming_message=None):
    """
    Duplicate join message spam fix:
    - User baar-baar /start dabaye to purana join message edit/refresh hoga.
    - Agar edit me 'message is not modified' aaye to bhi success maana jayega.
    - Naya message bhejna pade to purana saved message pehle delete karne ki try hogi.
    - User ka /start command message bhi delete karne ki try hogi, chat clean rahega.
    """
    text = _force_join_text()
    old_msg_id = _get_force_join_msg_id(user_id)

    if incoming_message is not None:
        _safe_delete_message(user_id, incoming_message.message_id)

    if old_msg_id:
        try:
            bot.edit_message_text(
                text,
                chat_id=user_id,
                message_id=old_msg_id,
                parse_mode="HTML",
                reply_markup=force_join_keyboard()
            )
            return
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err or "message not modified" in err:
                return
            print("Edit force join message error:", e)
            _safe_delete_message(user_id, old_msg_id)
            _clear_force_join_msg_id(user_id)

    try:
        msg = bot.send_message(user_id, text, parse_mode="HTML", reply_markup=force_join_keyboard())
        _save_force_join_msg_id(user_id, msg.message_id)
    except Exception as e:
        print("Send force join message error:", e)


def welcome_text_main():
    return (
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>\n\n🎉 <b>ᴡᴇʟᴄᴏᴍᴇ!</b>\n\n<b>ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴄʜᴏᴏꜱɪɴɢ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ.</b>\n\n🚀 <b>ᴇɴᴊᴏʏ ᴘʀᴇᴍɪᴜᴍ ꜱᴍᴍ ꜱᴇʀᴠɪᴄᴇꜱ ᴡɪᴛʜ ꜰᴀꜱᴛ ᴅᴇʟɪᴠᴇʀʏ, ʜɪɢʜ Qᴜᴀʟɪᴛʏ ᴀɴᴅ ꜱᴇᴄᴜʀᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ.</b>\n\n✨ <b>ᴡʜᴀᴛ ᴡᴇ ᴏꜰꜰᴇʀ</b>\n\n💎 <b>ᴘʀᴇᴍɪᴜᴍ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n⚡ <b>ꜰᴀꜱᴛ & ᴀᴜᴛᴏᴍᴀᴛᴇᴅ ᴅᴇʟɪᴠᴇʀʏ</b>\n🛡️ <b>ꜱᴀꜰᴇ ᴀɴᴅ ᴛʀᴜꜱᴛᴇᴅ ᴏʀᴅᴇʀꜱ</b>\n💰 <b>ᴄᴏᴍᴘᴇᴛɪᴛɪᴠᴇ ᴘʀɪᴄᴇꜱ</b>\n🎫 <b>24×7 ꜱᴜᴘᴘᴏʀᴛ ᴠɪᴀ ᴛɪᴄᴋᴇᴛ</b>\n\n❤️ <b>ᴡᴇ ᴛʀᴜʟʏ ᴀᴘᴘʀᴇᴄɪᴀᴛᴇ ʏᴏᴜʀ ᴛʀᴜꜱᴛ ᴀɴᴅ ꜱᴜᴘᴘᴏʀᴛ.</b>\n\n👇 <b>ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ꜰʀᴏᴍ ᴛʜᴇ ᴍᴇɴᴜ ᴛᴏ ɢᴇᴛ ꜱᴛᴀʀᴛᴇᴅ.</b>"
    )


def send_main_welcome(user_id):
    bot.send_message(user_id, welcome_text_main(), parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))


def send_order_log_to_channel(user_id, order_id, service_id, service_name, link, quantity, total_cost):
    try:
        db = load_json(DB_FILE)
        user = db.get(str(user_id), {})
        name = user.get("name", "Unknown")
        username = user.get("username", "No Username")
        username_line = f"@{username}" if username and username != "No Username" else "N/A"
        user_type = "👤 ɴᴏʀᴍᴀʟ"
        if is_vip_user(user_id):
            user_type = "👑 ᴠɪᴘ"

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🛒 ᴏʀᴅᴇʀ ɴᴏᴡ", url=BOT_LINK))
        kb.add(types.InlineKeyboardButton("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ", url=ORDER_LOG_CHANNEL_LINK))

        text = (
            "🛒 <b>ɴᴇᴡ ᴏʀᴅᴇʀ ʟᴏɢ</b>\n\n"
            f"👤 <b>ᴜꜱᴇʀ :</b> {html.escape(str(name))}\n"
            f"🆔 <b>ᴜꜱᴇʀ ɪᴅ :</b> <code>{user_id}</code>\n"
            f"🏷️ <b>ᴜꜱᴇʀ ᴛʏᴘᴇ :</b> {user_type}\n\n"
            f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ :</b> <code>{order_id}</code>\n"
            f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ :</b> <code>{service_id}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ :</b> {html.escape(str(service_name))}\n"
            f"🔗 <b>ʟɪɴᴋ :</b> {html.escape(str(link))}\n"
            f"🔢 <b>ǫᴜᴀɴᴛɪᴛʏ :</b> {quantity}\n"
            f"💰 <b>ᴘʀɪᴄᴇ :</b> ₹{float(total_cost):.2f}\n"
            f"📅 <b>ᴅᴀᴛᴇ :</b> {datetime.now().strftime('%d-%m-%Y %I:%M %p')}\n\n"
            "🚀 <b>ᴄʜᴇᴀᴘᴇꜱᴛ & ꜰᴀꜱᴛ ꜱᴍᴍ ꜱᴇʀᴠɪᴄᴇꜱ</b>"
        )
        bot.send_message(ORDER_LOG_CHANNEL, text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        print("Order log channel error:", e)
# --- END FORCE JOIN + ORDER LOG CHANNEL ---

# --- ADMIN COMMAND ---
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.chat.id == ADMIN_ID:
        send_admin_panel_message(ADMIN_ID)
    else:
        bot.send_message(message.chat.id, "❌ ᴀᴀᴘ ᴀᴅᴍɪɴ ɴᴀʜɪ ʜᴀɪɴ.")

# --- TEXT FLOW HANDLERS ---
@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    args = message.text.split()
    referrer = args[1] if len(args) > 1 else None
    if not setup_user(message.chat.id, message, referrer):
        bot.send_message(message.chat.id, "🚫 <b>ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ɪꜱ ᴅᴇʟᴇᴛᴇᴅ. ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ.</b>", parse_mode="HTML")
        return

    if is_maintenance_on() and message.chat.id != ADMIN_ID:
        bot.send_message(
            message.chat.id,
            "🛠️ <b>ʙᴏᴛ ɪꜱ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ.</b>\n\n"
            "⏳ <b>ᴘʟᴇᴀꜱᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b>",
            parse_mode="HTML"
        )
        return

    if message.chat.id != ADMIN_ID and not is_user_joined_order_channel(message.chat.id):
        send_force_join_message(message.chat.id, incoming_message=message)
        return

    send_main_welcome(message.chat.id)
    return
    
    welcome_text = (
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>\n\n🎉 <b>ᴡᴇʟᴄᴏᴍᴇ!</b>\n\n<b>ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴄʜᴏᴏꜱɪɴɢ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ.</b>\n\n🚀 <b>ᴇɴᴊᴏʏ ᴘʀᴇᴍɪᴜᴍ ꜱᴍᴍ ꜱᴇʀᴠɪᴄᴇꜱ ᴡɪᴛʜ ꜰᴀꜱᴛ ᴅᴇʟɪᴠᴇʀʏ, ʜɪɢʜ Qᴜᴀʟɪᴛʏ ᴀɴᴅ ꜱᴇᴄᴜʀᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ.</b>\n\n✨ <b>ᴡʜᴀᴛ ᴡᴇ ᴏꜰꜰᴇʀ</b>\n\n💎 <b>ᴘʀᴇᴍɪᴜᴍ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n⚡ <b>ꜰᴀꜱᴛ & ᴀᴜᴛᴏᴍᴀᴛᴇᴅ ᴅᴇʟɪᴠᴇʀʏ</b>\n🛡️ <b>ꜱᴀꜰᴇ ᴀɴᴅ ᴛʀᴜꜱᴛᴇᴅ ᴏʀᴅᴇʀꜱ</b>\n💰 <b>ᴄᴏᴍᴘᴇᴛɪᴛɪᴠᴇ ᴘʀɪᴄᴇꜱ</b>\n🎫 <b>24×7 ꜱᴜᴘᴘᴏʀᴛ ᴠɪᴀ ᴛɪᴄᴋᴇᴛ</b>\n\n❤️ <b>ᴡᴇ ᴛʀᴜʟʏ ᴀᴘᴘʀᴇᴄɪᴀᴛᴇ ʏᴏᴜʀ ᴛʀᴜꜱᴛ ᴀɴᴅ ꜱᴜᴘᴘᴏʀᴛ.</b>\n\n👇 <b>ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ꜰʀᴏᴍ ᴛʜᴇ ᴍᴇɴᴜ ᴛᴏ ɢᴇᴛ ꜱᴛᴀʀᴛᴇᴅ.</b>"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard(message.chat.id))


@bot.message_handler(content_types=['document'])
def handle_exchange_document(message):
    user_id = message.chat.id
    if user_id != ADMIN_ID:
        return

    st = admin_state.get(ADMIN_ID, {})
    mode = st.get("exchange_mode")
    if mode not in ["await_zip", "await_botpy", "await_json"]:
        return

    try:
        if mode == "await_zip":
            filename, pending_path = _download_admin_document(message, allowed_ext=[".zip"])
            _validate_zip_file(pending_path)
            _prepare_pending_exchange("zip", pending_path, filename)

        elif mode == "await_botpy":
            filename, pending_path = _download_admin_document(message, expected_name="bot.py", allowed_ext=[".py"])
            _validate_botpy(pending_path)
            _prepare_pending_exchange("botpy", pending_path, filename)

        elif mode == "await_json":
            target_json = st.get("target_json")
            filename, pending_path = _download_admin_document(message, expected_name=target_json, allowed_ext=[".json"])
            _validate_json_file(pending_path)
            _prepare_pending_exchange("json", pending_path, filename, target_json=target_json)

    except Exception as e:
        bot.send_message(
            ADMIN_ID,
            f"❌ <b>ꜰɪʟᴇ ᴇʀʀᴏʀ:</b> <code>{html.escape(str(e))}</code>",
            parse_mode="HTML",
            reply_markup=exchange_files_keyboard()
        )


@bot.message_handler(func=lambda message: True)
def handle_text(message):
    text = message.text
    user_id = message.chat.id

    if text in MENU_BUTTONS:
        try:
            bot.clear_step_handler_by_chat_id(user_id)
        except Exception:
            pass
    if not setup_user(user_id, message):
        bot.send_message(user_id, "🚫 <b>ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ɪꜱ ᴅᴇʟᴇᴛᴇᴅ. ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ.</b>", parse_mode="HTML")
        return

    if is_maintenance_on() and user_id != ADMIN_ID:
        bot.send_message(
            user_id,
            "🛠️ <b>ʙᴏᴛ ɪꜱ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ.</b>\n\n"
            "⏳ <b>ᴘʟᴇᴀꜱᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b>",
            parse_mode="HTML"
        )
        return

    db = load_json(DB_FILE)

    if str(user_id) in db and not db[str(user_id)].get("active", True):
        bot.send_message(
            user_id,
            "🚫 ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ ꜰʀᴏᴍ ᴜꜱɪɴɢ ᴛʜɪꜱ ʙᴏᴛ"
        )
        return

    if user_id == ADMIN_ID and admin_state.get(ADMIN_ID, {}).get("extra_bonus_step"):
        if _process_extra_bonus_text(message):
            return

    # ✅ Reply-keyboard navigation for admin panel and service menus
    if text in ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
        USER_NAV_STATE.pop(user_id, None)
        bot.send_message(
            user_id,
            "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(user_id)
        )
        return

    if text == "⬅️ ʙᴀᴄᴋ":
        nav_state = USER_NAV_STATE.get(user_id, {})
        if nav_state.get("mode") == "service_list":
            platform = nav_state.get("platform", "ig")
            USER_NAV_STATE[user_id] = {"platform": platform, "main_section": "services", "mode": "order_subcats"}
            bot.send_message(user_id, "✨ <b>ꜱᴇʟᴇᴄᴛ ꜱᴜʙ-ᴄᴀᴛᴇɢᴏʀʏ</b>", parse_mode="HTML", reply_markup=subcat_keyboard(platform))
            return
        if nav_state.get("mode") == "order_subcats":
            USER_NAV_STATE[user_id] = {"main_section": "services", "mode": "order_platforms"}
            bot.send_message(user_id, "<b>🌐 ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ᴘʟᴀᴛꜰᴏʀᴍ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏʀ:</b>", parse_mode="HTML", reply_markup=platforms_keyboard())
            return
        if nav_state.get("mode") == "order_platforms":
            USER_NAV_STATE[user_id] = {"main_section": "services"}
            open_main_section(user_id, "services")
            return
        if nav_state.get("mode") == "api_settings":
            send_admin_category_message(user_id, "⚙️ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ")
            return
        if nav_state.get("mode") == "admin_category":
            # Admin sub-menu se Back = exactly ek step, yani Admin Panel.
            send_admin_panel_message(user_id)
            return
        if nav_state.get("mode") == "admin_home":
            # Admin Panel se Back = Main Menu.
            USER_NAV_STATE.pop(user_id, None)
            bot.send_message(
                user_id,
                "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(user_id)
            )
            return
        if nav_state.get("mode") == "terms_menu":
            show_info_center_menu(user_id)
            return
        if nav_state.get("mode") == "info_center":
            USER_NAV_STATE[user_id] = {"main_section": "settings"}
            open_main_section(user_id, "settings")
            return
        if nav_state.get("mode") == "ig_followers_filter":
            USER_NAV_STATE[user_id] = {"platform": "ig", "main_section": "services"}
            bot.send_message(
                user_id,
                "✨ <b>ꜱᴇʟᴇᴄᴛ ꜱᴜʙ-ᴄᴀᴛᴇɢᴏʀʏ</b>",
                parse_mode="HTML",
                reply_markup=subcat_keyboard("ig")
            )
            return
        if nav_state.get("platform"):
            platform = nav_state.get("platform", "ig")
            USER_NAV_STATE[user_id] = {"main_section": "services", "mode": "order_platforms"}
            bot.send_message(user_id, "<b>🌐 ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ᴘʟᴀᴛꜰᴏʀᴍ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏʀ:</b>", parse_mode="HTML", reply_markup=platforms_keyboard())
            return
        if nav_state.get("main_section"):
            USER_NAV_STATE.pop(user_id, None)
            bot.send_message(
                user_id,
                "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(user_id)
            )
            return
        if user_id == ADMIN_ID and admin_state.get(ADMIN_ID):
            admin_state.pop(ADMIN_ID, None)
            send_admin_panel_message(user_id)
            return
        if user_id == ADMIN_ID:
            send_admin_panel_message(user_id)
            return
        USER_NAV_STATE.pop(user_id, None)
        bot.send_message(
            user_id,
            "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(user_id)
        )
        return

    if text == "🌐 ᴘʟᴀᴛꜰᴏʀᴍꜱ":
        USER_NAV_STATE.pop(user_id, None)
        bot.send_message(
            user_id,
            "🌐 <b>ꜱᴇʟᴇᴄᴛ ᴘʟᴀᴛꜰᴏʀᴍ</b>",
            parse_mode="HTML",
            reply_markup=platforms_keyboard()
        )
        return

    if text == "📋 ꜱᴇʀᴠɪᴄᴇꜱ":
        open_main_section(user_id, "services")
        return

    if text == "📦 ᴏʀᴅᴇʀꜱ":
        open_main_section(user_id, "orders")
        return

    if text == "ᴘᴀʏᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ":
        open_main_section(user_id, "wallet")
        return

    if text == "👤 ᴀᴄᴄᴏᴜɴᴛ":
        open_main_section(user_id, "account")
        return

    if text in ["⚙️ ꜱᴇᴛᴛɪɴɢꜱ", "⚙️ ꜱᴇᴛᴛɪɴɢꜱ & ᴛɪᴄᴋᴇᴛ", "🎫 ᴛɪᴄᴋᴇᴛ & ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ"]:
        open_main_section(user_id, "settings")
        return

    if user_id == ADMIN_ID and _inline_maker_handle_message(message):
        return

    if user_id == ADMIN_ID and text == "⬅️ ʙᴀᴄᴋ":
        nav = USER_NAV_STATE.get(user_id, {})
        if nav.get("mode") == "admin_home":
            USER_NAV_STATE.pop(user_id, None)
            bot.send_message(user_id, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))
        else:
            send_admin_panel_message(user_id)
        return

    # ✅ Exchange Files menu and confirmation
    if user_id == ADMIN_ID:
        st = admin_state.get(ADMIN_ID, {})
        if text == EXCHANGE_MENU_LABEL:
            send_exchange_files_menu(user_id)
            return
        if text == EXCHANGE_UPDATE_ZIP:
            start_exchange_zip()
            return
        if text == EXCHANGE_UPDATE_BOT:
            start_exchange_botpy()
            return
        if text == EXCHANGE_UPDATE_JSON:
            start_exchange_json()
            return

        if st.get("exchange_mode") == "select_json" and text in _json_files_list():
            admin_state[ADMIN_ID] = {"exchange_mode": "await_json", "target_json": text}
            bot.send_message(
                ADMIN_ID,
                f"📄 <b>{html.escape(text)}</b>\n\n📤 <b>ɴᴇᴡ {html.escape(text)} ꜰɪʟᴇ ꜱᴇɴᴅ ᴋᴀʀᴏ.</b>",
                parse_mode="HTML",
                reply_markup=_admin_flow_keyboard([], row_width=2)
            )
            return

        if st.get("exchange_mode") == "confirm" and text == EXCHANGE_CONFIRM:
            try:
                result_name = _apply_pending_exchange()
                admin_state.pop(ADMIN_ID, None)
                bot.send_message(
                    ADMIN_ID,
                    f"✅ <b>{html.escape(str(result_name))} ʀᴇᴘʟᴀᴄᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ.</b>\n\n♻️ <b>ʙᴏᴛ ᴀᴜᴛᴏ ʀᴇꜱᴛᴀʀᴛ ʜᴏ ʀᴀʜᴀ ʜᴀɪ...</b>",
                    parse_mode="HTML",
                    reply_markup=admin_keyboard()
                )
                _restart_bot_after_exchange(2)
            except Exception as e:
                bot.send_message(ADMIN_ID, f"❌ <b>ᴇxᴄʜᴀɴɢᴇ ᴇʀʀᴏʀ:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")
            return

        if st.get("exchange_mode") in ["menu", "await_zip", "await_botpy", "await_json", "confirm", "select_json"] and text in [EXCHANGE_CANCEL, "⬅️ ʙᴀᴄᴋ"]:
            cancel_exchange_files()
            return

    # ✅ Admin Add Service / Service Shift reply-keyboard selections
    if user_id == ADMIN_ID:
        st = admin_state.get(ADMIN_ID, {})

        add_mode = st.get("add_mode")
        if add_mode:
            if text in ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
                admin_state.pop(ADMIN_ID, None)
                bot.send_message(user_id, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))
                return
            if text == "⬅️ ʙᴀᴄᴋ":
                _handle_add_flow_back(message)
                return

            if add_mode == "platform":
                platform = _platform_from_label(text)
                if platform:
                    show_add_service_subcategories(platform)
                    return

            if add_mode == "subcat":
                platform = st.get("current_platform")
                subcat_key = _subcat_from_label(platform, text)
                if subcat_key:
                    ask_add_service_name(subcat_key)
                    return

        shift_mode = st.get("shift_mode")
        if shift_mode:
            if text in ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
                admin_state.pop(ADMIN_ID, None)
                bot.send_message(user_id, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))
                return
            if text == "⬅️ ʙᴀᴄᴋ":
                _handle_shift_flow_back(message)
                return

            if shift_mode == "source_platform":
                platform = _platform_from_label(text)
                if platform:
                    show_shift_source_subcategories(message, platform)
                    return

            if shift_mode == "source_subcat":
                platform = st.get("shift_source_platform")
                subcat = _subcat_from_label(platform, text)
                if subcat:
                    show_shift_service_list(message, subcat)
                    return

            if shift_mode == "service_select":
                sid = st.get("shift_service_text_map", {}).get(text)
                if sid:
                    choose_shift_destination_platform(message, sid)
                    return
                # ID type karke bhi select kar sakte hain
                raw_sid = str(text).strip().split()[0]
                if raw_sid.isdigit():
                    choose_shift_destination_platform(message, raw_sid)
                    return

            if shift_mode == "dest_platform":
                platform = _platform_from_label(text)
                if platform:
                    show_shift_destination_subcategories(message, platform)
                    return

            if shift_mode == "dest_subcat":
                platform = st.get("shift_destination_platform")
                subcat = _subcat_from_label(platform, text)
                if subcat:
                    finish_service_shift(message, subcat)
                    return

    if user_id == ADMIN_ID and admin_state.get(ADMIN_ID, {}).get("backup_json_select"):
        if text in ["⬅️ ʙᴀᴄᴋ", "⬅️ ʙᴀᴄᴋ"]:
            admin_state.pop(ADMIN_ID, None)
            show_backup_menu()
            return
        if str(text).endswith(".json"):
            admin_state.pop(ADMIN_ID, None)
            send_json_backup(text)
            return

    if user_id == ADMIN_ID and text in ADMIN_CATEGORY_ACTIONS:
        send_admin_category_message(user_id, text)
        return

    if user_id == ADMIN_ID and text in ADMIN_TEXT_ACTIONS:
        run_callback_from_keyboard(message, ADMIN_TEXT_ACTIONS[text])
        return

    selected_platform = PLATFORM_TEXT_MAP.get(text)
    if not selected_platform:
        for p_key, p_cfg in ADD_SERVICE_CATS.items():
            if text == f"{p_cfg.get('icon', '📦')} {p_cfg['title']}":
                selected_platform = p_key
                break

    if selected_platform:
        USER_NAV_STATE[user_id] = {"platform": selected_platform, "main_section": "services", "mode": "order_subcats"}
        bot.send_message(
            user_id,
            "✨ <b>ꜱᴇʟᴇᴄᴛ ꜱᴜʙ-ᴄᴀᴛᴇɢᴏʀʏ</b>",
            parse_mode="HTML",
            reply_markup=subcat_keyboard(selected_platform)
        )
        return

    nav_state = USER_NAV_STATE.get(user_id, {})
    nav_platform = nav_state.get("platform")

    if nav_platform == "ig" and text == str(ADD_SERVICE_CATS.get("ig", {}).get("subs", {}).get("ig_followers")):
        USER_NAV_STATE[user_id] = {"platform": "ig", "main_section": "services", "mode": "service_list"}
        show_services_for_subcat_keyboard(user_id, "ig_followers")
        return

    if nav_platform and nav_platform in ADD_SERVICE_CATS:
        selected_subcat = None
        for s_key, s_title in ADD_SERVICE_CATS[nav_platform].get("subs", {}).items():
            if text == str(s_title):
                selected_subcat = s_key
                break
        if selected_subcat:
            USER_NAV_STATE[user_id] = {"platform": nav_platform, "main_section": "services", "mode": "service_list"}
            show_services_for_subcat_keyboard(user_id, selected_subcat)
            return

    if text == "📋 ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇ":
        USER_NAV_STATE[user_id] = {"main_section": "services", "mode": "order_platforms"}
        bot.send_message(user_id, "<b>🌐 ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ᴘʟᴀᴛꜰᴏʀᴍ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏʀ:</b>", reply_markup=platforms_keyboard(), parse_mode="HTML")

    elif text == "⭐ ꜰᴀᴠᴏᴜʀɪᴛᴇꜱ":
        show_favorite_services(user_id)

    elif text == "🕒 ʀᴇᴄᴇɴᴛ":
        show_recent_services(user_id)

    elif text == "🔥 ᴛᴏᴘ":
        show_user_top_services(user_id)

    elif text == "📌 ᴘɪɴɴᴇᴅ":
        show_pinned_services(user_id)
        
    elif text == "👤 ᴘʀᴏꜰɪʟᴇ":
        db = load_json(DB_FILE)
        user = db.get(str(user_id), {})

        orders_db = load_json(ORDERS_FILE)
        user_history = orders_db.get(str(user_id), [])

        funds_db = load_json(FUNDS_HISTORY_FILE)
        funds_history = funds_db.get(str(user_id), [])

        bal = get_balance(user_id)
        ref_count = user.get("referrals_count", 0)

        vip_status = "👑 ᴠɪᴘ ᴜꜱᴇʀ" if user.get("vip", False) else "👤 ɴᴏʀᴍᴀʟ ᴜꜱᴇʀ"

        total_orders = len(user_history)
        total_spent = sum(float(o.get("charge", 0)) for o in user_history)
        total_funds = sum(float(f.get("amount", 0)) for f in funds_history)

        service_counter = {}

        for o in user_history:
            sid = str(o.get("srv_id", ""))
            if sid:
                service_counter[sid] = service_counter.get(sid, 0) + 1

        if service_counter:
            fav_sid = max(service_counter, key=service_counter.get)
            favourite = fav_sid
        else:
            favourite = "ɴᴏɴᴇ"
        join_date = user.get("join_date", "ɴᴏᴛ ꜱᴇᴛ")

        profile_text = (
            "👤 <b>ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ ᴅᴇᴛᴀɪʟꜱ</b>\n\n"

            f"ᴜꜱᴇʀ ᴛʏᴘᴇ » {vip_status}\n"
            f"🆔 <b>ᴜꜱᴇʀ ɪᴅ »</b> <code>{user_id}</code>\n"
            f"👤 <b>ɴᴀᴍᴇ »</b> {html.escape(message.from_user.first_name)}\n"
            f"💵 <b>ʙᴀʟᴀɴᴄᴇ »</b> ₹{bal:.2f}\n\n"
            f"📦 <b>ᴛᴏᴛᴀʟ ᴏʀᴅᴇʀꜱ »</b> {total_orders}\n"
            f"💸 <b>ᴛᴏᴛᴀʟ ꜱᴘᴇɴᴛ »</b> ₹{total_spent:.2f}\n"
            f"💳 <b>ᴛᴏᴛᴀʟ ꜰᴜɴᴅ ᴀᴅᴅᴇᴅ »</b> ₹{total_funds:.2f}\n"
            f"👥 <b>ᴛᴏᴛᴀʟ ʀᴇꜰᴇʀʀᴀʟꜱ »</b> {ref_count}\n\n"
            f"⭐ <b>ꜰᴀᴠᴏʀɪᴛᴇ ꜱᴇʀᴠɪᴄᴇ »</b> {favourite}\n"
            f"🥇 <b>ʀᴀɴᴋ »</b> {_user_rank(user_id)}\n"
            f"💎 <b>ᴠɪᴘ ᴘʀᴏɢʀᴇꜱꜱ »</b> ₹{min(total_spent, 500):.2f}/₹500\n"
            f"📅 <b>ᴊᴏɪɴ ᴅᴀᴛᴇ »</b> {join_date}\n\n"
            "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ</b> 💪🏻"
        )

        bot.send_message(user_id, profile_text, parse_mode="HTML")
        
    elif text == "💎 ᴠɪᴘ ᴘʀᴏɢʀᴇꜱꜱ":
        show_vip_progress(user_id)

    elif text == "🏆 ᴀᴄʜɪᴇᴠᴇᴍᴇɴᴛꜱ":
        show_achievements(user_id)

    elif text == "📊 ᴍᴏɴᴛʜʟʏ ʀᴇᴘᴏʀᴛ":
        show_monthly_report(user_id)

    elif text == "🥇 ᴍʏ ʀᴀɴᴋ":
        show_user_rank(user_id)

    elif text == "📋 ꜱᴇʀᴠɪᴄᴇ ɪᴅ ʟɪꜱᴛ":
        show_user_service_id_list(user_id)
            
    elif text == "📦 ᴍʏ ᴏʀᴅᴇʀꜱ":  # ONLY ORDERS HISTORY
        orders_db = load_json(ORDERS_FILE)
        user_history = orders_db.get(str(user_id), [])
        if not user_history:
            bot.send_message(user_id, "❌ <b><b>ᴀᴀᴘɴᴇ ᴀʙʜɪ ᴛᴀᴋ ᴋᴏɪ ᴏʀᴅᴇʀ ɴᴀʜɪ ʟᴀɢᴀʏᴀ ʜᴀɪ</b>.</b>", parse_mode="HTML")
            return
            
        history_text = "📦 <b>ʏᴏᴜʀ ᴏʀᴅᴇʀ ʜɪꜱᴛᴏʀʏ</b>\n\n"

        for order in user_history[::-1]:
            service_id = str(order.get("srv_id"))
            s_info = find_service(service_id)
            service_name = to_mini_text(s_info[0]) if s_info else "ᴜɴᴋɴᴏᴡɴ ꜱᴇʀᴠɪᴄᴇ"

            history_text += (
                f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order.get('order_id')}</code>\n"
                f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
                f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(service_name)}\n"
                f"🔗 <b>ʟɪɴᴋ »</b> {html.escape(order.get('link', 'N/A'))}\n"
                f"🔢 <b>Qᴜᴀɴᴛɪᴛʏ »</b> {order.get('qty')}\n"
                f"💸 <b>ᴄʜᴀʀɢᴇᴅ »</b> ₹{float(order.get('charge', 0)):.2f}\n"
                f"📅 <b>ᴅᴀᴛᴇ »</b> {order.get('date', 'N/A')}\n\n"
            )

        history_text += (
            "📊 <b>ꜱᴛᴀᴛᴜꜱ » ᴄʜᴇᴄᴋ ᴠɪᴀ ʙᴜᴛᴛᴏᴍ</b>\n\n "
            "⚡ <b>ɪɴꜱᴛᴀɴᴛ & ꜰᴀꜱᴛ ᴅᴇʟɪᴠᴇʀʏ</b>\n"
            "🛡️ <b>ꜱᴀꜰᴇ & ᴛʀᴜꜱᴛᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n"
            "🚀 <b>ᴘʀᴇᴍɪᴜᴍ ꜱᴍᴍ ꜱᴇʀᴠɪᴄᴇꜱ ᴀᴛ ʙᴇꜱᴛ ʀᴀᴛᴇꜱ</b>\n"
            "💎 <b>ʙᴜɪʟᴅ ʏᴏᴜʀ ꜱᴏᴄɪᴀʟ ᴘʀᴇꜱᴇɴᴄᴇ ᴡɪᴛʜ ᴜꜱ</b>\n\n"
            "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>"
        )

        mk = types.InlineKeyboardMarkup(row_width=1)
        for o in user_history[::-1][:5]:
            oid = str(o.get("order_id"))
            sid = str(o.get("srv_id", ""))
            mk.add(types.InlineKeyboardButton(f"🔁 ʀᴇᴏʀᴅᴇʀ » {oid} / {sid}", callback_data=f"reorder_{oid}"))
        bot.send_message(user_id, history_text[:4000], parse_mode="HTML", reply_markup=mk) 

    elif message.text == "🎫 ᴀᴘᴘʟʏ ᴄᴏᴜᴘᴏɴ":
        msg = bot.send_message(
            user_id,
            "🎫 ᴇɴᴛᴇʀ ᴄᴏᴜᴘᴏɴ ᴄᴏᴅᴇ:"
        )
        bot.register_next_step_handler(msg, process_coupon)
            
    elif text == "ℹ️ ɪɴꜰᴏ ᴄᴇɴᴛᴇʀ":
        show_info_center_menu(user_id)

    elif text == "📖 ʜᴏᴡ ᴛᴏ ᴏʀᴅᴇʀ":
        show_how_to_order(user_id)

    elif text == "📜 ᴛᴇʀᴍꜱ & ʀᴜʟᴇꜱ":
        show_terms_rules_menu(user_id)

    elif text == "ℹ️ ᴀʙᴏᴜᴛ ʙᴏᴛ":
        show_about_bot(user_id)

    elif text == "📜 ɢᴇɴᴇʀᴀʟ ʀᴜʟᴇꜱ":
        show_terms_section(user_id, "general")

    elif text == "🔄 ʀᴇꜰɪʟʟ ᴘᴏʟɪᴄʏ":
        show_terms_section(user_id, "refill")

    elif text == "💰 ʀᴇꜰᴜɴᴅ ᴘᴏʟɪᴄʏ":
        show_terms_section(user_id, "refund")

    elif text == "ℹ️ ɪᴍᴘᴏʀᴛᴀɴᴛ ɴᴏᴛᴇꜱ":
        show_terms_section(user_id, "notes")

    elif text == "⚙️ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ":
        settings_text = (
            "⚙️ <b><b>ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ</b></b>\n\n"
            "🤖 <b><b>ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ »</b></b> 🌟 ᴏɴʟɪɴᴇ & ᴀᴄᴛɪᴠᴇ\n"
            "🌐 <b><b>ʟᴀɴɢᴜᴀɢᴇ »</b></b> 🇬🇧 ᴇɴɢʟɪꜱʜ (ᴅᴇꜰᴀᴜʟᴛ)\n"
            "⚡ <b><b><b>ꜱᴇʀᴠᴇʀ ꜱᴘᴇᴇᴅ »</b></b></b> 🚀 100% ꜰᴀꜱᴛ\n\n"
            "💡 <i>Note: Agar aapko koi dikkat aaye to support me admin se contact karein.</i>"
        )
        bot.send_message(user_id, settings_text, parse_mode="HTML")

    elif text == "💰 ᴡᴀʟʟᴇᴛ":
        bal = get_balance(user_id)

        fancy_bal = fancy_number(f"{bal:.2f}")

        bot.send_message(
            user_id,
            f"👛 <b>ᴡᴀʟʟᴇᴛ ᴀᴍᴏᴜɴᴛ</b>\n\n"
            f"💰 ᴀᴠᴀɪʟᴀʙʟᴇ ʙᴀʟᴀɴᴄᴇ » ₹{fancy_bal}\n"
            f"🟢 ᴀᴄᴄᴏᴜɴᴛ ꜱᴛᴀᴛᴜꜱ » ᴀᴄᴛɪᴠᴇ\n\n"
            f"🚀 ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ɪꜱ ʀᴇᴀᴅʏ ꜰᴏʀ ɴᴇᴡ ᴏʀᴅᴇʀꜱ\n"
            f"⚡ ᴇɴᴊᴏʏ ꜰᴀꜱᴛ ᴏʀᴅᴇʀ ᴘʀᴏᴄᴇꜱꜱɪɴɢ\n"
            f"💎 ɢᴇᴛ ᴘʀᴇᴍɪᴜᴍ ꜱᴇʀᴠɪᴄᴇꜱ ᴀᴛ ʙᴇꜱᴛ ʀᴀᴛᴇꜱ\n"
            f"🛡️ ꜱᴇᴄᴜʀᴇ ᴘᴀʏᴍᴇɴᴛꜱ ᴀɴᴅ ʀᴇʟɪᴀʙʟᴇ ꜱᴜᴘᴘᴏʀᴛ\n\n"
            f"🙏 ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴄʜᴏᴏꜱɪɴɢ\n"
            f"🤖 ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ",
            parse_mode="HTML"
        )
        
    elif text == "➕ ᴀᴅᴅ ꜰᴜɴᴅ":
        caption = (
            "💳 <b>𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗖𝗘𝗡𝗧𝗘𝗥</b>\n\n"
            "📷 <b>ꜱᴄᴀɴ ᴛʜᴇ Qʀ ᴄᴏᴅᴇ ᴛᴏ ᴄᴏᴍᴘʟᴇᴛᴇ ᴘᴀʏᴍᴇɴᴛ</b>\n\n"
            "💰 <b>ᴇɴᴛᴇʀ ᴛʜᴇ ᴇxᴀᴄᴛ ᴀᴍᴏᴜɴᴛ ᴘᴀɪᴅ</b>\n\n"
            "⚠️ <b>ᴍɪɴɪᴍᴜᴍ ᴀᴍᴏᴜɴᴛ: ₹5</b>"
        )

        with open("qr.png", "rb") as qr:
            msg = bot.send_photo(
                user_id,
                qr,
                caption=caption,
                parse_mode="HTML"
            )
        bot.register_next_step_handler(msg, process_fund_amount)
        
    elif text == "📊 ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ":
        msg = bot.send_message(user_id, "<b>📊 ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ</b>\n\n✍️ ᴀᴘɴᴇ ᴏʀᴅᴇʀ ᴋᴀ ʟɪᴠᴇ ꜱᴛᴀᴛᴜꜱ ᴄʜᴇᴄᴋ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ᴀᴘɴɪ <b>ᴏʀᴅᴇʀ ɪᴅ</b> ᴇɴᴛᴇʀ ᴋᴀʀᴇɪɴ:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_status_check)
        
    elif text == "🎫 ᴛɪᴄᴋᴇᴛ":
        show_ticket_menu(user_id)
        
    elif text == "🎁 ʀᴇꜰᴇʀʀᴀʟ":
        db = load_json(DB_FILE)
        user_ref_data = db.get(str(user_id), {})
        ref_count = user_ref_data.get("referrals_count", 0)
        ref_earnings = float(user_ref_data.get("referral_earnings", 0))
        try: bot_username = bot.get_me().username
        except: bot_username = "ALL_TYPE_SERVICE_PROVIDER_BOT"
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        bot.send_message(
            user_id,
            f"<b>🎁 ʀᴇꜰᴇʀʀᴀʟ ᴘʀᴏɢʀᴀᴍ</b>\n\n"
            f"<b>🔗 ʏᴏᴜʀ ʀᴇꜰᴇʀʀᴀʟ ʟɪɴᴋ:</b>\n{ref_link}\n\n"
            f"<b>👥 ᴛᴏᴛᴀʟ ʀᴇꜰᴇʀʀᴀʟꜱ:</b> {ref_count}\n"
            f"<b>💰 ᴛᴏᴛᴀʟ ᴇᴀʀɴɪɴɢꜱ:</b> ₹{ref_earnings:.2f}\n\n"
            f"🎉 <b>ʙᴇɴᴇꜰɪᴛ:</b> ᴀᴀᴘᴋᴇ ʀᴇꜰᴇʀ ᴋɪʏᴇ ᴜꜱᴇʀ ᴊᴀʙ ʙʜɪ ꜰᴜɴᴅ ᴀᴅᴅ ᴋᴀʀᴇɴɢᴇ, ᴀᴀᴘᴋᴏ ᴜꜱᴋᴀ <b>2%</b> ʙᴏɴᴜꜱ ᴡᴀʟʟᴇᴛ ᴍᴇ ᴍɪʟᴇɢᴀ.",
            parse_mode="HTML"
        )

    elif text == "💳 ᴡᴀʟʟᴇᴛ ʜɪꜱᴛᴏʀʏ":
        show_wallet_history(user_id)

    elif text == "📜 ꜰᴜɴᴅ ʜɪꜱᴛᴏʀʏ":
        show_fund_history(user_id, page=1)

    elif text == "🔍 ꜱᴇᴀʀᴄʜ ꜱᴇʀᴠɪᴄᴇ":
        start_service_search(message)

    elif text == "❌ ᴄᴀɴᴄᴇʟ ᴏʀᴅᴇʀ":
        msg = bot.send_message(
            user_id,
            "🆔 <b>ᴇɴᴛᴇʀ ᴏʀᴅᴇʀ ɪᴅ:</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_cancel_order)

    elif text == "🔄 ʀᴇꜰɪʟʟ ᴏʀᴅᴇʀ":
        msg = bot.send_message(
            user_id,
            "🆔 <b>ᴇɴᴛᴇʀ ᴏʀᴅᴇʀ ɪᴅ:</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_refill_order)

    elif text == "⚙️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ" and user_id == ADMIN_ID:
        send_admin_panel_message(ADMIN_ID)

# --- LIVE ORDER STATUS TRACKING ---
def process_order_status_check(message):
    user_id = message.chat.id
    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return

    order_id = message.text.strip()
    if not order_id.isdigit():
        bot.send_message(user_id, "❌ ɢᴀʟᴀᴛ ᴏʀᴅᴇʀ ɪᴅ! ꜱɪʀꜰ ɴᴜᴍʙᴇʀ ᴅᴀʟᴇɪɴ.")
        return

    orders_db = load_json(ORDERS_FILE)
    user_history = orders_db.get(str(user_id), [])

    found_order = None
    for o in user_history:
        if str(o.get("order_id")) == order_id:
            found_order = o
            break

    if not found_order:
        bot.send_message(user_id, "❌ ʏᴇ ᴏʀᴅᴇʀ ᴀᴀᴘᴋᴇ ᴀᴄᴄᴏᴜɴᴛ ᴍᴇ ɴᴀʜɪ ᴍɪʟᴀ.")
        return

    service_id = str(found_order.get("srv_id", ""))
    link = found_order.get("link", "N/A")
    quantity = int(found_order.get("qty", 0))
    charge = float(found_order.get("charge", 0))
    date = found_order.get("date", "N/A")

    s_info = find_service(service_id)
    service_name = to_mini_text(s_info[0]) if s_info else "ᴜɴᴋɴᴏᴡɴ ꜱᴇʀᴠɪᴄᴇ"

    try:
        response = _api_post(
            {"key": SMM_API_KEY, "action": "status", "order": order_id},
            timeout=(4, 8)
        ).json()

        if "status" not in response:
            bot.send_message(user_id, f"❌ <b>ᴇʀʀᴏʀ:</b> {response.get('error', 'Order not found')}", parse_mode="HTML")
            return

        status = str(response.get("status", "")).lower()
        start_count = response.get("start_count", "0")
        remains_raw = response.get("remains", "0")

        try:
                remains_num = int(str(remains_raw).replace(",", "").strip())
        except:
                remains_num = 0
        if status == "completed":
            completed = quantity
            progress_text = "100%"
            completed_text = f"{quantity} / {quantity}"
        elif remains_num > 0 and quantity > 0:
            completed = max(quantity - remains_num, 0)
            progress = min(100, max(0, (completed / quantity) * 100))
            completed_text = f"{completed} / {quantity}"
            progress_text = f"{progress:.0f}%"
        else:
            completed_text = "ᴄᴀʟᴄᴜʟᴀᴛɪɴɢ..."
            progress_text = "ᴄᴀʟᴄᴜʟᴀᴛɪɴɢ..."

        if status == "completed":
            display_status = "✅ <b>ꜱᴛᴀᴛᴜꜱ »</b> ᴄᴏᴍᴘʟᴇᴛᴇᴅ"
            footer_msg = "🎉 <b>ᴏʀᴅᴇʀ ꜱᴜᴄᴄᴇꜱꜰᴜʟʟʏ ᴅᴇʟɪᴠᴇʀᴇᴅ</b>"
        elif status in ("processing", "pending"):
            display_status = "⚙️ <b>ꜱᴛᴀᴛᴜꜱ »</b> ᴘʀᴏᴄᴇꜱꜱɪɴɢ"
            footer_msg = "⚙️ <b>ᴏʀᴅᴇʀ ɪꜱ ᴘʀᴏᴄᴇꜱꜱɪɴɢ</b>"
        elif "progress" in status:
            display_status = "🚀 <b>ꜱᴛᴀᴛᴜꜱ »</b> ɪɴ ᴘʀᴏɢʀᴇꜱꜱ"
            footer_msg = "🚀 <b>ᴏʀᴅᴇʀ ɪꜱ ɢʀᴏᴡɪɴɢ ꜰᴀꜱᴛ</b>"
        elif status in ("canceled", "cancelled"):
            display_status = "❌ <b>ꜱᴛᴀᴛᴜꜱ »</b> ᴄᴀɴᴄᴇʟᴇᴅ"

            if not found_order.get("refunded", False):
                refund_amount = charge
                update_balance(user_id, refund_amount)
                log_wallet(user_id, refund_amount, "ʀᴇꜰᴜɴᴅ", order_id=order_id)

                found_order["refunded"] = True
                save_json(ORDERS_FILE, orders_db)

                footer_msg = f"💰 <b>₹{refund_amount:.2f} ʀᴇꜰᴜɴᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ ✨</b>"
            else:
                footer_msg = "❌ <b>ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟᴇᴅ</b>"
        elif status == "partial":
            display_status = "⚠️ <b>ꜱᴛᴀᴛᴜꜱ »</b> ᴘᴀʀᴛɪᴀʟ"
            footer_msg = "⚠️ <b>ᴏʀᴅᴇʀ ᴘᴀʀᴛɪᴀʟʟʏ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>"
        else:
            display_status = f"⏳ <b>ꜱᴛᴀᴛᴜꜱ »</b> {status.upper()}"
            footer_msg = "⏳ <b>ᴏʀᴅᴇʀ ɪꜱ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ</b>"

        status_msg = (
            "📊 <b>ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ</b>\n\n"
            f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
            f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(service_name)}\n"
            f"🔗 <b>ʟɪɴᴋ »</b> {html.escape(link)}\n"
            f"🔢 <b>Qᴜᴀɴᴛɪᴛʏ »</b> {quantity}\n"
            f"💸 <b>ᴄʜᴀʀɢᴇ »</b> ₹{charge:.2f}\n"
            f"{display_status}\n"
            f"📅 <b>ᴅᴀᴛᴇ »</b> {date}\n"
            f"📈 <b>ꜱᴛᴀʀᴛ ᴄᴏᴜɴᴛ »</b> {start_count}\n"
            f"🔄 <b>ʀᴇᴍᴀɪɴꜱ »</b> {remains_raw}\n"
            f"📉 <b>ᴄᴏᴍᴘʟᴇᴛᴇᴅ »</b> {completed_text}\n"
            f"📊 <b>ᴘʀᴏɢʀᴇꜱꜱ »</b> {progress_text}\n\n"
            f"{footer_msg}\n\n"
            "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔄 ʀᴇꜰɪʟʟ", callback_data=f"refill_order_{order_id}"),
            types.InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data=f"cancel_order_{order_id}"),
            types.InlineKeyboardButton("🔁 ʀᴇᴏʀᴅᴇʀ", callback_data=f"reorder_{order_id}")
        )

        bot.send_message(user_id, status_msg, parse_mode="HTML", reply_markup=markup)

    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>Order Status Error</b>\n<code>{e}</code>", parse_mode="HTML")
        bot.send_message(user_id, "❌ ꜱᴇʀᴠᴇʀ ᴄᴏɴɴᴇᴄᴛɪᴏɴ ɪꜱꜱᴜᴇ! ᴛʀʏ ᴀɢᴀɪɴ.")

def process_reorder(user_id, order_id):
    orders_db = load_json(ORDERS_FILE)
    order_id = str(order_id).strip()

    for order in orders_db.get(str(user_id), []):
        saved_id = str(order.get("order_id", "")).strip()
        if saved_id == order_id:
            service_id = str(order.get("srv_id", "")).strip()
            link = str(order.get("link", "")).strip()
            qty = int(order.get("qty", 0) or 0)
            if not service_id or not link or qty <= 0:
                start_order_flow_for_reorder(user_id, service_id)
                return
            s_info = find_service(service_id)
            if not s_info:
                bot.send_message(user_id, "❌ <b>ꜱᴇʀᴠɪᴄᴇ ᴀʙ ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴀʜɪ ʜᴀɪ.</b>", parse_mode="HTML")
                return
            selling_price = get_selling_price_for_user(service_id, user_id) or (s_info[1] if len(s_info) > 1 else 0)
            total_cost = round((qty / 1000) * float(selling_price), 2)
            user_orders[user_id] = {"service_id": service_id, "link": link, "quantity": qty, "selling_price": float(selling_price), "total_cost": total_cost}
            bot.send_message(user_id, "🔁 <b>Qᴜɪᴄᴋ ʀᴇᴏʀᴅᴇʀ ʀᴇᴀᴅʏ</b>\n\nᴘᴜʀᴀɴᴀ ʟɪɴᴋ ᴀᴜʀ Qᴜᴀɴᴛɪᴛʏ ᴀᴜᴛᴏ ꜰɪʟʟ ᴋɪʏᴀ ɢᴀʏᴀ.", parse_mode="HTML")
            send_order_confirm_message(user_id)
            return

    bot.send_message(
        user_id,
        f"❌ <b>ᴏʀᴅᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>\n\n🆔 <code>{order_id}</code>",
        parse_mode="HTML"
    )


def find_user_order(user_id, order_id):
    orders_db = load_json(ORDERS_FILE)
    user_history = orders_db.get(str(user_id), [])

    for order in user_history:
        if str(order.get("order_id")) == str(order_id):
            return order

    return None


def update_saved_order(user_id, order_id, updates):
    """orders.json me kisi order ke fields safe way me update karta hai."""
    orders_db = load_json(ORDERS_FILE)
    uid = str(user_id)
    changed = False

    for order in orders_db.get(uid, []):
        if str(order.get("order_id")) == str(order_id):
            order.update(updates)
            changed = True
            break

    if changed:
        save_json(ORDERS_FILE, orders_db)

    return changed


def init_order_flags(order):
    """Purane aur naye orders ke liye notification flags default set karta hai."""
    defaults = {
        "status": order.get("status", "processing"),
        "completed_notified": False,
        "cancelled_notified": False,
        "partial_notified": False,
        "refill_notified": False,
        "cancel_request_notified": False,
        "refunded": order.get("refunded", False),
    }

    changed = False
    for key, value in defaults.items():
        if key not in order:
            order[key] = value
            changed = True

    return changed


def get_panel_order_status(order_id):
    """Panel se live order status fetch karta hai."""
    try:
        return requests.post(
            SMM_API_URL,
            data={"key": SMM_API_KEY, "action": "status", "order": order_id},
            timeout=15
        ).json()
    except Exception as e:
        print("Auto order status error:", order_id, e)
        return {}


def get_panel_refill_status(refill_id):
    """Panel se refill status fetch karta hai, agar panel support kare."""
    if not refill_id:
        return {}

    try:
        return requests.post(
            SMM_API_URL,
            data={"key": SMM_API_KEY, "action": "refill_status", "refill": refill_id},
            timeout=15
        ).json()
    except Exception as e:
        print("Auto refill status error:", refill_id, e)
        return {}


def send_auto_completed_notification(user_id, order_id, service_id, service_name):
    bot.send_message(
        int(user_id),
        "✅ <b>ᴏʀᴅᴇʀ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
        f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
        f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(service_name)}\n\n"
        "🎉 <b>ʏᴏᴜʀ ᴏʀᴅᴇʀ ʜᴀꜱ ʙᴇᴇɴ ᴅᴇʟɪᴠᴇʀᴇᴅ.</b>\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
        parse_mode="HTML"
    )


def send_auto_cancelled_notification(user_id, order_id, service_id, service_name, refund_amount):
    bot.send_message(
        int(user_id),
        "❌ <b>ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟʟᴇᴅ!</b>\n\n"
        f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
        f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(service_name)}\n\n"
        f"💰 <b>₹{refund_amount:.2f} ʀᴇꜰᴜɴᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ.</b>\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
        parse_mode="HTML"
    )


def send_auto_partial_notification(user_id, order_id, service_id, service_name, remains):
    bot.send_message(
        int(user_id),
        "⚠️ <b>ᴏʀᴅᴇʀ ᴘᴀʀᴛɪᴀʟ!</b>\n\n"
        f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
        f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(service_name)}\n"
        f"🔄 <b>ʀᴇᴍᴀɪɴꜱ »</b> {remains}\n\n"
        "📌 <b>ᴘʟᴇᴀꜱᴇ ᴄʜᴇᴄᴋ ᴏʀᴅᴇʀ ꜱᴛᴀᴛᴜꜱ.</b>\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
        parse_mode="HTML"
    )


def send_refill_completed_notification(user_id, order_id, service_id, service_name):
    bot.send_message(
        int(user_id),
        "🔄 <b>ʀᴇꜰɪʟʟ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
        f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
        f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(service_name)}\n\n"
        "✅ <b>ʏᴏᴜʀ ʀᴇꜰɪʟʟ ʜᴀꜱ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴄᴏᴍᴘʟᴇᴛᴇᴅ.</b>\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
        parse_mode="HTML"
    )


def send_cancel_request_completed_notification(user_id, order_id, service_id, service_name):
    bot.send_message(
        int(user_id),
        "❌ <b>ᴄᴀɴᴄᴇʟ ʀᴇQᴜᴇꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
        f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
        f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(service_name)}\n\n"
        "✅ <b>ʏᴏᴜʀ ᴄᴀɴᴄᴇʟ ʀᴇQᴜᴇꜱᴛ ʜᴀꜱ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴘʀᴏᴄᴇꜱꜱᴇᴅ.</b>\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
        parse_mode="HTML"
    )


def check_auto_order_notifications():
    """orders.json ke pending orders ko auto check karke notifications bhejta hai."""
    orders_db = load_json(ORDERS_FILE)
    changed = False

    for uid, orders in list(orders_db.items()):
        if not isinstance(orders, list):
            continue

        for order in orders:
            if not isinstance(order, dict):
                continue

            if init_order_flags(order):
                changed = True

            order_id = str(order.get("order_id", "")).strip()
            if not order_id:
                continue

            service_id = str(order.get("srv_id", ""))
            service_name = get_service_name(service_id)
            current_status = str(order.get("status", "processing")).lower()

            # Refill completion check, agar refill id saved hai.
            refill_id = order.get("refill_id")
            if order.get("refill_requested") and not order.get("refill_notified") and refill_id:
                refill_response = get_panel_refill_status(refill_id)
                refill_status = str(refill_response.get("status", "")).lower()
                if refill_status in ("completed", "complete", "success", "refilled"):
                    try:
                        send_refill_completed_notification(uid, order_id, service_id, service_name)
                        order["refill_notified"] = True
                        changed = True
                    except Exception as e:
                        print("Refill notify error:", uid, order_id, e)

            # Final order status already notified ho gaya to panel hit skip.
            if current_status in ("completed", "cancelled", "canceled", "partial"):
                if order.get("completed_notified") or order.get("cancelled_notified") or order.get("partial_notified"):
                    continue

            response = get_panel_order_status(order_id)
            if "status" not in response:
                continue

            status = str(response.get("status", "")).lower()
            remains = response.get("remains", "0")
            order["status"] = status
            changed = True

            if status == "completed":
                sent_refill_completed = False

                if order.get("refill_requested") and not order.get("refill_notified") and not refill_id:
                    try:
                        send_refill_completed_notification(uid, order_id, service_id, service_name)
                        order["refill_notified"] = True
                        sent_refill_completed = True
                        changed = True
                    except Exception as e:
                        print("Refill notify error:", uid, order_id, e)

                if not sent_refill_completed and not order.get("completed_notified"):
                    try:
                        send_auto_completed_notification(uid, order_id, service_id, service_name)
                        order["completed_notified"] = True
                        order["notified"] = True
                        changed = True
                    except Exception as e:
                        print("Completed notify error:", uid, order_id, e)

            elif status in ("canceled", "cancelled"):
                refund_amount = float(order.get("charge", 0) or 0)

                if not order.get("refunded") and refund_amount > 0:
                    update_balance(uid, refund_amount)
                    log_wallet(uid, refund_amount, "ʀᴇꜰᴜɴᴅ", order_id=order_id, service_id=service_id)
                    order["refunded"] = True
                    changed = True

                if order.get("cancel_requested") and not order.get("cancel_request_notified"):
                    try:
                        send_cancel_request_completed_notification(uid, order_id, service_id, service_name)
                        order["cancel_request_notified"] = True
                        changed = True
                    except Exception as e:
                        print("Cancel request notify error:", uid, order_id, e)

                if not order.get("cancelled_notified"):
                    try:
                        send_auto_cancelled_notification(uid, order_id, service_id, service_name, refund_amount)
                        order["cancelled_notified"] = True
                        order["notified"] = True
                        changed = True
                    except Exception as e:
                        print("Cancelled notify error:", uid, order_id, e)

            elif status == "partial":
                if not order.get("partial_notified"):
                    try:
                        send_auto_partial_notification(uid, order_id, service_id, service_name, remains)
                        order["partial_notified"] = True
                        order["notified"] = True
                        changed = True
                    except Exception as e:
                        print("Partial notify error:", uid, order_id, e)

    if changed:
        save_json(ORDERS_FILE, orders_db)


def auto_order_notification_checker():
    while True:
        try:
            check_auto_order_notifications()
        except Exception as e:
            print("Auto notification checker error:", e)
        time.sleep(300)

def process_cancel_order(message):
    user_id = message.chat.id

    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return

    order_id = message.text.strip()

    if not order_id.isdigit():
        bot.send_message(user_id, "❌ ɢᴀʟᴀᴛ ᴏʀᴅᴇʀ ɪᴅ.")
        return

    order = find_user_order(user_id, order_id)

    if not order:
        bot.send_message(user_id, "❌ <b>ʏᴇ ᴏʀᴅᴇʀ ᴀᴀᴘᴋᴇ ᴀᴄᴄᴏᴜɴᴛ ᴍᴇ ɴᴀʜɪ ᴍɪʟᴀ.</b>", parse_mode="HTML")
        return

    service_id = str(order.get("srv_id"))
    s_info = find_service(service_id)
    service_name = s_info[0] if s_info else "UNKNOWN SERVICE"

    try:
        response = requests.post(
            SMM_API_URL,
            data={
                "key": SMM_API_KEY,
                "action": "cancel",
                "order": order_id
            },
            timeout=15
        ).json()

        status = str(response.get("status", "")).lower()
        error = str(response.get("error", response.get("message", "")))

        if status == "success":
            update_saved_order(user_id, order_id, {
                "cancel_requested": True,
                "cancel_request_date": datetime.now().strftime("%d-%m-%Y %I:%M %p")
            })
            bot.send_message(
                user_id,
                f"✅ <b>ᴄᴀɴᴄᴇʟ ʀᴇQᴜᴇꜱᴛ ꜱᴇɴᴛ</b>\n\n"
                f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
                f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
                f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ »</b> {html.escape(service_name)}\n\n"
                f"❌ <b>ꜱᴛᴀᴛᴜꜱ »</b> ᴄᴀɴᴄᴇʟ ʀᴇQᴜᴇꜱᴛᴇᴅ\n\n"
                f"🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
                parse_mode="HTML"
            )
        else:
            bot.send_message(
                user_id,
                f"❌ <b>ᴄᴀɴᴄᴇʟ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ</b>\n\n"
                f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
                f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ »</b> {html.escape(service_name)}\n\n"
                f"⚠️ <b>ᴛʜɪꜱ ꜱᴇʀᴠɪᴄᴇ ᴅᴏᴇꜱ ɴᴏᴛ ꜱᴜᴘᴘᴏʀᴛ ᴄᴀɴᴄᴇʟ.</b>\n"
                f"{html.escape(error)}\n\n"
                f"🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
                parse_mode="HTML"
            )

    except Exception as e:
        bot.send_message(user_id, f"❌ <b>ᴄᴀɴᴄᴇʟ ᴇʀʀᴏʀ:</b> <code>{e}</code>", parse_mode="HTML")


def process_refill_order(message):
    user_id = message.chat.id

    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return

    order_id = message.text.strip()

    if not order_id.isdigit():
        bot.send_message(user_id, "❌ ɢᴀʟᴀᴛ ᴏʀᴅᴇʀ ɪᴅ.")
        return

    order = find_user_order(user_id, order_id)

    if not order:
        bot.send_message(user_id, "❌ <b>ʏᴇ ᴏʀᴅᴇʀ ᴀᴀᴘᴋᴇ ᴀᴄᴄᴏᴜɴᴛ ᴍᴇ ɴᴀʜɪ ᴍɪʟᴀ.</b>", parse_mode="HTML")
        return

    service_id = str(order.get("srv_id"))
    s_info = find_service(service_id)
    service_name = s_info[0] if s_info else "UNKNOWN SERVICE"

    try:
        response = requests.post(
            SMM_API_URL,
            data={
                "key": SMM_API_KEY,
                "action": "refill",
                "order": order_id
            },
            timeout=15
        ).json()

        status = str(response.get("status", "")).lower()
        error = str(response.get("error", response.get("message", "")))

        if status == "success":
            update_saved_order(user_id, order_id, {
                "refill_requested": True,
                "refill_id": response.get("refill"),
                "refill_request_date": datetime.now().strftime("%d-%m-%Y %I:%M %p")
            })
            bot.send_message(
                user_id,
                f"✅ <b>ʀᴇꜰɪʟʟ ʀᴇQᴜᴇꜱᴛ ꜱᴇɴᴛ</b>\n\n"
                f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order_id}</code>\n"
                f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
                f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ »</b> {html.escape(service_name)}\n\n"
                f"♻️ <b>ꜱᴛᴀᴛᴜꜱ »</b> ʀᴇQᴜᴇꜱᴛᴇᴅ\n\n"
                f"🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
                parse_mode="HTML"
            )
        else:
            bot.send_message(
                user_id,
                f"❌ <b>ʀᴇꜰɪʟʟ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ</b>\n\n"
                f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n"
                f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ »</b> {html.escape(service_name)}\n\n"
                f"⚠️ <b>ᴛʜɪꜱ ꜱᴇʀᴠɪᴄᴇ ᴅᴏᴇꜱ ɴᴏᴛ ꜱᴜᴘᴘᴏʀᴛ ʀᴇꜰɪʟʟ.</b>\n"
                f"{html.escape(error)}\n\n"
                f"🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
                parse_mode="HTML"
            )

    except Exception as e:
        bot.send_message(user_id, f"❌ <b>ʀᴇꜰɪʟʟ ᴇʀʀᴏʀ:</b> <code>{e}</code>", parse_mode="HTML")

# --- FUND WORKFLOWS ---
def process_fund_amount(message):
    user_id = message.chat.id
    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            bot.send_message(user_id, "❌ ᴀᴍᴏᴜɴᴛ 0 ꜱᴇ ᴢyᴀᴅᴀ ʜᴏɴᴀ ᴄʜᴀʜɪyᴇ.")
            return
        user_funds[user_id] = {"amount": amount}
        msg = bot.send_message(user_id, "<b>🧾 <b><b>📸 ᴘᴀʏᴍᴇɴᴛ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ ʏᴀ ᴜᴛʀ ɪᴅ ꜱᴇɴᴅ ᴋᴀʀᴇɪɴ »</b></b></b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_fund_utr)
    except:
        bot.send_message(user_id, "❌ ɢᴀʟᴀᴛ ᴀᴍᴏᴜnt! ᴋʀɪᴘʏᴀ ꜱɪʀꜰ ɴᴜᴍʙᴇʀ ᴇɴᴛᴇʀ ᴋᴀʀᴇɪɴ.")

def process_fund_utr(message):
    user_id = message.chat.id
    if message.content_type == "photo":
        amount = user_funds[user_id]["amount"]

        caption = (
        f"📥 ɴᴇᴡ ꜰᴜɴᴅ ʀᴇQᴜᴇꜱᴛ\n\n"
        f"👤 ᴜꜱᴇʀ ɪᴅ: {user_id}\n"
        f"💰 ᴀᴍᴏᴜɴᴛ: ₹{amount}\n\n"
        f"📸 ᴘᴀʏᴍᴇɴᴛ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ ᴀᴛᴛᴀᴄʜᴇᴅ"
        )
 
        request_id = create_fund_request(user_id, amount, has_photo=True)
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ ᴀᴘᴘʀᴏᴠᴇ", callback_data=f"fund_approve_{request_id}"),
            types.InlineKeyboardButton("❌ ʀᴇᴊᴇᴄᴛ", callback_data=f"fund_reject_{request_id}")
        )
        bot.send_photo(
    ADMIN_ID,
    message.photo[-1].file_id,
    caption=caption
)

        bot.send_message(
   ADMIN_ID,
    "✅ ᴀᴘᴘʀᴏᴠᴇ / ❌ ʀᴇᴊᴇᴄᴛ",
    reply_markup=admin_markup
)

        bot.send_message(
        user_id,
        "⏳ ᴀᴀᴘᴋɪ ʀᴇQᴜᴇꜱᴛ ᴀᴅᴍɪɴ ᴋᴏ ʙʜᴇᴊ ᴅɪ ɢᴀʏɪ ʜᴀɪ!\n"
        "💰 ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴋᴇ ʙᴀᴀᴅ ʙᴀʟᴀɴᴄᴇ ᴀᴅᴅ ʜᴏ ᴊᴀʏᴇɢᴀ."
        )

        user_funds.pop(user_id, None)
        return
    if message.text in MENU_BUTTONS:
        user_funds.pop(user_id, None)
        handle_menu_redirection(message)
        return
    utr = message.text
    if user_id not in user_funds: return
    amount = user_funds[user_id]["amount"]
    
    bot.send_message(user_id, "<b>⏳ <b><b>ᴀᴀᴘᴋɪ ʀᴇqᴜᴇꜱᴛ ᴀᴅᴍɪɴ ᴋᴏ ʙʜᴇᴊ ᴅɪ ɢᴀyɪ ʜᴀɪ!</b>\nᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴋᴇ ʙᴀᴀᴅ ʙᴀʟᴀɴᴄᴇ ᴀᴅᴅ ʜᴏ ᴊᴀyᴇɢᴀ.</b></b>", parse_mode="HTML")
    
    request_id = create_fund_request(user_id, amount, utr=utr, has_photo=False)
    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    admin_markup.add(
        types.InlineKeyboardButton("✅ ᴀᴘᴘʀᴏᴠᴇ", callback_data=f"fund_approve_{request_id}"),
        types.InlineKeyboardButton("❌ ʀᴇᴊᴇᴄᴛ", callback_data=f"fund_reject_{request_id}")
    )

    admin_msg = (
        "<b>📥 ɴᴇᴡ ꜰᴜɴᴅ ʀᴇqᴜᴇꜱᴛ</b>\n\n"
        f"<b>👤 ᴜꜱᴇʀ ɪᴅ:</b> <code>{user_id}</code>\n"
        f"<b>💰 ᴀᴍᴏᴜɴᴛ:</b> ₹{amount}\n"
        f"<b>🧾 ᴜᴛʀ ɪᴅ:</b> <code>{utr}</code>\n\n"
        "ᴀᴘɴᴇ ʙᴀɴᴋ ᴍᴇ ᴄʜᴇᴄᴋ ᴋᴀʀᴋᴇ ᴀᴄᴛɪᴏɴ ʟɪᴊɪyᴇ 👇"
    )
    try:
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML", reply_markup=admin_markup)
    except:
        print("Error sending message to Admin.")
    user_funds.pop(user_id, None)

# --- ADMIN PANEL LOGIC HANDLERS ---
def process_admin_broadcast(message):
    if message.chat.id != ADMIN_ID:
        return

    if message.text in MENU_BUTTONS:
        return

    import time
    from telebot.apihelper import ApiTelegramException

    db = load_json(DB_FILE)

    success = 0
    failed = 0
    failed_users = []

    def mark_inactive(uid):
        uid_key = str(uid)

        if uid_key in db and isinstance(db[uid_key], dict):
            db[uid_key]["active"] = False

    def get_error_reason(error):
        error_text = str(error).lower()

        if "bot was blocked" in error_text:
            return "ʙᴏᴛ ʙʟᴏᴄᴋᴇᴅ", True

        if "chat not found" in error_text:
            return "ᴄʜᴀᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ", True

        if "user is deactivated" in error_text:
            return "ᴜꜱᴇʀ ᴅᴇᴀᴄᴛɪᴠᴀᴛᴇᴅ", True

        if "too many requests" in error_text:
            return "ʀᴀᴛᴇ ʟɪᴍɪᴛ", False

        if "forbidden" in error_text:
            return "ꜰᴏʀʙɪᴅᴅᴇɴ", True

        return "ᴜɴᴋɴᴏᴡɴ ᴇʀʀᴏʀ", False

    for uid, user_data in db.items():
        try:
            user_id = int(uid)

            if isinstance(user_data, dict):
                if not user_data.get("active", True):
                    continue

            if message.content_type == "photo":
                bot.send_photo(
                    user_id,
                    message.photo[-1].file_id,
                    caption=format_relay_text_html(message.caption or ""),
                    parse_mode="HTML"
                )

            else:
                bot.send_message(
                    user_id,
                    format_relay_text_html(message.text or ""),
                    parse_mode="HTML"
                )

            success += 1

        except ApiTelegramException as error:
            failed += 1

            reason, should_disable = get_error_reason(error)

            if should_disable:
                mark_inactive(uid)

            failed_users.append(
                f"▫️ <code>{uid}</code> — {reason}"
            )

            if reason == "ʀᴀᴛᴇ ʟɪᴍɪᴛ":
                time.sleep(2)

        except Exception as error:
            failed += 1

            failed_users.append(
                f"▫️ <code>{uid}</code> — ᴜɴᴋɴᴏᴡɴ ᴇʀʀᴏʀ"
            )

        time.sleep(0.05)

    save_json(DB_FILE, db)

    if message.content_type == "photo":
        report = (
            "📢 <b>ᴘʜᴏᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            f"✅ ꜱᴜᴄᴄᴇꜱꜱ: {success}\n"
            f"❌ ꜰᴀɪʟᴇᴅ: {failed}"
        )
    else:
        report = (
            "📢 <b>ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            f"✅ ꜱᴜᴄᴄᴇꜱꜱ: {success}\n"
            f"❌ ꜰᴀɪʟᴇᴅ: {failed}"
        )

    if failed_users:
        report += "\n\n📋 <b>ꜰᴀɪʟᴇᴅ ᴅᴇᴛᴀɪʟꜱ:</b>\n"
        report += "\n".join(failed_users[:30])

        if len(failed_users) > 30:
            report += (
                f"\n\n➕ ᴀɴᴅ {len(failed_users) - 30} ᴍᴏʀᴇ"
            )

    bot.send_message(
        ADMIN_ID,
        report,
        parse_mode="HTML"
    )      


# --- FINAL AUTO / ADMIN UTILITY FEATURES ---
REMOVED_SERVICES_FILE = "recent_removed_services.json"


def _json_file_names_for_backup():
    try:
        names = []
        for x in os.listdir(_base_dir()):
            if x.endswith('.json'):
                names.append(x)
        return sorted(set(names))
    except Exception:
        return []


def backup_menu_keyboard():
    return _admin_flow_keyboard([
        "📦 ʙᴀᴄᴋᴜᴘ ᴢɪᴘ",
        "🐍 ʙᴀᴄᴋᴜᴘ ʙᴏᴛ.ᴘʏ",
        "📄 ʙᴀᴄᴋᴜᴘ ᴊꜱᴏɴ",
        "♻️ ʀᴇꜱᴛᴏʀᴇ ʟᴀꜱᴛ ʙᴀᴄᴋᴜᴘ",
    ], row_width=1)


def backup_json_keyboard():
    return _admin_flow_keyboard(_json_file_names_for_backup(), row_width=2)


def show_backup_menu():
    bot.send_message(
        ADMIN_ID,
        "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ʙᴀᴄᴋᴜᴘ</b>",
        parse_mode="HTML",
        reply_markup=backup_menu_keyboard()
    )


def send_botpy_backup():
    path = os.path.join(_base_dir(), "bot.py")
    if not os.path.exists(path):
        bot.send_message(ADMIN_ID, "❌ <b>bot.py ɴᴏᴛ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return
    with open(path, "rb") as f:
        bot.send_document(ADMIN_ID, f, caption="🐍 <b>ʙᴏᴛ.ᴘʏ ʙᴀᴄᴋᴜᴘ</b>", parse_mode="HTML")


def start_backup_json_select():
    admin_state[ADMIN_ID] = {"backup_json_select": True}
    bot.send_message(
        ADMIN_ID,
        "📄 <b>ʙᴀᴄᴋᴜᴘ ᴊꜱᴏɴ</b>\n\n📌 <b>ᴊɪꜱ ᴊꜱᴏɴ ᴋᴀ ʙᴀᴄᴋᴜᴘ ᴄʜᴀʜɪʏᴇ ᴜꜱᴇ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ.</b>",
        parse_mode="HTML",
        reply_markup=backup_json_keyboard()
    )


def send_json_backup(filename):
    filename = _safe_basename(str(filename))
    if not filename.endswith(".json"):
        bot.send_message(ADMIN_ID, "❌ <b>ᴏɴʟʏ ᴊꜱᴏɴ ꜰɪʟᴇ ᴀʟʟᴏᴡᴇᴅ.</b>", parse_mode="HTML")
        return
    path = os.path.join(_base_dir(), filename)
    if not os.path.exists(path):
        bot.send_message(ADMIN_ID, f"❌ <b>{html.escape(filename)} ɴᴏᴛ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return
    with open(path, "rb") as f:
        bot.send_document(ADMIN_ID, f, caption=f"📄 <b>{html.escape(filename)} ʙᴀᴄᴋᴜᴘ</b>", parse_mode="HTML")


def _recent_removed_load():
    data = load_json(REMOVED_SERVICES_FILE)
    return data if isinstance(data, dict) else {}


def _recent_removed_save(data):
    save_json(REMOVED_SERVICES_FILE, data if isinstance(data, dict) else {})


def _recent_removed_add(sid, name="Unknown", subcat="", source="", row=None):
    data = _recent_removed_load()
    sid = str(sid).strip()
    data[sid] = {
        "sid": sid,
        "name": str(name or "Unknown"),
        "subcat": str(subcat or ""),
        "source": str(source or ""),
        "row": row,
        "time": datetime.now().strftime("%d-%m-%Y %I:%M %p"),
        "status": "removed"
    }
    # last 100 only
    items = list(data.items())[-100:]
    _recent_removed_save(dict(items))


def show_recent_removed_services():
    data = _recent_removed_load()
    rows = [r for r in data.values() if isinstance(r, dict)]
    if not rows:
        bot.send_message(ADMIN_ID, "🗑️ <b>ʀᴇᴄᴇɴᴛʟʏ ʀᴇᴍᴏᴠᴇᴅ ᴇᴍᴘᴛʏ</b>", parse_mode="HTML")
        return
    bot.send_message(ADMIN_ID, f"🗑️ <b>ʀᴇᴄᴇɴᴛʟʏ ʀᴇᴍᴏᴠᴇᴅ</b>\n\n📦 <b>ᴛᴏᴛᴀʟ »</b> {len(rows)}", parse_mode="HTML")
    for r in rows[-50:]:
        sid = str(r.get("sid", ""))
        mk = types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("♻️ ʀᴇꜱᴛᴏʀᴇ", callback_data=f"restore_removed_service_{sid}"))
        bot.send_message(
            ADMIN_ID,
            "🗑️ <b>ʀᴇᴍᴏᴠᴇᴅ ꜱᴇʀᴠɪᴄᴇ</b>\n\n"
            f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(sid)}</code>\n"
            f"📦 <b>ɴᴀᴍᴇ »</b> {html.escape(str(r.get('name','Unknown')))}\n"
            f"📁 <b>ᴄᴀᴛᴇɢᴏʀʏ »</b> {html.escape(str(r.get('subcat','')))}\n"
            f"📄 <b>ꜱᴏᴜʀᴄᴇ »</b> {html.escape(str(r.get('source','')))}\n"
            f"🕒 <b>ᴛɪᴍᴇ »</b> {html.escape(str(r.get('time','')))}",
            parse_mode="HTML",
            reply_markup=mk
        )


def restore_removed_service(sid):
    sid = str(sid).strip()
    data = _recent_removed_load()
    row = data.get(sid)
    if not row:
        bot.send_message(ADMIN_ID, f"❌ <b>ʀᴇᴍᴏᴠᴇᴅ ʀᴇᴄᴏʀᴅ ɴᴏᴛ ꜰᴏᴜɴᴅ:</b> <code>{html.escape(sid)}</code>", parse_mode="HTML")
        return
    subcat = row.get("subcat") or "other"
    source = row.get("source") or "added_services.json"
    saved = row.get("row")
    if source == "services.json":
        services_db = load_json(SERVICES_FILE)
        if not isinstance(services_db, dict): services_db = {}
        if not isinstance(services_db.get(subcat), dict): services_db[subcat] = {}
        if isinstance(saved, list):
            services_db[subcat][sid] = saved
        else:
            services_db[subcat][sid] = [row.get("name", "Unknown"), 0]
        save_json(SERVICES_FILE, services_db)
    else:
        added_db = load_json(ADDED_SERVICES_FILE)
        if not isinstance(added_db, dict): added_db = {}
        if isinstance(saved, dict):
            added_db[sid] = saved
        else:
            added_db[sid] = {"name": row.get("name", "Unknown"), "subcat": subcat, "price": 0, "date": datetime.now().strftime("%d-%m-%Y %I:%M %p")}
        save_json(ADDED_SERVICES_FILE, added_db)
    data.pop(sid, None)
    _recent_removed_save(data)
    bot.send_message(ADMIN_ID, f"♻️ <b>ꜱᴇʀᴠɪᴄᴇ ʀᴇꜱᴛᴏʀᴇᴅ</b>\n\n🆔 <code>{html.escape(sid)}</code>", parse_mode="HTML")


def _random_coupon_code(amount=None):
    import random, string
    suffix = str(int(float(amount))) if amount not in (None, "") else ""
    return "RHN" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5)) + suffix


def start_coupon_create(random_code=False):
    code = _random_coupon_code() if random_code else ""
    admin_state[ADMIN_ID] = {"coupon_create": True, "coupon_random": bool(random_code), "coupon_code": code}
    if random_code:
        msg = bot.send_message(ADMIN_ID, f"🎲 <b>ɢᴇɴᴇʀᴀᴛᴇᴅ ᴄᴏᴜᴘᴏɴ »</b> <code>{code}</code>\n\n💰 <b>ᴇɴᴛᴇʀ ᴀᴍᴏᴜɴᴛ:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_coupon_amount)
    else:
        msg = bot.send_message(ADMIN_ID, "🎫 <b>ᴇɴᴛᴇʀ ᴄᴏᴜᴘᴏɴ ᴄᴏᴅᴇ:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_coupon_code)


def process_coupon_code(message):
    if message.chat.id != ADMIN_ID: return
    code = (message.text or "").strip().upper()
    if not code:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴅᴇ</b>", parse_mode="HTML")
        return
    st = admin_state.get(ADMIN_ID, {})
    st["coupon_code"] = code
    admin_state[ADMIN_ID] = st
    msg = bot.send_message(ADMIN_ID, "💰 <b>ᴇɴᴛᴇʀ ᴄᴏᴜᴘᴏɴ ᴀᴍᴏᴜɴᴛ:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_coupon_amount)


def process_coupon_amount(message):
    if message.chat.id != ADMIN_ID: return
    try:
        amount = float((message.text or "").strip())
        if amount <= 0: raise ValueError
    except Exception:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ</b>", parse_mode="HTML")
        return
    st = admin_state.get(ADMIN_ID, {})
    st["coupon_amount"] = amount
    if st.get("coupon_random") and st.get("coupon_code", "").endswith("RHN"):
        st["coupon_code"] = _random_coupon_code(amount)
    admin_state[ADMIN_ID] = st
    msg = bot.send_message(ADMIN_ID, "👥 <b>ᴇɴᴛᴇʀ ᴍᴀx ᴜꜱᴇꜱ:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_coupon_uses)


def process_coupon_uses(message):
    if message.chat.id != ADMIN_ID: return
    try:
        uses = int((message.text or "").strip())
        if uses <= 0: raise ValueError
    except Exception:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴜꜱᴇꜱ</b>", parse_mode="HTML")
        return
    st = admin_state.get(ADMIN_ID, {})
    st["coupon_uses"] = uses
    admin_state[ADMIN_ID] = st
    msg = bot.send_message(ADMIN_ID, "📅 <b>ᴇɴᴛᴇʀ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ:</b>\n<code>DD-MM-YYYY</code> ᴏʀ <code>NO</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_coupon_expiry)


def process_coupon_expiry(message):
    if message.chat.id != ADMIN_ID: return
    expiry = (message.text or "").strip()
    if expiry.upper() in ["NO", "NONE", "N"]:
        expiry = ""
    st = admin_state.get(ADMIN_ID, {})
    st["coupon_expiry"] = expiry
    admin_state[ADMIN_ID] = st
    code = st.get("coupon_code")
    amount = float(st.get("coupon_amount", 0))
    uses = int(st.get("coupon_uses", 1))
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("✅ ᴄᴏɴꜰɪʀᴍ", callback_data="coupon_create_confirm"), types.InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="coupon_create_cancel"))
    bot.send_message(
        ADMIN_ID,
        "🎁 <b>ᴄᴏɴꜰɪʀᴍ ᴄᴏᴜᴘᴏɴ</b>\n\n"
        f"🎫 <b>ᴄᴏᴅᴇ »</b> <code>{html.escape(str(code))}</code>\n"
        f"💰 <b>ᴀᴍᴏᴜɴᴛ »</b> ₹{amount:.2f}\n"
        f"👥 <b>ᴍᴀx ᴜꜱᴇꜱ »</b> {uses}\n"
        f"📅 <b>ᴇxᴘɪʀʏ »</b> {html.escape(expiry or 'ɴᴏ ᴇxᴘɪʀʏ')}",
        parse_mode="HTML",
        reply_markup=mk
    )


def confirm_coupon_create():
    st = admin_state.get(ADMIN_ID, {})
    code = str(st.get("coupon_code", "")).strip().upper()
    amount = float(st.get("coupon_amount", 0) or 0)
    uses = int(st.get("coupon_uses", 1) or 1)
    expiry = str(st.get("coupon_expiry", "") or "")
    if not code or amount <= 0:
        bot.send_message(ADMIN_ID, "❌ <b>ᴄᴏᴜᴘᴏɴ ᴅᴀᴛᴀ ᴇxᴘɪʀᴇᴅ</b>", parse_mode="HTML")
        return
    coupons = load_json(COUPON_FILE)
    if not isinstance(coupons, dict): coupons = {}
    coupons[code] = {"amount": amount, "max_uses": uses, "used_by": [], "expiry": expiry, "created_at": datetime.now().strftime("%d-%m-%Y %I:%M %p")}
    save_json(COUPON_FILE, coupons)
    admin_state.pop(ADMIN_ID, None)
    bot.send_message(ADMIN_ID, f"✅ <b>ᴄᴏᴜᴘᴏɴ ᴄʀᴇᴀᴛᴇᴅ</b>\n\n🎫 <code>{html.escape(code)}</code>", parse_mode="HTML")


def start_coupon_delete():
    msg = bot.send_message(ADMIN_ID, "❌ <b>ᴇɴᴛᴇʀ ᴄᴏᴜᴘᴏɴ ᴄᴏᴅᴇ ᴛᴏ ᴅᴇʟᴇᴛᴇ:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_coupon_delete)


def process_coupon_delete(message):
    if message.chat.id != ADMIN_ID: return
    code = (message.text or "").strip().upper()
    coupons = load_json(COUPON_FILE)
    if not isinstance(coupons, dict): coupons = {}
    if code in coupons:
        coupons.pop(code, None)
        save_json(COUPON_FILE, coupons)
        bot.send_message(ADMIN_ID, f"✅ <b>ᴄᴏᴜᴘᴏɴ ᴅᴇʟᴇᴛᴇᴅ:</b> <code>{html.escape(code)}</code>", parse_mode="HTML")
    else:
        bot.send_message(ADMIN_ID, f"❌ <b>ᴄᴏᴜᴘᴏɴ ɴᴏᴛ ꜰᴏᴜɴᴅ:</b> <code>{html.escape(code)}</code>", parse_mode="HTML")



# ✅ Coupon Auto Expire

def _parse_coupon_expiry_date(value):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            pass
    return None


def is_coupon_expired(item):
    exp = _parse_coupon_expiry_date((item or {}).get("expiry", ""))
    if not exp:
        return False
    return datetime.now().date() > exp


def auto_expire_coupons_once(notify=True):
    coupons = load_json(COUPON_FILE)
    if not isinstance(coupons, dict) or not coupons:
        return []
    expired = []
    changed = False
    for code, item in list(coupons.items()):
        if is_coupon_expired(item):
            expired.append((code, item))
            coupons.pop(code, None)
            changed = True
    if changed:
        save_json(COUPON_FILE, coupons)
        if notify:
            try:
                msg = "🎁 <b>ᴄᴏᴜᴘᴏɴ ᴀᴜᴛᴏ ᴇxᴘɪʀᴇᴅ</b>\n\n"
                for code, item in expired[:30]:
                    msg += f"🎫 <code>{html.escape(str(code))}</code> » 📅 {html.escape(str(item.get('expiry','')))}\n"
                if len(expired) > 30:
                    msg += f"\n➕ <b>ᴍᴏʀᴇ:</b> {len(expired)-30}"
                bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
                try:
                    log_admin_action("coupon_auto_expire", f"expired={len(expired)}")
                except Exception:
                    pass
            except Exception as e:
                print("coupon expire notify error:", e)
    return expired


def auto_coupon_expire_checker(interval_seconds=3600):
    time.sleep(20)
    while True:
        try:
            auto_expire_coupons_once(notify=True)
        except Exception as e:
            print("auto coupon expire error:", e)
        time.sleep(interval_seconds)

def auto_ticket_close_checker(interval_seconds=3600):
    time.sleep(15)
    while True:
        try:
            tickets = load_json(TICKETS_FILE)
            if isinstance(tickets, dict):
                changed = False
                now = datetime.now()
                for tid, row in tickets.items():
                    if not isinstance(row, dict):
                        continue
                    status = str(row.get("status", "open")).lower()
                    if status in ["closed", "auto_closed", "answered"]:
                        continue
                    tstr = row.get("updated") or row.get("created") or ""
                    dt = None
                    for fmt in ["%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M", "%d-%m-%Y"]:
                        try:
                            dt = datetime.strptime(str(tstr), fmt); break
                        except Exception:
                            pass
                    if dt and (now - dt).total_seconds() >= 72 * 3600:
                        row["status"] = "auto_closed"
                        row["auto_closed_at"] = now.strftime("%d-%m-%Y %I:%M %p")
                        changed = True
                        try:
                            uid = int(row.get("user_id"))
                            bot.send_message(uid, f"🎫 <b>ᴛɪᴄᴋᴇᴛ ᴀᴜᴛᴏ ᴄʟᴏꜱᴇᴅ</b>\n\n🆔 <code>{html.escape(str(tid))}</code>", parse_mode="HTML")
                        except Exception:
                            pass
                if changed:
                    save_json(TICKETS_FILE, tickets)
                    bot.send_message(ADMIN_ID, "🎫 <b>ɪɴᴀᴄᴛɪᴠᴇ ᴛɪᴄᴋᴇᴛꜱ ᴀᴜᴛᴏ ᴄʟᴏꜱᴇᴅ</b>", parse_mode="HTML")
        except Exception as e:
            print("auto ticket close error:", e)
        time.sleep(interval_seconds)


def auto_vip_upgrade_checker(interval_seconds=3600):
    time.sleep(20)
    while True:
        try:
            users = load_json(DB_FILE)
            orders = load_json(ORDERS_FILE)
            if isinstance(users, dict) and isinstance(orders, dict):
                changed = False
                for uid, u in users.items():
                    if not isinstance(u, dict) or u.get("vip"):
                        continue
                    total_spent = 0.0
                    for o in orders.get(str(uid), []):
                        if isinstance(o, dict):
                            total_spent += float(o.get("charge", 0) or 0)
                    if total_spent >= 500:
                        u["vip"] = True
                        u["vip_auto_at"] = datetime.now().strftime("%d-%m-%Y %I:%M %p")
                        changed = True
                        try:
                            bot.send_message(int(uid), "👑 <b>ᴠɪᴘ ᴀᴜᴛᴏ ᴀᴄᴛɪᴠᴀᴛᴇᴅ!</b>\n\n🎉 <b>ᴀᴀᴘɴᴇ ₹500 ꜱᴘᴇɴᴅ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀ ʟɪʏᴀ.</b>", parse_mode="HTML")
                        except Exception:
                            pass
                        bot.send_message(ADMIN_ID, f"👑 <b>ᴠɪᴘ ᴀᴜᴛᴏ ᴜᴘɢʀᴀᴅᴇ</b>\n\n👤 <code>{html.escape(str(uid))}</code>\n💰 <b>ꜱᴘᴇɴᴛ »</b> ₹{total_spent:.2f}", parse_mode="HTML")
                if changed:
                    save_json(DB_FILE, users)
        except Exception as e:
            print("auto vip upgrade error:", e)
        time.sleep(interval_seconds)

# --- END FINAL AUTO / ADMIN UTILITY FEATURES ---



# --- EXTRA SAFETY / ACTIVITY FEATURES ---
def clear_all_pending_actions():
    try:
        save_json(PENDING_ACTIONS_FILE, {})
        bot.send_message(ADMIN_ID, "🧹 <b>ᴘᴇɴᴅɪɴɢ ᴀᴄᴛɪᴏɴꜱ ᴄʟᴇᴀʀᴇᴅ</b>", parse_mode="HTML")
        try:
            log_admin_action("clear_pending_actions", "all pending actions cleared")
        except Exception:
            pass
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>ᴄʟᴇᴀʀ ᴘᴇɴᴅɪɴɢ ᴇʀʀᴏʀ:</b> {html.escape(str(e))}", parse_mode="HTML")


def _latest_backup_zip_path():
    candidates = []
    try:
        for folder in [os.path.join(_base_dir(), "backups"), _base_dir()]:
            if not os.path.isdir(folder):
                continue
            for name in os.listdir(folder):
                if name.endswith(".zip") and ("backup" in name.lower() or "smm_bot" in name.lower()):
                    path = os.path.join(folder, name)
                    if os.path.isfile(path):
                        candidates.append(path)
    except Exception:
        pass
    if not candidates:
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))


def restore_latest_backup_zip():
    try:
        backup_path = _latest_backup_zip_path()
        if not backup_path:
            bot.send_message(ADMIN_ID, "❌ <b>ᴋᴏɪ ʙᴀᴄᴋᴜᴘ ᴢɪᴘ ɴᴀʜɪ ᴍɪʟᴀ.</b>", parse_mode="HTML")
            return
        with zipfile.ZipFile(backup_path, "r") as z:
            names = [os.path.basename(x) for x in z.namelist()]
            if "bot.py" not in names:
                bot.send_message(ADMIN_ID, "❌ <b>ʙᴀᴄᴋᴜᴘ ᴢɪᴘ ᴍᴇ bot.py ɴᴀʜɪ ᴍɪʟᴀ.</b>", parse_mode="HTML")
                return
            for member in z.namelist():
                base = os.path.basename(member)
                if not base or not (base == "bot.py" or base.endswith(".json")):
                    continue
                target = os.path.join(_base_dir(), base)
                with z.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        bot.send_message(
            ADMIN_ID,
            f"♻️ <b>ʟᴀꜱᴛ ʙᴀᴄᴋᴜᴘ ʀᴇꜱᴛᴏʀᴇᴅ</b>\n\n📦 <b>ꜰɪʟᴇ »</b> <code>{html.escape(os.path.basename(backup_path))}</code>\n\n🔄 <b>ʙᴏᴛ ᴀᴜᴛᴏ ʀᴇꜱᴛᴀʀᴛ ʜᴏ ʀᴀʜᴀ ʜᴀɪ...</b>",
            parse_mode="HTML"
        )
        try:
            log_admin_action("restore_backup", os.path.basename(backup_path))
        except Exception:
            pass
        try:
            _restart_bot_after_exchange(2)
        except Exception:
            pass
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>ʀᴇꜱᴛᴏʀᴇ ᴇʀʀᴏʀ:</b> {html.escape(str(e))}", parse_mode="HTML")
# --- END EXTRA SAFETY / ACTIVITY FEATURES ---

# --- CALLBACK ROUTER SYSTEM ---


# --- SMART ASSISTANT ---
def _service_category_label_by_id(sid):
    sid = str(sid)
    services_db = load_json(SERVICES_FILE)
    if isinstance(services_db, dict):
        for cat, items in services_db.items():
            if isinstance(items, dict) and sid in items:
                for platform, cfg in ADD_SERVICE_CATS.items():
                    if cat in cfg.get("subs", {}):
                        return f"{cfg.get('title', platform)} / {cfg['subs'].get(cat, cat)}"
                return str(cat)
    added = load_json(ADDED_SERVICES_FILE)
    if isinstance(added, dict) and sid in added:
        cat = added[sid].get("subcat", "")
        for platform, cfg in ADD_SERVICE_CATS.items():
            if cat in cfg.get("subs", {}):
                return f"{cfg.get('title', platform)} / {cfg['subs'].get(cat, cat)}"
        return str(cat or "added_services")
    return "ɴᴏᴛ ᴀᴅᴅᴇᴅ"


def _service_order_stats(sid):
    sid = str(sid)
    total_orders = 0
    total_sales = 0.0
    orders_db = load_json(ORDERS_FILE)
    if isinstance(orders_db, dict):
        for rows in orders_db.values():
            if isinstance(rows, list):
                for o in rows:
                    if str(o.get("srv_id", o.get("service_id", ""))) == sid:
                        total_orders += 1
                        try:
                            total_sales += float(o.get("charge", o.get("total_cost", 0)) or 0)
                        except Exception:
                            pass
    return total_orders, total_sales


def _is_service_pinned(sid):
    sid = str(sid)
    pins = load_json(PINNED_SERVICES_FILE)
    if isinstance(pins, dict):
        return sid in pins or sid in [str(x) for x in pins.values()]
    if isinstance(pins, list):
        return sid in [str(x) for x in pins]
    return False


def smart_assistant_keyboard(sid, in_bot=True, in_panel=False):
    mk = types.InlineKeyboardMarkup(row_width=2)
    sid = str(sid)
    if in_bot:
        mk.add(
            types.InlineKeyboardButton("🎯 ᴄʜᴀɴɢᴇ ᴍᴀʀɢɪɴ", callback_data=f"smart_margin_{sid}"),
            types.InlineKeyboardButton("🔁 ꜱʜɪꜰᴛ ꜱᴇʀᴠɪᴄᴇ", callback_data=f"smart_shift_{sid}")
        )
        mk.add(
            types.InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ", callback_data=f"smart_remove_{sid}"),
            types.InlineKeyboardButton("📌 ᴘɪɴ / ᴜɴᴘɪɴ", callback_data=f"smart_pin_{sid}")
        )
        mk.add(
            types.InlineKeyboardButton("📊 ᴘʀɪᴄᴇ ʜɪꜱᴛᴏʀʏ", callback_data=f"smart_price_history_{sid}"),
            types.InlineKeyboardButton("🩺 ꜱᴇʀᴠɪᴄᴇ ʜᴇᴀʟᴛʜ", callback_data=f"smart_health_{sid}")
        )
    elif in_panel:
        mk.add(types.InlineKeyboardButton("➕ ᴀᴅᴅ ꜱᴇʀᴠɪᴄᴇ", callback_data=f"autoadd_service_{sid}"))
    mk.add(types.InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin_cat_services"))
    return mk


def start_smart_assistant(message=None):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(types.KeyboardButton("⬅️ ʙᴀᴄᴋ"), types.KeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"))
    msg = bot.send_message(
        ADMIN_ID,
        "🤖 <b>ꜱᴍᴀʀᴛ ᴀꜱꜱɪꜱᴛᴀɴᴛ</b>\n\n🆔 <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    bot.register_next_step_handler(msg, process_smart_assistant_id)


def process_smart_assistant_id(message):
    if message.chat.id != ADMIN_ID:
        return
    text = str(message.text or "").strip()
    if text in ["⬅️ ʙᴀᴄᴋ", "⬅️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ"]:
        send_admin_category_message(ADMIN_ID, "📦 ꜱᴇʀᴠɪᴄᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ")
        return
    if text in ["🏠 ᴍᴇɴᴜ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"]:
        bot.send_message(ADMIN_ID, "🏠 <b>ᴍᴀɪɴ ᴍᴇɴᴜ</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(ADMIN_ID))
        return
    sid = text.split()[0] if text else ""
    if not sid or not sid.isdigit():
        msg = bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ꜱᴇʀᴠɪᴄᴇ ɪᴅ</b>\n\n🆔 <b>ᴇɴᴛᴇʀ ɴᴜᴍᴇʀɪᴄ ꜱᴇʀᴠɪᴄᴇ ɪᴅ</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_smart_assistant_id)
        return
    show_smart_service_panel(sid)


def show_smart_service_panel(sid):
    sid = str(sid).strip()
    info = find_service(sid)
    panel = find_panel_service(sid)
    in_bot = bool(info)
    in_panel = bool(panel)
    if info:
        name = str(info[0]) if isinstance(info, (list, tuple)) and info else "Unknown"
        bot_price = get_selling_price(sid)
    elif panel:
        name = str(panel.get("name", "Unknown"))
        bot_price = 0
    else:
        bot.send_message(ADMIN_ID, f"❌ <b>ꜱᴇʀᴠɪᴄᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ</b>\n\n🆔 <code>{html.escape(sid)}</code>", parse_mode="HTML")
        return
    panel_price = 0.0
    if panel:
        try:
            panel_price = float(panel.get("rate", 0) or 0)
        except Exception:
            panel_price = 0.0
    total_orders, total_sales = _service_order_stats(sid)
    status = "✅ ᴀᴄᴛɪᴠᴇ" if in_panel else "🚫 ᴘᴀɴᴇʟ ᴍᴇ ɴᴀʜɪ / ᴅɪꜱᴀʙʟᴇᴅ"
    added_status = "✅ ʏᴇꜱ" if in_bot else "❌ ɴᴏ"
    pinned = "✅ ʏᴇꜱ" if _is_service_pinned(sid) else "❌ ɴᴏ"
    msg = (
        "🤖 <b>ꜱᴍᴀʀᴛ ꜱᴇʀᴠɪᴄᴇ ᴘᴀɴᴇʟ</b>\n\n"
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(sid)}</code>\n"
        f"📦 <b>ɴᴀᴍᴇ »</b> {html.escape(name)}\n"
        f"📁 <b>ᴄᴀᴛᴇɢᴏʀʏ »</b> {_service_category_label_by_id(sid)}\n"
        f"📊 <b>ᴘᴀɴᴇʟ ᴘʀɪᴄᴇ »</b> ₹{panel_price:.4f}\n"
        f"💎 <b>ʙᴏᴛ ᴘʀɪᴄᴇ »</b> ₹{float(bot_price or 0):.4f}\n"
        f"🎯 <b>ᴍᴀʀɢɪɴ »</b> {get_service_multiplier(sid)}x\n"
        f"📦 <b>ᴛᴏᴛᴀʟ ᴏʀᴅᴇʀꜱ »</b> {total_orders}\n"
        f"💰 <b>ᴛᴏᴛᴀʟ ꜱᴀʟᴇ »</b> ₹{total_sales:.2f}\n"
        f"📌 <b>ᴘɪɴɴᴇᴅ »</b> {pinned}\n"
        f"📍 <b>ʙᴏᴛ ᴍᴇ ᴀᴅᴅᴇᴅ »</b> {added_status}\n"
        f"🔄 <b>ꜱᴛᴀᴛᴜꜱ »</b> {status}"
    )
    bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=smart_assistant_keyboard(sid, in_bot=in_bot, in_panel=in_panel))
# --- END SMART ASSISTANT ---



# --- EXTRA BONUS SYSTEM ---
def start_extra_bonus_flow(message=None):
    admin_state[ADMIN_ID] = {"extra_bonus_step": "amount"}
    bot.send_message(ADMIN_ID, "🎁 <b>ᴇxᴛʀᴀ ʙᴏɴᴜꜱ</b>\n\n💰 <b>ʙᴏɴᴜꜱ ᴀᴍᴏᴜɴᴛ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>", parse_mode="HTML")

def _process_extra_bonus_text(message):
    if message.chat.id != ADMIN_ID:
        return False
    st = admin_state.get(ADMIN_ID, {})
    step = st.get("extra_bonus_step")
    if not step:
        return False
    text = (message.text or "").strip()
    if text in ["⬅️ ʙᴀᴄᴋ", "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ", "🏠 ᴍᴇɴᴜ"]:
        admin_state.pop(ADMIN_ID, None)
        send_admin_panel_message(ADMIN_ID)
        return True
    if step == "amount":
        try:
            amount = float(text.replace("₹", "").strip())
            if amount <= 0:
                raise ValueError("amount must be positive")
        except Exception:
            bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b> ᴇxᴀᴍᴘʟᴇ: <code>10</code>", parse_mode="HTML")
            return True
        st["amount"] = amount
        st["extra_bonus_step"] = "reason"
        admin_state[ADMIN_ID] = st
        bot.send_message(ADMIN_ID, "📌 <b>ʙᴏɴᴜꜱ ᴋɪꜱ ʟɪʏᴇ?</b>\n\nᴇxᴀᴍᴘʟᴇ: <code>ᴇɪᴅ ʙᴏɴᴜꜱ</code> / <code>ʜᴏʟɪᴅᴀʏ ʙᴏɴᴜꜱ</code>", parse_mode="HTML")
        return True
    if step == "reason":
        if not text:
            bot.send_message(ADMIN_ID, "❌ <b>ʀᴇᴀꜱᴏɴ ᴇᴍᴘᴛʏ ɴᴀʜɪ ʜᴏ ꜱᴀᴋᴛᴀ.</b>", parse_mode="HTML")
            return True
        st["reason"] = text[:120]
        st["extra_bonus_step"] = "ask_greeting"
        admin_state[ADMIN_ID] = st
        bot.send_message(ADMIN_ID, "💬 <b>ʙᴀᴅʜᴀʏɪ / ɢʀᴇᴇᴛɪɴɢ ᴛᴇxᴛ ʙʜᴇᴊɴᴀ ʜᴀɪ?</b>\n\n<code>yes</code> ʏᴀ <code>no</code> ʟɪᴋʜᴏ.", parse_mode="HTML")
        return True
    if step == "ask_greeting":
        low = text.lower()
        if low in ["no", "n", "nah", "nahi", "nhi"]:
            st["greeting"] = ""
            _confirm_extra_bonus(st)
            return True
        if low in ["yes", "y", "ha", "haan", "h"]:
            st["extra_bonus_step"] = "greeting"
            admin_state[ADMIN_ID] = st
            bot.send_message(ADMIN_ID, "✍️ <b>ɢʀᴇᴇᴛɪɴɢ / ʙᴀᴅʜᴀʏɪ ᴛᴇxᴛ ʙʜᴇᴊᴏ:</b>", parse_mode="HTML")
            return True
        bot.send_message(ADMIN_ID, "❌ <b>ꜱɪʀꜰ yes ʏᴀ no ʟɪᴋʜᴏ.</b>", parse_mode="HTML")
        return True
    if step == "greeting":
        st["greeting"] = text[:800]
        _confirm_extra_bonus(st)
        return True
    return False

def _confirm_extra_bonus(st):
    admin_state[ADMIN_ID] = {"extra_bonus_step": "confirm", **st}
    greeting = st.get("greeting", "")
    msg = (
        "🎁 <b>ᴇxᴛʀᴀ ʙᴏɴᴜꜱ ᴄᴏɴꜰɪʀᴍ?</b>\n\n"
        f"💰 <b>ᴀᴍᴏᴜɴᴛ »</b> ₹{float(st.get('amount', 0)):.2f}\n"
        f"📌 <b>ʀᴇᴀꜱᴏɴ »</b> {html.escape(str(st.get('reason', '')))}\n"
    )
    if greeting:
        msg += f"💬 <b>ᴍᴇꜱꜱᴀɢᴇ »</b> {html.escape(str(greeting))}\n"
    msg += "\n⚠️ <b>ʏᴇ ʙᴏɴᴜꜱ ꜱᴀʀᴇ ᴜꜱᴇʀꜱ ᴋᴏ ᴄʀᴇᴅɪᴛ ʜᴏɢᴀ.</b>"
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("✅ ᴄᴏɴꜰɪʀᴍ", callback_data="extra_bonus_confirm"))
    mk.add(types.InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="extra_bonus_cancel"))
    bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=mk)

def apply_extra_bonus_to_all():
    st = admin_state.get(ADMIN_ID, {})
    amount = float(st.get("amount", 0) or 0)
    reason = str(st.get("reason", "ᴇxᴛʀᴀ ʙᴏɴᴜꜱ"))
    greeting = str(st.get("greeting", ""))
    if amount <= 0:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ʙᴏɴᴜꜱ ᴀᴍᴏᴜɴᴛ.</b>", parse_mode="HTML")
        admin_state.pop(ADMIN_ID, None)
        return
    db = load_json(DB_FILE)
    success = failed = 0
    for uid in list(db.keys()):
        try:
            update_balance(uid, amount)
            log_wallet(uid, amount, f"ᴇxᴛʀᴀ ʙᴏɴᴜꜱ - {reason}")
            text = (
                "🎁 <b>ᴇxᴛʀᴀ ʙᴏɴᴜꜱ ᴄʀᴇᴅɪᴛᴇᴅ!</b>\n\n"
                f"💰 <b>ᴀᴍᴏᴜɴᴛ »</b> ₹{amount:.2f}\n"
                f"📌 <b>ʀᴇᴀꜱᴏɴ »</b> {html.escape(reason)}\n"
            )
            if greeting:
                text += f"\n💬 <b>{html.escape(greeting)}</b>\n"
            text += "\n💳 <b>ᴡᴀʟʟᴇᴛ ᴜᴘᴅᴀᴛᴇᴅ.</b>"
            bot.send_message(int(uid), text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
    admin_state.pop(ADMIN_ID, None)
    bot.send_message(ADMIN_ID, f"✅ <b>ᴇxᴛʀᴀ ʙᴏɴᴜꜱ ᴅᴏɴᴇ</b>\n\n✅ ꜱᴜᴄᴄᴇꜱꜱ: {success}\n❌ ꜰᴀɪʟᴇᴅ: {failed}", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.message.chat.id
    data = call.data

    try:
        bot.clear_step_handler_by_chat_id(user_id)
    except Exception:
        pass

    if user_id == ADMIN_ID and data == "admin_clear_pending_actions":
        bot.answer_callback_query(call.id)
        clear_all_pending_actions()
        return

    if user_id == ADMIN_ID and data == "admin_restore_last_backup":
        bot.answer_callback_query(call.id)
        restore_latest_backup_zip()
        return


    if user_id == ADMIN_ID and data == "admin_recent_removed":
        bot.answer_callback_query(call.id)
        show_recent_removed_services()
        return

    if user_id == ADMIN_ID and data.startswith("restore_removed_service_"):
        bot.answer_callback_query(call.id)
        sid = data.replace("restore_removed_service_", "", 1)
        restore_removed_service(sid)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return

    if user_id == ADMIN_ID and data == "admin_create_coupon":
        bot.answer_callback_query(call.id)
        start_coupon_create(False)
        return

    if user_id == ADMIN_ID and data == "admin_generate_coupon":
        bot.answer_callback_query(call.id)
        start_coupon_create(True)
        return

    if user_id == ADMIN_ID and data == "admin_delete_coupon":
        bot.answer_callback_query(call.id)
        start_coupon_delete()
        return

    if user_id == ADMIN_ID and data == "coupon_create_confirm":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        confirm_coupon_create()
        return

    if user_id == ADMIN_ID and data == "coupon_create_cancel":
        admin_state.pop(ADMIN_ID, None)
        bot.answer_callback_query(call.id, "Cancelled")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.send_message(ADMIN_ID, "❌ <b>ᴄᴏᴜᴘᴏɴ ᴄʀᴇᴀᴛᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>", parse_mode="HTML")
        return

    if user_id == ADMIN_ID and data == "admin_backup_menu":
        bot.answer_callback_query(call.id)
        show_backup_menu()
        return

    if user_id == ADMIN_ID and data == "admin_backup_botpy":
        bot.answer_callback_query(call.id)
        send_botpy_backup()
        return

    if user_id == ADMIN_ID and data == "admin_backup_json_menu":
        bot.answer_callback_query(call.id)
        start_backup_json_select()
        return

    if data == "lowbal_popup":
        bot.answer_callback_query(call.id, low_balance_popup_text(user_id), show_alert=True)
        return

    if user_id == ADMIN_ID and data == "admin_panel_home":
        try:
            bot.edit_message_text(
                "🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ</b>",
                chat_id=user_id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=admin_inline_keyboard()
            )
        except Exception:
            send_admin_panel_message(user_id)
        bot.answer_callback_query(call.id)
        return

    if user_id == ADMIN_ID and data in ADMIN_CATEGORY_CALLBACKS:
        category = ADMIN_CATEGORY_CALLBACKS[data]
        try:
            bot.edit_message_text(
                f"🟢 <b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ {admin_category_welcome_title(category)}</b>",
                chat_id=user_id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=admin_sub_inline_keyboard(category)
            )
        except Exception:
            send_admin_category_message(user_id, category)
        bot.answer_callback_query(call.id)
        return

    if user_id == ADMIN_ID and data == "admin_api_settings":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        show_api_settings_menu(user_id)
        return

    if user_id == ADMIN_ID and data == "admin_change_api_url":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        start_change_api_url()
        return

    if user_id == ADMIN_ID and data == "admin_change_api_key":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        start_change_api_key()
        return

    if user_id == ADMIN_ID and data == "admin_test_api":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        test_current_api()
        return

    if user_id == ADMIN_ID and data == "admin_exchange_files":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        send_exchange_files_menu(user_id)
        return

    if user_id == ADMIN_ID and data == "admin_exchange_update_zip":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        start_exchange_zip()
        return

    if user_id == ADMIN_ID and data == "admin_exchange_update_botpy":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        start_exchange_botpy()
        return

    if user_id == ADMIN_ID and data == "admin_exchange_update_json":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        start_exchange_json()
        return

    if data.startswith("fundhist_"):
        try:
            page = int(data.split("_", 1)[1])
        except Exception:
            page = 1
        show_fund_history(user_id, page=page, edit_message=call.message)
        bot.answer_callback_query(call.id)
        return

    if data == "order_confirm":
        success, error_msg = place_confirmed_order(user_id)
        if success:
            try:
                bot.edit_message_reply_markup(chat_id=user_id, message_id=call.message.message_id, reply_markup=None)
            except Exception:
                pass
            if get_balance(user_id) < LOW_BALANCE_LIMIT:
                bot.answer_callback_query(call.id, low_balance_popup_text(user_id), show_alert=True)
            else:
                bot.answer_callback_query(call.id, "✅ ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇᴅ")
        else:
            bot.answer_callback_query(call.id, "❌ ᴏʀᴅᴇʀ ɴᴏᴛ ᴘʟᴀᴄᴇᴅ", show_alert=True)
            if error_msg:
                bot.send_message(user_id, error_msg, parse_mode="HTML")
        return

    if data == "order_cancel":
        user_orders.pop(user_id, None)
        try:
            bot.edit_message_text(
                "❌ <b>ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>",
                chat_id=user_id,
                message_id=call.message.message_id,
                parse_mode="HTML"
            )
        except Exception:
            bot.send_message(user_id, "❌ <b>ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>", parse_mode="HTML")
        bot.answer_callback_query(call.id, "❌ ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟʟᴇᴅ")
        return

    if data.startswith("notify_service_"):
        sid = data.replace("notify_service_", "", 1)
        subscribe_service_back_alert(user_id, sid)
        bot.answer_callback_query(call.id, "🔔 ɴᴏᴛɪꜰʏ ᴇɴᴀʙʟᴇᴅ")
        bot.send_message(user_id, f"🔔 <b>ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ꜱᴇᴛ</b>\n\n🆔 <code>{sid}</code>\n✅ <b>ꜱᴇʀᴠɪᴄᴇ ᴡᴀᴘᴀꜱ ᴀᴀɴᴇ ᴘᴀʀ ᴀᴀᴘᴋᴏ ᴍᴇꜱꜱᴀɢᴇ ᴍɪʟᴇɢᴀ.</b>", parse_mode="HTML")
        return

    if data == "start_after_join":
        if is_user_joined_order_channel(user_id):
            bot.answer_callback_query(call.id, "✅ ᴄʜᴀɴɴᴇʟ ᴊᴏɪɴᴇᴅ")
            try:
                bot.delete_message(user_id, call.message.message_id)
            except Exception:
                pass
            _clear_force_join_msg_id(user_id)
            send_main_welcome(user_id)
        else:
            bot.answer_callback_query(call.id, "❌ ᴘʜʟᴇ ᴄʜᴀɴɴᴇʟ ᴊᴏɪɴ ᴋᴀʀᴏ", show_alert=True)
            # Naya message send nahi karna; isi message ke button/text ko refresh rakho.
            try:
                bot.edit_message_text(
                    _force_join_text(),
                    chat_id=user_id,
                    message_id=call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=force_join_keyboard()
                )
                _save_force_join_msg_id(user_id, call.message.message_id)
            except Exception as e:
                err = str(e).lower()
                if "message is not modified" not in err and "message not modified" not in err:
                    print("Refresh force join callback error:", e)
                    _save_force_join_msg_id(user_id, call.message.message_id)
        return

    if data.startswith("fav_add_"):
        sid = data.replace("fav_add_", "", 1)
        add_favorite_service(user_id, sid)
        bot.answer_callback_query(call.id, "⭐ ᴀᴅᴅᴇᴅ ᴛᴏ ꜰᴀᴠᴏᴜʀɪᴛᴇꜱ")
        return

    elif data == "fav_remove_menu":
        msg = bot.send_message(
            user_id,
            "🆔 <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ:</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_favorite_remove_id)
        return

    elif data.startswith("fav_remove_"):
        sid = data.replace("fav_remove_", "", 1)
        remove_favorite_service(user_id, sid)
        bot.answer_callback_query(call.id, "🗑️ ʀᴇᴍᴏᴠᴇᴅ")
        show_favorite_services(user_id)
        return

    elif data.startswith("fav_buy_"):
        sid = data.replace("fav_buy_", "", 1)
        start_order_flow(user_id, sid)
        return

    elif data == "ticket_create":
        start_create_ticket(call.message)
        return

    elif data == "ticket_status":
        show_ticket_status(user_id)
        return

    elif data.startswith("admin_reply_ticket_") and user_id == ADMIN_ID:
        ticket_id = data.replace("admin_reply_ticket_", "", 1)
        start_admin_ticket_reply(ticket_id)
        return
    
    # Admin Panel callbacks
    if data == "admin_inline_maker" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        _inline_maker_start(ADMIN_ID)
        return

    if data == "admin_broadcast" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(ADMIN_ID, "<b>✍️ ꜱᴀᴀʀᴇ ᴜꜱᴇʀꜱ ᴋᴏ ʙʜᴇᴊᴀ ᴊᴀᴀɴᴇ ᴡᴀʟᴀ ᴍᴇꜱꜱᴀɢᴇ ʟɪᴋʜᴇɪɴ (ʜᴛᴍʟ ᴛᴀɢꜱ ᴜꜱᴇ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ):</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_admin_broadcast)

    elif data == "admin_panel_prices" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "📊 ꜰᴇᴛᴄʜɪɴɢ ᴘʀɪᴄᴇꜱ...")
        show_panel_prices()

    elif data == "admin_service_price_checker" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        start_service_price_checker(call.message)
        return


    elif data == "admin_users" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "⚡ ꜰᴇᴛᴄʜɪɴɢ ᴜꜱᴇʀꜱ...")

        db = load_json(DB_FILE)
        text = "👥 ᴜꜱᴇʀꜱ ʟɪꜱᴛ\n\n"

        for uid, user in db.items():
            name = user.get("name", "Unknown")
            username = user.get("username", "No Username")
            # VIP / NORMAL
            user_type = "ᴠɪᴘ" if user.get("vip", False) else "ɴᴏʀᴍᴀʟ"
            # Join Date
            join_date = user.get("join_date", "Unknown")

            text += (
                f"🆔 ᴜꜱᴇʀ ɪᴅ » <code>{uid}</code>\n"
                f"👤 ɴᴀᴍᴇ : {name}\n"
                f"📛 ᴜꜱᴇʀɴᴀᴍᴇ : @{username}\n"
                f"👑 ᴜꜱᴇʀ ᴛʏᴘᴇ » {user_type}\n"
                f"📅 ᴊᴏɪɴᴇᴅ » {join_date}\n\n"
            )

        bot.send_message(
            ADMIN_ID,
            text,
            parse_mode="HTML")

    elif data == "admin_search_user" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "🔍 ᴜꜱᴇʀ ɪᴅ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:")
        bot.register_next_step_handler(msg, process_admin_search_user)

    elif data == "admin_ban_user" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "🚫 ᴜꜱᴇʀ ɪᴅ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:")
        bot.register_next_step_handler(msg, process_ban_user)

    elif data == "admin_unban_user" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "✅ ᴜꜱᴇʀ ɪᴅ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:")
        bot.register_next_step_handler(msg, process_unban_user)

    elif data == "admin_top_users" and user_id == ADMIN_ID:
        db = load_json(DB_FILE)
        top = sorted(db.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
        orders_db = load_json(ORDERS_FILE)

        text = "📈 ᴛᴏᴘ ᴜꜱᴇʀꜱ\n\n"
        for i, (uid, user) in enumerate(top, 1):
            orders = orders_db.get(uid, [])
            total_orders = len(orders)

            total_spent = 0
            for order in orders:
                total_spent += float(order.get("charge", 0))

            text += (
                f"🏆 ᴛᴏᴘ #{i}\n"
                f"👤 ɴᴀᴍᴇ : {user.get('name', 'Unknown')}\n"
                f"📛 ᴜꜱᴇʀɴᴀᴍᴇ : @{user.get('username', 'No Username')}\n"
                f"🆔 ᴜɪᴅ : {uid}\n"
                f"💰 ʙᴀʟᴀɴᴄᴇ : ₹{user.get('balance', 0):.2f}\n"
                f"📦 ᴛᴏᴛᴀʟ ᴏʀᴅᴇʀꜱ : {total_orders}\n"
                f"💸 ᴛᴏᴛᴀʟ ꜱᴘᴇɴᴅ : ₹{total_spent:.2f}\n\n"
            )
        bot.send_message(ADMIN_ID, text)

    elif data == "admin_total_balance" and user_id == ADMIN_ID:
        db = load_json(DB_FILE)
        total = sum(user.get("balance", 0) for user in db.values())
        bot.send_message(ADMIN_ID, f"💰 ᴛᴏᴛᴀʟ ʙᴀʟᴀɴᴄᴇ : ₹{total:.2f}")

    elif data == "admin_total_orders" and user_id == ADMIN_ID:
        orders_db = load_json(ORDERS_FILE)
        total = sum(len(v) for v in orders_db.values())
        bot.send_message(ADMIN_ID, f"📦 ᴛᴏᴛᴀʟ ᴏʀᴅᴇʀꜱ : {total}") 

    elif data == "admin_msg_user" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "📩 ᴜꜱᴇʀ ɪᴅ ʙʜᴇᴊᴏ:")
        bot.register_next_step_handler(msg, process_msg_user)

    elif data == "admin_mass_add" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "🎁 ᴍᴀꜱꜱ ᴀᴅᴅ ʙᴀʟᴀɴᴄᴇ\n\nFormat:\nUSER_ID1,USER_ID2 | AMOUNT")
        bot.register_next_step_handler(msg, process_mass_add)

    elif data == "admin_delete_user" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "🗑️ ᴜꜱᴇʀ ɪᴅ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:")
        bot.register_next_step_handler(msg, process_delete_user)

    elif data == "admin_restore_user" and user_id == ADMIN_ID:
        show_deleted_users_for_restore()

    elif data == "admin_export_csv" and user_id == ADMIN_ID:
        export_users_csv()

    elif data == "admin_list_coupons" and user_id == ADMIN_ID:
        coupons = load_json(COUPON_FILE)
        if not coupons:
            bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ᴄᴏᴜᴘᴏɴꜱ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        else:
            msg = "📋 <b>ᴄᴏᴜᴘᴏɴꜱ ʟɪꜱᴛ</b>\n\n"
            for code, item in coupons.items():
                msg += (
                    f"🎫 <b>{html.escape(str(code))}</b>\n"
                    f"💰 ᴀᴍᴏᴜɴᴛ: ₹{float(item.get('amount', 0)):.2f}\n"
                    f"👥 ᴜꜱᴇᴅ: {len(item.get('used_by', []))}/{item.get('max_uses', '∞')}\n"
                    f"📅 ᴇxᴘɪʀʏ: {html.escape(str(item.get('expiry') or 'ɴᴏ ᴇxᴘɪʀʏ'))}\n\n"
                )
            safe_send_long(ADMIN_ID, msg)

    elif data == "price_history" and user_id == ADMIN_ID:
        show_price_history()


    elif data == "maintenance" and user_id == ADMIN_ID:
        maintenance_menu(call.message)

    elif data == "schedule_bc" and user_id == ADMIN_ID:
        start_schedule_broadcast(call.message)

    elif data == "export_orders" and user_id == ADMIN_ID:
        export_orders()

    elif data == "export_funds" and user_id == ADMIN_ID:
        export_funds()

    elif data == "top_services" and user_id == ADMIN_ID:
        show_top_services()

    elif data == "admin_remove_pin_service" and user_id == ADMIN_ID:
        msg = bot.send_message(
            ADMIN_ID,
            "🗑️ <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ / ɪᴅꜱ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴘɪɴ:</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_remove_pin_service)

    elif data == "maint_on" and user_id == ADMIN_ID:
        set_maintenance(True)
        bot.answer_callback_query(call.id, "Maintenance Enabled")
        bot.send_message(ADMIN_ID, "🟢 <b>ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴏɴ</b>", parse_mode="HTML")

    elif data == "maint_off" and user_id == ADMIN_ID:
        set_maintenance(False)
        bot.answer_callback_query(call.id, "Maintenance Disabled")
        bot.send_message(ADMIN_ID, "🔴 <b>ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴏꜰꜰ</b>", parse_mode="HTML")

    elif data == "admin_panel_balance" and user_id == ADMIN_ID:
        show_panel_balance()


    elif data == "admin_backup_zip" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "📦 ʙᴀᴄᴋᴜᴘ ʀᴇᴀᴅʏ...")
        send_full_backup_zip()
        log_admin_action("backup_zip", "manual backup sent")

    elif data == "admin_auto_hide_disabled" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "🧹 ᴄʜᴇᴄᴋɪɴɢ ᴅɪꜱᴀʙʟᴇᴅ...")
        auto_hide_disabled_services()
        log_admin_action("auto_hide_disabled", "manual check")

    elif data == "admin_reports" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "🧾 ʀᴇᴘᴏʀᴛ...")
        show_business_report()

    elif data == "admin_duplicate_services" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "🔁 ᴄʜᴇᴄᴋɪɴɢ...")
        show_duplicate_services()

    elif data == "admin_delete_service" and user_id == ADMIN_ID:
        msg = bot.send_message(
            ADMIN_ID,
            "🗑️ <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ / ɪᴅꜱ ᴛᴏ ᴅᴇʟᴇᴛᴇ:</b>\n\n"
            "<code>1051</code>\n<code>1051 559 4123</code>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_delete_service_ids)

    elif data == "admin_shift_service_category" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        start_service_shift_flow(call.message)

    elif data.startswith("shift_srcplat_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        platform = data.replace("shift_srcplat_", "", 1)
        show_shift_source_subcategories(call.message, platform)

    elif data.startswith("shift_srccat_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        subcat = data.replace("shift_srccat_", "", 1)
        if subcat == "ig_followers":
            show_shift_source_ig_follow_types(call.message)
        else:
            show_shift_service_list(call.message, subcat)

    elif data.startswith("shift_srcigft_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        ft = data.replace("shift_srcigft_", "", 1)
        show_shift_service_list(call.message, "ig_followers", ft)

    elif data.startswith("shift_srv_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        sid = data.replace("shift_srv_", "", 1)
        choose_shift_destination_platform(call.message, sid)

    elif data.startswith("shift_dstplat_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        platform = data.replace("shift_dstplat_", "", 1)
        show_shift_destination_subcategories(call.message, platform)

    elif data.startswith("shift_dstcat_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        subcat = data.replace("shift_dstcat_", "", 1)
        if subcat == "ig_followers":
            show_shift_destination_ig_follow_types(call.message)
        else:
            finish_service_shift(call.message, subcat)

    elif data.startswith("shift_dstigft_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        ft = data.replace("shift_dstigft_", "", 1)
        finish_service_shift(call.message, "ig_followers", ft)

    elif data == "admin_bulk_margin" and user_id == ADMIN_ID:
        start_bulk_margin_editor(call.message)

    elif data == "admin_service_health" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "🩺 ᴄʜᴇᴄᴋɪɴɢ...")
        show_service_health_report()

    elif data == "admin_export_services" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "📤 ᴇxᴘᴏʀᴛɪɴɢ...")
        export_services_csv()

    elif data == "admin_action_logs" and user_id == ADMIN_ID:
        show_admin_action_logs()

    elif data == "admin_clean_logs" and user_id == ADMIN_ID:
        clean_admin_logs()

    elif data == "admin_pin_service" and user_id == ADMIN_ID:
        msg = bot.send_message(
            ADMIN_ID,
            "📌 <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ / ɪᴅꜱ ᴛᴏ ᴘɪɴ:</b>\n\n<code>1051</code>\n<code>1051 559 4123</code>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_pin_service)

    elif data == "custom_margin" and user_id == ADMIN_ID:
        start_margin_editor(call.message)

    elif data == "vip_margin" and user_id == ADMIN_ID:
        start_vip_margin_editor(call.message)

    elif data == "admin_add_vip" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "⭐ <b>ᴇɴᴛᴇʀ ᴜꜱᴇʀ ɪᴅ ᴛᴏ ᴀᴅᴅ ᴠɪᴘ:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_add_vip)

    elif data == "admin_remove_vip" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "❌ <b>ᴇɴᴛᴇʀ ᴜꜱᴇʀ ɪᴅ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴠɪᴘ:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_remove_vip)

    elif data == "add_balance" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)

        admin_state[ADMIN_ID] = {"action": "add"}

        msg = bot.send_message(
            ADMIN_ID,
            "<b>➕ ᴇɴᴛᴇʀ ᴜꜱᴇʀ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅ:</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_balance_uid)

    elif data == "deduct_balance" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)

        admin_state[ADMIN_ID] = {"action": "deduct"}

        msg = bot.send_message(
            ADMIN_ID,
            "<b>➖ ᴇɴᴛᴇʀ ᴜꜱᴇʀ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅ:</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_balance_uid)

    elif data == "add_service" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        start_add_service(call.message)

    elif data.startswith("addcat_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        platform = data.replace("addcat_", "")
        show_add_service_subcategories(platform)

    elif data.startswith("addsub_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        subcat_key = data.replace("addsub_", "")
        if subcat_key == "ig_followers":
            show_add_ig_follower_type()
        else:
            ask_add_service_name(subcat_key)

    elif data.startswith("addigft_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        ig_follow_type = data.replace("addigft_", "")
        ask_add_service_name("ig_followers", ig_follow_type)

    elif data == "vip_percent_margin" and user_id == ADMIN_ID:
        start_vip_percent_margin(call.message)


    elif data.startswith("autoadd_service_") and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "Opening add service flow")
        sid = data.replace("autoadd_service_", "", 1)
        _pending_remove("new", sid)
        _pending_remove("enabled", sid)
        p = find_panel_service(sid)
        if not p:
            bot.send_message(ADMIN_ID, f"❌ <b>ᴘᴀɴᴇʟ ᴍᴇ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ᴍɪʟɪ:</b> <code>{html.escape(str(sid))}</code>", parse_mode="HTML")
            return
        admin_state[ADMIN_ID] = {
            "add_services": [{
                "id": str(sid),
                "panel_name": p.get("name", "Unknown"),
                "panel_price": float(p.get("rate", 0) or 0)
            }],
            "add_index": 0,
            "added_result": []
        }
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        ask_add_service_category()

    elif data.startswith("autoremove_service_") and user_id == ADMIN_ID:
        sid = data.replace("autoremove_service_", "", 1)
        _pending_remove("disabled", sid)
        removed, name, subcat = _remove_service_from_bot(sid)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        if removed:
            bot.answer_callback_query(call.id, "Removed from bot")
            bot.send_message(
                ADMIN_ID,
                "✅ <b>ꜱᴇʀᴠɪᴄᴇ ʀᴇᴍᴏᴠᴇᴅ ꜰʀᴏᴍ ʙᴏᴛ</b>\n\n"
                f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(str(sid))}</code>\n"
                f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(name))}\n"
                f"📁 <b>ᴄᴀᴛᴇɢᴏʀʏ »</b> {html.escape(str(subcat))}",
                parse_mode="HTML"
            )
        else:
            bot.answer_callback_query(call.id, "Not found in bot", show_alert=True)


    elif data.startswith("autoignore_") and user_id == ADMIN_ID:
        parts = data.split("_", 2)
        if len(parts) >= 3:
            kind = parts[1]
            sid = parts[2]
            _pending_remove(kind, sid)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Ignored")

    elif data == "admin_pending_actions" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "📌 ᴘᴇɴᴅɪɴɢ ᴀᴄᴛɪᴏɴꜱ")
        show_pending_actions()
    elif data == "admin_smart_assistant" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        start_smart_assistant(call.message)

    elif data.startswith("smart_margin_") and user_id == ADMIN_ID:
        sid = data.replace("smart_margin_", "", 1)
        bot.answer_callback_query(call.id)
        admin_state[ADMIN_ID] = {"margin_ids": [sid]}
        msg = bot.send_message(ADMIN_ID, f"🎯 <b>ᴇɴᴛᴇʀ ɴᴇᴡ ᴍᴀʀɢɪɴ ꜰᴏʀ</b> <code>{html.escape(str(sid))}</code>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_new_margin)

    elif data.startswith("smart_shift_") and user_id == ADMIN_ID:
        sid = data.replace("smart_shift_", "", 1)
        bot.answer_callback_query(call.id)
        choose_shift_destination_platform(call.message, sid)

    elif data.startswith("smart_remove_") and user_id == ADMIN_ID:
        sid = data.replace("smart_remove_", "", 1)
        bot.answer_callback_query(call.id)
        removed, name, subcat = _remove_service_from_bot(sid)
        if removed:
            bot.send_message(ADMIN_ID, f"✅ <b>ꜱᴇʀᴠɪᴄᴇ ʀᴇᴍᴏᴠᴇᴅ</b>\n\n🆔 <code>{html.escape(str(sid))}</code>\n📦 {html.escape(str(name))}", parse_mode="HTML")
        else:
            bot.send_message(ADMIN_ID, f"❌ <b>ꜱᴇʀᴠɪᴄᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ:</b> <code>{html.escape(str(sid))}</code>", parse_mode="HTML")

    elif data.startswith("smart_pin_") and user_id == ADMIN_ID:
        sid = data.replace("smart_pin_", "", 1)
        bot.answer_callback_query(call.id)
        pins = load_json(PINNED_SERVICES_FILE)
        if not isinstance(pins, list):
            pins = list(pins.keys()) if isinstance(pins, dict) else []
        sid = str(sid)
        if sid in [str(x) for x in pins]:
            pins = [x for x in pins if str(x) != sid]
            save_json(PINNED_SERVICES_FILE, pins)
            bot.send_message(ADMIN_ID, f"🗑️ <b>ᴘɪɴ ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{html.escape(sid)}</code>", parse_mode="HTML")
        else:
            pins.append(sid)
            save_json(PINNED_SERVICES_FILE, pins)
            bot.send_message(ADMIN_ID, f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ᴘɪɴɴᴇᴅ:</b> <code>{html.escape(sid)}</code>", parse_mode="HTML")

    elif data.startswith("smart_price_history_") and user_id == ADMIN_ID:
        sid = data.replace("smart_price_history_", "", 1)
        bot.answer_callback_query(call.id)
        history = load_json(PRICE_HISTORY_FILE)
        msg = f"📊 <b>ᴘʀɪᴄᴇ ʜɪꜱᴛᴏʀʏ</b>\n\n🆔 <code>{html.escape(str(sid))}</code>\n\n"
        found = 0
        if isinstance(history, dict):
            for t, rows in list(history.items())[-50:]:
                if isinstance(rows, list):
                    for row in rows:
                        if str(row).startswith(str(sid)+":"):
                            msg += f"📅 {html.escape(str(t))}\n{html.escape(str(row))}\n\n"
                            found += 1
        if not found:
            msg += "❌ ɴᴏ ʜɪꜱᴛᴏʀʏ"
        bot.send_message(ADMIN_ID, msg[:4000], parse_mode="HTML")

    elif data.startswith("smart_health_") and user_id == ADMIN_ID:
        sid = data.replace("smart_health_", "", 1)
        bot.answer_callback_query(call.id)
        panel = find_panel_service(sid)
        status = "✅ ᴀᴄᴛɪᴠᴇ ɪɴ ᴘᴀɴᴇʟ" if panel else "🚫 ɴᴏᴛ ꜰᴏᴜɴᴅ / ᴅɪꜱᴀʙʟᴇᴅ"
        bot.send_message(ADMIN_ID, f"🩺 <b>ꜱᴇʀᴠɪᴄᴇ ʜᴇᴀʟᴛʜ</b>\n\n🆔 <code>{html.escape(str(sid))}</code>\n🔄 <b>{status}</b>", parse_mode="HTML")

    elif data == "admin_extra_bonus" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        start_extra_bonus_flow(call.message)

    elif data == "extra_bonus_confirm" and user_id == ADMIN_ID:
        bot.answer_callback_query(call.id, "ᴄʀᴇᴅɪᴛɪɴɢ...")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        apply_extra_bonus_to_all()

    elif data == "extra_bonus_cancel" and user_id == ADMIN_ID:
        admin_state.pop(ADMIN_ID, None)
        bot.answer_callback_query(call.id, "ᴄᴀɴᴄᴇʟʟᴇᴅ")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.send_message(ADMIN_ID, "❌ <b>ᴇxᴛʀᴀ ʙᴏɴᴜꜱ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>", parse_mode="HTML")

    # Fund approvals
    elif data.startswith("fund_approve_") and user_id == ADMIN_ID:
        request_id = data.replace("fund_approve_", "", 1)
        req, req_db = get_pending_fund_request(request_id)
        if not req:
            bot.answer_callback_query(call.id, "Already approved/rejected", show_alert=True)
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            except:
                pass
            return

        target_uid = req["user_id"]
        amount = float(req["amount"])
        update_balance(target_uid, amount)
        log_fund_transaction(target_uid, amount, status="approved", utr=req.get("utr", ""), has_photo=req.get("has_photo", False), request_id=request_id)
        referral_bonus = give_referral_commission(target_uid, amount)

        req_db[request_id]["status"] = "approved"
        req_db[request_id]["approved_at"] = datetime.now().strftime("%d-%m-%Y %I:%M %p")
        save_json(FUND_REQUESTS_FILE, req_db)
        bot.answer_callback_query(call.id, "Fund approved")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass
        
        bot.send_message(
            ADMIN_ID,
                "✅ <b>ꜰᴜɴᴅ ᴀᴘᴘʀᴏᴠᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n"
                f"👤 <b>ᴜꜱᴇʀ ɪᴅ »</b> <code>{target_uid}</code>\n"
                f"💰 <b>ᴀᴍᴏᴜɴᴛ ᴀᴅᴅᴇᴅ »</b> ₹{amount:.2f}\n"
                f"🎁 <b>ʀᴇꜰᴇʀʀᴀʟ ʙᴏɴᴜꜱ »</b> ₹{referral_bonus:.2f}\n"
                f"💎 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ »</b> ₹{get_balance(target_uid):.2f}\n\n"
                "⚡ <b>ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ</b>\n\n"
                "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
            parse_mode="HTML"
        )
        try:
            new_bal = get_balance(target_uid)
            success_msg = (
                "✅ <b>ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ!</b>\n\n"
                "🎉 <b>ᴘᴀʏᴍᴇɴᴛ ᴄᴏɴꜰɪʀᴍᴇᴅ</b>\n"
                "💳 <b>ꜰᴜɴᴅ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n"
                f"➕ <b>ᴀᴍᴏᴜɴᴛ ᴀᴅᴅᴇᴅ »</b> ₹{amount:.2f}\n"
                f"💰 <b>ᴄᴜʀʀᴇɴᴛ ʙᴀʟᴀɴᴄᴇ »</b> ₹{new_bal:.2f}\n"
                f"📅 <b>ᴅᴀᴛᴇ »</b> {datetime.now().strftime('%d-%m-%Y')}\n"
                f"🕒 <b>ᴛɪᴍᴇ »</b> {datetime.now().strftime('%I:%M %p')}\n\n"
                "💎 <b>ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ ʜᴀꜱ ʙᴇᴇɴ ᴜᴘᴅᴀᴛᴇᴅ.</b>\n"
                "🚀 <b>ʏᴏᴜ ᴄᴀɴ ɴᴏᴡ ᴘʟᴀᴄᴇ ᴏʀᴅᴇʀꜱ ɪɴꜱᴛᴀɴᴛʟʏ.</b>\n"
                "⚡ <b>ᴇɴᴊᴏʏ ꜰᴀꜱᴛ, ꜱᴀꜰᴇ & ʀᴇʟɪᴀʙʟᴇ ꜱᴇʀᴠɪᴄᴇꜱ.</b>\n\n"
                "🙏 <b>ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴄʜᴏᴏꜱɪɴɢ ᴜꜱ!</b>\n"
                "🤖 <b>ʟᴇɢᴇɴᴅᴀʀʏ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💎</b>"
            )
            bot.send_message(target_uid, success_msg, parse_mode="HTML")
        except: pass
        
    elif data.startswith("fund_reject_") and user_id == ADMIN_ID:
        request_id = data.replace("fund_reject_", "", 1)
        req, req_db = get_pending_fund_request(request_id)
        if not req:
            bot.answer_callback_query(call.id, "Already approved/rejected", show_alert=True)
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            except:
                pass
            return

        target_uid = req["user_id"]
        amount = float(req.get("amount", 0) or 0)
        log_fund_transaction(target_uid, amount, status="rejected", utr=req.get("utr", ""), has_photo=req.get("has_photo", False), request_id=request_id)
        req_db[request_id]["status"] = "rejected"
        req_db[request_id]["rejected_at"] = datetime.now().strftime("%d-%m-%Y %I:%M %p")
        save_json(FUND_REQUESTS_FILE, req_db)
        bot.answer_callback_query(call.id, "Fund rejected")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass
        bot.send_message(
            ADMIN_ID,
            "❌ <b>ꜰᴜɴᴅ ʀᴇQᴜᴇꜱᴛ ʀᴇᴊᴇᴄᴛᴇᴅ!</b>\n\n"
            f"👤 <b>ᴜꜱᴇʀ ɪᴅ »</b> <code>{target_uid}</code>\n"
            "⚠️ <b>ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ɴᴏᴛ ᴀᴘᴘʀᴏᴠᴇᴅ</b>\n\n"
            "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
            parse_mode="HTML"
        )
        try:
            bot.send_message(target_uid, "❌ <b>ꜰᴜɴᴅ ʀᴇᴊᴇᴄᴛᴇᴅ!</b>\nᴀᴀᴘᴋᴀ ᴜᴛʀ ᴍᴀᴛᴄʜ ɴᴀʜɪ ʜᴜᴀ. ᴋʀɪᴘʏᴀ ᴛɪᴄᴋᴇᴛ ᴄʀᴇᴀᴛᴇ ᴋᴀʀᴇɪɴ.", parse_mode="HTML")
        except:
            pass

    elif data.startswith("refill_order_"):
        order_id = data.split("_")[-1]

        class FakeMessage:
            pass

        fake = FakeMessage()
        fake.chat = call.message.chat
        fake.text = order_id

        process_refill_order(fake)

    elif data.startswith("cancel_order_"):
        order_id = data.split("_")[-1]

        class FakeMessage:
            pass

        fake = FakeMessage()
        fake.chat = call.message.chat
        fake.text = order_id

        process_cancel_order(fake)

      #ORDER LINK LE KAR AGE BHEJNA
    elif data.startswith("plat_"):
        plat = data.split("_")[1]
        try:
            bot.edit_message_text("<b>✨ ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ꜱᴜʙ-ᴄᴀᴛᴇɢᴏʀʏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏʀ:</b>", chat_id=user_id, message_id=call.message.message_id, reply_markup=subcat_keyboard(plat), parse_mode="HTML")
        except Exception as e:
            if "message is not modified" not in str(e):
                print("Platform edit error:", e)
        
    elif data == "back_platforms":
        try:
            bot.edit_message_text("<b>🌐 ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ᴘʟᴀᴛꜰᴏʀᴍ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏʀᴅᴇʀ ꜱᴇʀᴠɪᴄᴇꜱ ꜰᴏʀ:</b>", chat_id=user_id, message_id=call.message.message_id, reply_markup=platforms_keyboard(), parse_mode="HTML")
        except Exception as e:
            if "message is not modified" not in str(e):
                print("Back edit error:", e)
        
    elif data.startswith("subcat_"):
        cat_key = data.replace("subcat_", "")
        markup = types.InlineKeyboardMarkup(row_width=1)

        counter = 1

        if cat_key in SERVICES:
            for s_id, s_info in SERVICES[cat_key].items():
                clean_name = s_info[0].replace("<b>", "").replace("</b>", "")
                selling_price = get_selling_price_for_user(s_id, user_id) or s_info[1]
                display_text = f"{counter}. {clean_name} - ₹{float(selling_price):.2f}"
                markup.add(types.InlineKeyboardButton(display_text, callback_data=f"srv_{s_id}"))
                counter += 1

        added_db = load_json(ADDED_SERVICES_FILE)

        for s_id, item in added_db.items():
            if item.get("subcat") != cat_key:
                continue

            clean_name = item.get("name", "Unknown")
            selling_price = get_selling_price_for_user(s_id, user_id) or float(item.get("price", 0))

            display_text = f"{counter}. {clean_name} - ₹{selling_price:.2f}"
            markup.add(types.InlineKeyboardButton(display_text, callback_data=f"srv_{s_id}"))
            counter += 1

        p_back = cat_key.split("_")[0]
        if p_back not in ADD_SERVICE_CATS:
            p_back = "ig"
            
        markup.add(types.InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"plat_{p_back}"))
        try:
            bot.edit_message_text("<b>📦 ᴘʟᴇᴀꜱᴇ ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ꜱᴇʀᴠɪᴄᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴘʟᴀᴄᴇ ᴀɴ ᴏʀᴅᴇʀ ꜰᴏʀ:</b>", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            if "message is not modified" not in str(e):
                print("Subcat edit error:", e)
        
    elif data.startswith("srv_"):
        service_id = data.split("_")[1]
        start_order_flow(user_id, service_id)

      #SEARCH HISTORY SE BUY NIW KA CALLBACK LEKAR AGE KA KAAM KARNA
    elif data == "search_buy_now":
        results = search_results.get(user_id, [])

        if not results:
            bot.send_message(
                user_id,
                "❌ <b>ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛ ᴇxᴘɪʀᴇᴅ. ᴘʟᴇᴀꜱᴇ ꜱᴇᴀʀᴄʜ ᴀɢᴀɪɴ.</b>",
                parse_mode="HTML"
            )
            return

        if len(results) == 1:
            start_order_flow(user_id, results[0])
            return

        msg = bot.send_message(
            user_id,
            "🆔 <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ:</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_search_buy_service_id)

    elif data.startswith("reorder_"):
        order_id = data.replace("reorder_", "").replace("_", "").strip()
        process_reorder(user_id, order_id)

def process_balance_uid(message):
    if message.chat.id != ADMIN_ID:
        return

    uid = message.text.strip()
    db = load_json(DB_FILE)

    if uid not in db:
        bot.send_message(ADMIN_ID, "❌ <b>ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return

    admin_state[ADMIN_ID]["target_uid"] = uid

    msg = bot.send_message(
        ADMIN_ID,
        f"👤 <b>ᴜꜱᴇʀ ɪᴅ »</b> <code>{uid}</code>\n"
        f"💰 <b>ᴄᴜʀʀᴇɴᴛ ʙᴀʟᴀɴᴄᴇ »</b> ₹{get_balance(uid):.2f}\n\n"
        "✏️ <b>ᴇɴᴛᴇʀ ᴀᴍᴏᴜɴᴛ:</b>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_balance_amount)


def process_balance_amount(message):
    if message.chat.id != ADMIN_ID:
        return

    try:
        amount = float(message.text.strip())
    except:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ</b>", parse_mode="HTML")
        return

    action = admin_state[ADMIN_ID].get("action", "add")
    uid = admin_state[ADMIN_ID].get("target_uid")

    if action == "deduct":
        amount = -abs(amount)
    else:
        amount = abs(amount)

    old_balance = get_balance(uid)
    update_balance(uid, amount)
    new_balance = get_balance(uid)

    reason = "ᴍᴀɴᴜᴀʟ ᴀᴅᴅ" if amount > 0 else "ᴍᴀɴᴜᴀʟ ᴅᴇᴅᴜᴄᴛ"
    log_wallet(uid, amount, reason)

    if amount > 0:
        log_fund_transaction(uid, amount)
        title = "✅ <b>ʙᴀʟᴀɴᴄᴇ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>"
        amount_text = "➕ <b>ᴀᴍᴏᴜɴᴛ ᴀᴅᴅᴇᴅ »</b>"
    else:
        title = "➖ <b>ʙᴀʟᴀɴᴄᴇ ᴅᴇᴅᴜᴄᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>"
        amount_text = "➖ <b>ᴀᴍᴏᴜɴᴛ ᴅᴇᴅᴜᴄᴛᴇᴅ »</b>"

    bot.send_message(
        ADMIN_ID,
        f"{title}\n\n"
        f"👤 <b>ᴜꜱᴇʀ ɪᴅ »</b> <code>{uid}</code>\n"
        f"💰 <b>ᴏʟᴅ ʙᴀʟᴀɴᴄᴇ »</b> ₹{old_balance:.2f}\n"
        f"{amount_text} ₹{abs(amount):.2f}\n"
        f"💎 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ »</b> ₹{new_balance:.2f}\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
        parse_mode="HTML"
    )

    bot.send_message(
        int(uid),
        f"{title}\n\n"
        f"{amount_text} ₹{abs(amount):.2f}\n"
        f"💎 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ »</b> ₹{new_balance:.2f}\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>",
        parse_mode="HTML"
    )

    admin_state.pop(ADMIN_ID, None)

def process_search_buy_service_id(message):
    user_id = message.chat.id

    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return

    service_id = message.text.strip()
    results = search_results.get(user_id, [])

    if service_id not in results:
        bot.send_message(
            user_id,
            "❌ <b>ɪɴᴠᴀʟɪᴅ ꜱᴇʀᴠɪᴄᴇ ɪᴅ</b>\n\n"
            "📌 ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛ ᴍᴇ ꜱᴇ ʜɪ ɪᴅ ᴅᴀʟᴏ.",
            parse_mode="HTML"
        )
        return

    start_order_flow(user_id, service_id)

def start_order_flow(user_id, service_id):
    record_recent_service(user_id, service_id)
    schema = _detect_order_schema(service_id)
    user_orders[user_id] = {"service_id": service_id, "schema": schema}

    s_info = find_service(service_id)

    if not s_info:
        bot.send_message(user_id, "❌ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ᴍɪʟɪ.")
        return

    clean_srv_name = s_info[0].replace("<b>", "").replace("</b>", "")
    selling_price = get_selling_price_for_user(service_id, user_id) or s_info[1]

    fav_markup = types.InlineKeyboardMarkup()
    fav_markup.add(
        types.InlineKeyboardButton(
            "⭐ ᴀᴅᴅ ᴛᴏ ꜰᴀᴠᴏᴜʀɪᴛᴇ",
            callback_data=f"fav_add_{service_id}"
        )
    )

    msg = bot.send_message(
        user_id,
        f"<b>ꜱᴇʟᴇᴄᴛᴇᴅ</b>: <b>{clean_srv_name}</b>\n"
        f"<b>ʀᴀᴛᴇ:</b> ₹{selling_price:.2f}/1000\n"\
        f"{'👑 <b>ᴠɪᴘ ᴘʀɪᴄᴇ</b>\n' if is_vip_user(user_id) else ''}\n"
        f"<b>🔗 ᴀᴘɴɪ ʟɪɴᴋ ᴇɴᴛᴇʀ ᴋᴀʀᴇɪɴ:</b>",
        parse_mode="HTML",
        reply_markup=fav_markup
    )

    bot.register_next_step_handler(msg, process_link)

def start_order_flow_for_reorder(user_id, service_id):
    schema = _detect_order_schema(service_id)
    user_orders[user_id] = {"service_id": service_id, "schema": schema}

    s_info = find_service(service_id)

    if not s_info:
        bot.send_message(user_id, "❌ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ᴍɪʟɪ.")
        return

    clean_srv_name = s_info[0].replace("<b>", "").replace("</b>", "")
    selling_price = get_selling_price_for_user(service_id, user_id) or s_info[1]

    msg = bot.send_message(
        user_id,
        f"<b>🔁 ʀᴇᴏʀᴅᴇʀ ᴍᴏᴅᴇ</b>\n\n"
        f"<b>ꜱᴇʟᴇᴄᴛᴇᴅ</b>: <b>{clean_srv_name}</b>\n"
        f"<b>ʀᴀᴛᴇ:</b> ₹{selling_price:.2f}/1000\n"\
        f"{'👑 <b>ᴠɪᴘ ᴘʀɪᴄᴇ</b>\n' if is_vip_user(user_id) else ''}\n"
        f"<b>🔗 ᴀᴘɴɪ ʟɪɴᴋ ᴇɴᴛᴇʀ ᴋᴀʀᴇɪɴ:</b>",
        parse_mode="HTML"
    )

    bot.register_next_step_handler(msg, process_link)

def start_service_search(message):
    user_id = message.chat.id

    bot.clear_step_handler_by_chat_id(user_id)

    msg = bot.send_message(
        user_id,
        "🔍 <b>ᴇɴᴛᴇʀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ᴏʀ ɴᴀᴍᴇ:</b>\n\n"
        "🔍 <b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
        "🔍 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ 1</b>\n"
        "🔍 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ 2</b>\n\n"
        "🔍 <b>ᴀᴘᴋᴏ ᴊɪᴛɴᴀ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ꜱᴇᴀʀᴄʜ ᴋᴀʀɴᴀ ʜᴀɪ ɪꜱ ꜰᴏʀᴍᴀᴛ ᴍᴇ ᴅᴀʟɪʏᴇ. ᴀɢᴀʀ ᴇᴋ ʜɪ ꜱᴇʀᴠɪᴄᴇ ᴅᴇᴋʜɴɪ ʜᴀɪ ᴛᴏ ꜱɪʀꜰ ᴇᴋ ɪᴅ ᴅᴀʟɪʏᴇ.</b>",
        parse_mode="HTML"
    )

    bot.register_next_step_handler_by_chat_id(user_id, process_service_search)

def show_top_services():
    orders = load_json(ORDERS_FILE)
    counter = Counter()

    for uid, user_orders_list in orders.items():
        for order in user_orders_list:
            sid = str(order.get("srv_id") or order.get("service") or "")
            if sid:
                counter[sid] += 1

    if not counter:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ᴏʀᴅᴇʀ ʜɪꜱᴛᴏʀʏ</b>", parse_mode="HTML")
        return

    msg = "🏆 <b>ᴛᴏᴘ 10 ᴍᴏꜱᴛ ᴏʀᴅᴇʀᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n\n"

    for rank, (sid, total) in enumerate(counter.most_common(10), 1):
        msg += (
            f"{rank}. 🆔 <b>{sid}</b> » <b>{get_service_name(sid)}</b>\n"
            f"📊 <b>ᴏʀᴅᴇʀꜱ :</b> {total}\n\n"
        )

    bot.send_message(ADMIN_ID, msg, parse_mode="HTML")

def process_service_search(message):
    user_id = message.chat.id

    if not getattr(message, "text", None):
        return

    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return

    raw_query = message.text.strip()
    if not raw_query:
        return

    query_parts = raw_query.replace(",", " ").replace("\n", " ").split()
    query_parts = [q.strip().lower() for q in query_parts if q.strip()]

    matched_services = []
    added_ids = set()
    all_services = get_all_bot_services_map()

    for sid, item in all_services.items():
        service_name = str(item.get("name", "Unknown"))
        sid_lower = str(sid).lower()
        name_lower = service_name.lower()

        matched = False

        for q in query_parts:
            if q == sid_lower:
                matched = True
                break

        if not matched and raw_query.lower() in name_lower:
            matched = True

        if not matched and any(not q.isdigit() for q in query_parts):
            text_words = [q for q in query_parts if not q.isdigit()]
            if text_words and all(q in name_lower for q in text_words):
                matched = True

        if matched and sid not in added_ids:
            matched_services.append((sid, item))
            added_ids.add(sid)

    if not matched_services:
        bot.send_message(
            user_id,
            "❌ <b>ɴᴏ ꜱᴇʀᴠɪᴄᴇ ꜰᴏᴜɴᴅ</b>",
            parse_mode="HTML"
        )
        return

    search_results[user_id] = [sid for sid, item in matched_services]

    msg = "🔍 <b>ꜱᴇʀᴠɪᴄᴇ ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛ</b>\n\n"

    markup = types.InlineKeyboardMarkup(row_width=1)

    for index, (sid, item) in enumerate(matched_services, 1):
        service_name = str(item.get("name", "Unknown"))

        try:
            selling_price = get_selling_price_for_user(str(sid), user_id)
            if selling_price is None:
                selling_price = float(item.get("price", 0))
        except Exception:
            selling_price = float(item.get("price", 0))

        msg += (
            f"{index}. 🆔 <b>{sid}</b> » <b>{html.escape(service_name)}</b>\n"
            f"💎 <b>ʙᴏᴛ ʀᴀᴛᴇ :</b> ₹{selling_price:.2f}/1000\n\n"
        )

    if len(matched_services) == 1:
        sid = matched_services[0][0]
        markup.add(
            types.InlineKeyboardButton(
                "🛒 ʙᴜʏ ɴᴏᴡ",
                callback_data=f"srv_{sid}"
            )
        )
    else:
        markup.add(
            types.InlineKeyboardButton(
                "🛒 ʙᴜʏ ɴᴏᴡ",
                callback_data="search_buy_now"
            )
        )

    if len(msg) <= 3900:
        bot.send_message(
            user_id,
            msg,
            parse_mode="HTML",
            reply_markup=markup
        )
    else:
        chunks = []
        current = "🔍 <b>ꜱᴇʀᴠɪᴄᴇ ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛ</b>\n\n"

        for block in msg.split("\n\n")[1:]:
            line = block + "\n\n"
            if len(current) + len(line) > 3900:
                chunks.append(current)
                current = "🔍 <b>ꜱᴇʀᴠɪᴄᴇ ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛ</b>\n\n"
            current += line

        if current.strip():
            chunks.append(current)

        for part in chunks[:-1]:
            bot.send_message(user_id, part, parse_mode="HTML")

        bot.send_message(
            user_id,
            chunks[-1],
            parse_mode="HTML",
            reply_markup=markup
        )


def safe_send_long(chat_id, text, parse_mode="HTML", chunk=3900):
    """Long message ko safe parts me send karta hai."""
    if not text:
        return
    parts = []
    while len(text) > chunk:
        cut = text.rfind("\n", 0, chunk)
        if cut == -1:
            cut = chunk
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    for part in parts:
        bot.send_message(chat_id, part, parse_mode=parse_mode)


def send_full_backup_zip():
    """Admin ko bot.py + JSON files ka instant ZIP backup bhejta hai."""
    try:
        files = ["bot.py"]
        files += [f for f in os.listdir(".") if f.endswith(".json") and not f.endswith("_backup.json")]
        stamp = datetime.now().strftime("%d%m%Y_%H%M%S")
        zip_name = f"smm_bot_backup_{stamp}.zip"

        import zipfile
        with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                if os.path.exists(f):
                    z.write(f)

        backup_dir = os.path.join(_base_dir(), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        saved_backup_path = os.path.join(backup_dir, zip_name)
        try:
            shutil.copy(zip_name, saved_backup_path)
        except Exception:
            saved_backup_path = zip_name

        with open(zip_name, "rb") as doc:
            bot.send_document(ADMIN_ID, doc, caption="📦 <b>ꜰᴜʟʟ ʙᴏᴛ ʙᴀᴄᴋᴜᴘ</b>", parse_mode="HTML")
        try:
            if os.path.abspath(zip_name) != os.path.abspath(saved_backup_path):
                os.remove(zip_name)
        except:
            pass
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>ʙᴀᴄᴋᴜᴘ ᴇʀʀᴏʀ:</b> {html.escape(str(e))}", parse_mode="HTML")


def auto_hide_disabled_services():
    """Panel me jo service nahi milti, usko services.json / added_services.json se hide/delete karta hai."""
    try:
        panel_services = get_all_panel_services()
        panel_ids = {str(s.get("service")) for s in panel_services}

        services_db = load_json(SERVICES_FILE)
        added_db = load_json(ADDED_SERVICES_FILE)
        margins_db = load_json(MARGINS_FILE)

        removed = []

        for subcat, items in list(services_db.items()):
            if not isinstance(items, dict):
                continue
            for sid in list(items.keys()):
                if str(sid) not in panel_ids:
                    name = items[sid][0] if isinstance(items[sid], list) and items[sid] else "Unknown"
                    removed.append((str(sid), name, subcat, "services.json"))
                    items.pop(sid, None)
                    margins_db.pop(str(sid), None)
            services_db[subcat] = items

        for sid, item in list(added_db.items()):
            if str(sid) not in panel_ids:
                removed.append((str(sid), item.get("name", "Unknown"), item.get("subcat", ""), "added_services.json"))
                added_db.pop(str(sid), None)
                margins_db.pop(str(sid), None)

        save_json(SERVICES_FILE, services_db)
        save_json(ADDED_SERVICES_FILE, added_db)
        save_json(MARGINS_FILE, margins_db)

        if not removed:
            bot.send_message(ADMIN_ID, "✅ <b>ᴋᴏɪ ᴅɪꜱᴀʙʟᴇᴅ ꜱᴇʀᴠɪᴄᴇ ʜɪᴅᴇ ɴᴀʜɪ ʜᴜɪ.</b>", parse_mode="HTML")
            return

        msg = f"🧹 <b>ᴅɪꜱᴀʙʟᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ ʜɪᴅᴇᴅ</b>\n\n📦 <b>ᴛᴏᴛᴀʟ:</b> {len(removed)}\n\n"
        for sid, name, subcat, source in removed[:80]:
            msg += f"🆔 <code>{sid}</code> » {html.escape(str(name))}\n📁 {html.escape(str(subcat))} | {source}\n\n"
        safe_send_long(ADMIN_ID, msg)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>ᴀᴜᴛᴏ ʜɪᴅᴇ ᴇʀʀᴏʀ:</b> {html.escape(str(e))}", parse_mode="HTML")


def show_business_report():
    """Orders, wallet, funds aur profit ka quick report."""
    orders_db = load_json(ORDERS_FILE)
    users_db = load_json(DB_FILE)
    funds_db = load_json(FUNDS_HISTORY_FILE)

    total_orders = 0
    completed = pending = cancelled = partial = 0
    total_sales = 0.0
    today_sales = 0.0
    today_orders = 0
    today = datetime.now().strftime("%d-%m-%Y")

    service_counter = Counter()
    user_counter = Counter()

    for uid, orders in orders_db.items():
        for order in orders:
            total_orders += 1
            sid = str(order.get("srv_id") or order.get("service") or "")
            status = str(order.get("status", "")).lower()
            charge = float(order.get("charge", 0) or 0)
            date_text = str(order.get("date") or order.get("time") or order.get("created_at") or "")

            total_sales += charge
            service_counter[sid] += 1
            user_counter[str(uid)] += 1

            if today in date_text:
                today_sales += charge
                today_orders += 1

            if status == "completed":
                completed += 1
            elif status in ("cancelled", "canceled"):
                cancelled += 1
            elif status == "partial":
                partial += 1
            else:
                pending += 1

    active_users = sum(1 for u in users_db.values() if u.get("active", True))
    banned_users = len(users_db) - active_users
    vip_users = sum(1 for u in users_db.values() if u.get("vip", False))
    today_users = sum(1 for u in users_db.values() if u.get("join_date") == today)

    total_wallet = sum(float(u.get("balance", 0) or 0) for u in users_db.values())
    total_funds = 0.0
    for uid, rows in funds_db.items():
        for r in rows:
            total_funds += float(r.get("amount", 0) or 0)

    msg = (
        "🧾 <b>ʙᴜꜱɪɴᴇꜱꜱ ʀᴇᴘᴏʀᴛ</b>\n\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ:</b> {len(users_db)}\n"
        f"🟢 <b>ᴀᴄᴛɪᴠᴇ ᴜꜱᴇʀꜱ:</b> {active_users}\n"
        f"🚫 <b>ʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ:</b> {banned_users}\n"
        f"👑 <b>ᴠɪᴘ ᴜꜱᴇʀꜱ:</b> {vip_users}\n"
        f"📅 <b>ᴛᴏᴅᴀʏ ᴜꜱᴇʀꜱ:</b> {today_users}\n\n"
        f"📦 <b>ᴛᴏᴛᴀʟ ᴏʀᴅᴇʀꜱ:</b> {total_orders}\n"
        f"✅ <b>ᴄᴏᴍᴘʟᴇᴛᴇᴅ:</b> {completed}\n"
        f"⏳ <b>ᴘᴇɴᴅɪɴɢ/ᴘʀᴏᴄᴇꜱꜱ:</b> {pending}\n"
        f"⚠️ <b>ᴘᴀʀᴛɪᴀʟ:</b> {partial}\n"
        f"❌ <b>ᴄᴀɴᴄᴇʟʟᴇᴅ:</b> {cancelled}\n\n"
        f"💰 <b>ᴛᴏᴛᴀʟ ꜱᴀʟᴇꜱ:</b> ₹{total_sales:.2f}\n"
        f"📅 <b>ᴛᴏᴅᴀʏ ᴏʀᴅᴇʀꜱ:</b> {today_orders}\n"
        f"📅 <b>ᴛᴏᴅᴀʏ ꜱᴀʟᴇꜱ:</b> ₹{today_sales:.2f}\n"
        f"➕ <b>ᴛᴏᴛᴀʟ ꜰᴜɴᴅꜱ:</b> ₹{total_funds:.2f}\n"
        f"👛 <b>ᴜꜱᴇʀ ᴡᴀʟʟᴇᴛ ʟɪᴀʙɪʟɪᴛʏ:</b> ₹{total_wallet:.2f}\n\n"
    )

    if service_counter:
        msg += "🏆 <b>ᴛᴏᴘ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n"
        for sid, count in service_counter.most_common(5):
            msg += f"🆔 <code>{sid}</code> » {count} ᴏʀᴅᴇʀꜱ\n"

    safe_send_long(ADMIN_ID, msg)


def show_duplicate_services():
    """Same service name ya same ID duplicate check."""
    all_services = get_all_bot_services_map()
    name_map = {}
    for sid, item in all_services.items():
        name = str(item.get("name", "Unknown")).strip().lower()
        name_map.setdefault(name, []).append(str(sid))

    duplicates = [(name, ids) for name, ids in name_map.items() if len(ids) > 1]

    if not duplicates:
        bot.send_message(ADMIN_ID, "✅ <b>ᴅᴜᴘʟɪᴄᴀᴛᴇ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ᴍɪʟɪ.</b>", parse_mode="HTML")
        return

    msg = f"🔁 <b>ᴅᴜᴘʟɪᴄᴀᴛᴇ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n\n📦 <b>ᴛᴏᴛᴀʟ:</b> {len(duplicates)}\n\n"
    for name, ids in duplicates[:80]:
        msg += f"📦 {html.escape(name)}\n🆔 {', '.join(ids)}\n\n"
    safe_send_long(ADMIN_ID, msg)


def process_delete_service_ids(message):
    if message.chat.id != ADMIN_ID:
        return

    ids = message.text.replace(",", " ").replace("\n", " ").split()
    ids = [str(x).strip() for x in ids if x.strip()]
    if not ids:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ꜱᴇʀᴠɪᴄᴇ ɪᴅ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return

    services_db = load_json(SERVICES_FILE)
    added_db = load_json(ADDED_SERVICES_FILE)
    margins_db = load_json(MARGINS_FILE)

    deleted = []
    not_found = []

    for sid in ids:
        found = False
        for subcat, items in services_db.items():
            if isinstance(items, dict) and sid in items:
                removed_row = items.get(sid)
                name = items[sid][0] if isinstance(items[sid], list) and items[sid] else "Unknown"
                items.pop(sid, None)
                source = "services.json"
                try:
                    _recent_removed_add(sid, name, subcat, source, removed_row)
                except Exception as e:
                    print("recent removed save error:", e)
                deleted.append((sid, name, subcat, source))
                found = True
                break
        if sid in added_db:
            removed_row = added_db.get(sid, {})
            name = added_db[sid].get("name", "Unknown")
            subcat = added_db[sid].get("subcat", "")
            added_db.pop(sid, None)
            source = "added_services.json"
            try:
                _recent_removed_add(sid, name, subcat, source, removed_row)
            except Exception as e:
                print("recent removed save error:", e)
            deleted.append((sid, name, subcat, source))
            found = True
        margins_db.pop(sid, None)
        if not found:
            not_found.append(sid)

    save_json(SERVICES_FILE, services_db)
    save_json(ADDED_SERVICES_FILE, added_db)
    save_json(MARGINS_FILE, margins_db)

    msg = "🗑️ <b>ᴅᴇʟᴇᴛᴇ ꜱᴇʀᴠɪᴄᴇ ʀᴇꜱᴜʟᴛ</b>\n\n"
    for sid, name, subcat, source in deleted:
        msg += f"✅ <code>{sid}</code> » {html.escape(str(name))}\n📁 {html.escape(str(subcat))} | {source}\n\n"
    if not_found:
        msg += "❌ <b>ɴᴏᴛ ꜰᴏᴜɴᴅ:</b> " + ", ".join(not_found)
    safe_send_long(ADMIN_ID, msg)




def _shift_platform_keyboard(prefix):
    # Reply Keyboard version for admin shift flow
    return _admin_platform_keyboard()


def _shift_subcat_keyboard(platform, prefix):
    # Reply Keyboard version for admin shift flow
    return _admin_subcat_keyboard(platform)


def _shift_ig_type_keyboard(prefix):
    # Reply Keyboard version for admin shift flow
    return _admin_ig_follow_keyboard()


def _get_services_for_shift(subcat, ig_follow_filter=None):
    result = []
    services_db = load_json(SERVICES_FILE)
    added_db = load_json(ADDED_SERVICES_FILE)

    if isinstance(services_db.get(subcat), dict):
        for sid, val in services_db.get(subcat, {}).items():
            name = val[0] if isinstance(val, list) and val else "Unknown"
            if subcat == "ig_followers" and ig_follow_filter:
                # old services.json entries me type saved nahi hota, name se best match
                if not _match_ig_follower_filter(str(name), "", ig_follow_filter):
                    continue
            result.append({"sid": str(sid), "name": str(name), "source": "services"})

    for sid, item in added_db.items():
        item_subcat = item.get("subcat", "")
        if subcat == "ig_followers":
            if item_subcat != "ig_followers" and not str(item_subcat).startswith("ig_followers_"):
                continue
            saved_ft = item.get("ig_follow_type", "")
            if not saved_ft and str(item_subcat).startswith("ig_followers_"):
                saved_ft = str(item_subcat).replace("ig_followers_", "", 1)
            if ig_follow_filter:
                if saved_ft and saved_ft != ig_follow_filter:
                    continue
                if not saved_ft and not _match_ig_follower_filter(str(item.get("name", "")), str(item.get("panel_name", "")), ig_follow_filter):
                    continue
        elif item_subcat != subcat:
            continue
        result.append({"sid": str(sid), "name": str(item.get("name", "Unknown")), "source": "added"})

    # duplicate id ko ek baar dikhana
    seen = set()
    unique = []
    for x in result:
        if x["sid"] in seen:
            continue
        seen.add(x["sid"])
        unique.append(x)
    return unique


def start_service_shift_flow(message=None):
    admin_state[ADMIN_ID] = {"shift_flow": True, "shift_mode": "source_platform"}
    bot.send_message(
        ADMIN_ID,
        "🔁 <b>ꜱᴇʀᴠɪᴄᴇ ꜱʜɪꜰᴛ</b>\n\n"
        "📌 <b>ᴘʜʟᴇ ᴡᴏ ᴘʟᴀᴛꜰᴏʀᴍ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ ᴊᴀʜᴀ ꜱᴇ ꜱᴇʀᴠɪᴄᴇ ꜱʜɪꜰᴛ ᴋᴀʀɴᴀ ʜᴀɪ.</b>",
        parse_mode="HTML",
        reply_markup=_shift_platform_keyboard("shift_srcplat_")
    )


def show_shift_source_subcategories(message, platform):
    state = admin_state.get(ADMIN_ID, {})
    state["shift_source_platform"] = platform
    state["shift_mode"] = "source_subcat"
    admin_state[ADMIN_ID] = state
    bot.send_message(
        ADMIN_ID,
        f"📂 <b>ꜱᴏᴜʀᴄᴇ ꜱᴜʙ-ᴄᴀᴛᴇɢᴏʀʏ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ</b>\n\n📦 <b>ᴘʟᴀᴛꜰᴏʀᴍ »</b> {ADD_SERVICE_CATS.get(platform, {}).get('title', platform)}",
        parse_mode="HTML",
        reply_markup=_shift_subcat_keyboard(platform, "shift_srccat_")
    )


def show_shift_source_ig_follow_types(message):
    state = admin_state.get(ADMIN_ID, {})
    state["shift_mode"] = "source_igft"
    admin_state[ADMIN_ID] = state
    bot.send_message(
        ADMIN_ID,
        "👥 <b>ꜱᴏᴜʀᴄᴇ ꜰᴏʟʟᴏᴡᴇʀꜱ ᴛʏᴘᴇ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ</b>",
        parse_mode="HTML",
        reply_markup=_shift_ig_type_keyboard("shift_srcigft_")
    )


def show_shift_service_list(message, subcat, ig_follow_type=None):
    state = admin_state.get(ADMIN_ID, {})
    state["shift_source_subcat"] = subcat
    state["shift_source_ig_follow_type"] = ig_follow_type or ""
    state["shift_mode"] = "service_select"

    services = _get_services_for_shift(subcat, ig_follow_type)
    if not services:
        bot.send_message(ADMIN_ID, "❌ <b>ɪꜱ ᴄᴀᴛᴇɢᴏʀʏ ᴍᴇ ᴋᴏɪ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ᴍɪʟɪ.</b>", parse_mode="HTML")
        return

    labels = []
    text_map = {}
    for i, item in enumerate(services[:80], 1):
        name = item["name"].replace("<b>", "").replace("</b>", "")
        if len(name) > 45:
            name = name[:42] + "..."
        label_btn = f"{i}. {item['sid']} » {name}"
        labels.append(label_btn)
        text_map[label_btn] = str(item["sid"])

    state["shift_service_text_map"] = text_map
    admin_state[ADMIN_ID] = state
    mk = _admin_flow_keyboard(labels, row_width=1)

    label = subcat
    for cfg in ADD_SERVICE_CATS.values():
        if subcat in cfg.get("subs", {}):
            label = cfg["subs"][subcat]
            break
    if ig_follow_type:
        label = f"{label} / {_IG_FOLLOW_TYPE_LABELS.get(ig_follow_type, ig_follow_type)}"

    bot.send_message(
        ADMIN_ID,
        f"📦 <b>ᴋᴏᴜɴ ꜱᴀ ꜱᴇʀᴠɪᴄᴇ ꜱʜɪꜰᴛ ᴋᴀʀɴᴀ ʜᴀɪ?</b>\n\n📁 <b>ꜱᴏᴜʀᴄᴇ »</b> {label}",
        parse_mode="HTML",
        reply_markup=mk
    )


def choose_shift_destination_platform(message, sid):
    state = admin_state.get(ADMIN_ID, {})
    state["shift_sid"] = str(sid)
    state["shift_mode"] = "dest_platform"
    admin_state[ADMIN_ID] = state
    bot.send_message(
        ADMIN_ID,
        f"📍 <b>ᴀʙ ᴊᴀʜᴀ ꜱʜɪꜰᴛ ᴋᴀʀɴᴀ ʜᴀɪ ᴡᴏ ᴘʟᴀᴛꜰᴏʀᴍ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ.</b>\n\n🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(str(sid))}</code>",
        parse_mode="HTML",
        reply_markup=_shift_platform_keyboard("shift_dstplat_")
    )


def show_shift_destination_subcategories(message, platform):
    state = admin_state.get(ADMIN_ID, {})
    state["shift_destination_platform"] = platform
    state["shift_mode"] = "dest_subcat"
    admin_state[ADMIN_ID] = state
    bot.send_message(
        ADMIN_ID,
        f"📁 <b>ᴅᴇꜱᴛɪɴᴀᴛɪᴏɴ ꜱᴜʙ-ᴄᴀᴛᴇɢᴏʀʏ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ</b>\n\n📦 <b>ᴘʟᴀᴛꜰᴏʀᴍ »</b> {ADD_SERVICE_CATS.get(platform, {}).get('title', platform)}",
        parse_mode="HTML",
        reply_markup=_shift_subcat_keyboard(platform, "shift_dstcat_")
    )


def show_shift_destination_ig_follow_types(message):
    state = admin_state.get(ADMIN_ID, {})
    state["shift_mode"] = "dest_igft"
    admin_state[ADMIN_ID] = state
    bot.send_message(
        ADMIN_ID,
        "👥 <b>ᴅᴇꜱᴛɪɴᴀᴛɪᴏɴ ꜰᴏʟʟᴏᴡᴇʀꜱ ᴛʏᴘᴇ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ</b>",
        parse_mode="HTML",
        reply_markup=_shift_ig_type_keyboard("shift_dstigft_")
    )


def finish_service_shift(message, new_cat, new_ig_follow_type=None):
    state = admin_state.get(ADMIN_ID, {})
    sid = str(state.get("shift_sid", "")).strip()
    if not sid:
        bot.send_message(ADMIN_ID, "❌ <b>ꜱᴇʀᴠɪᴄᴇ ꜱᴇʟᴇᴄᴛ ɴᴀʜɪ ʜᴜᴀ. ᴅᴏʙᴀʀᴀ ᴛʀʏ ᴋᴀʀᴏ.</b>", parse_mode="HTML")
        return

    services_db = load_json(SERVICES_FILE)
    added_db = load_json(ADDED_SERVICES_FILE)

    old_cat = ""
    name = "Unknown"
    moved = False

    if sid in added_db:
        old_cat = added_db[sid].get("subcat", "")
        name = added_db[sid].get("name", "Unknown")
        added_db[sid]["subcat"] = new_cat
        added_db[sid]["ig_follow_type"] = new_ig_follow_type or ""
        added_db[sid]["name"] = ensure_platform_in_service_name(name, new_cat)
        save_json(ADDED_SERVICES_FILE, added_db)
        moved = True
    else:
        for cat, items in list(services_db.items()):
            if isinstance(items, dict) and sid in items:
                old_cat = cat
                val = items.pop(sid)
                name = val[0] if isinstance(val, list) and val else "Unknown"
                if new_cat == "ig_followers" and new_ig_follow_type:
                    # services.json me follower type save nahi hota, isliye added_services me shift karte hain.
                    added_db[sid] = {
                        "name": ensure_platform_in_service_name(name, new_cat),
                        "subcat": new_cat,
                        "ig_follow_type": new_ig_follow_type,
                        "panel_name": name,
                        "margin": get_margin(sid),
                        "price": float(val[1]) if isinstance(val, list) and len(val) > 1 else 0,
                        "date": datetime.now().strftime("%d-%m-%Y %I:%M %p")
                    }
                    save_json(ADDED_SERVICES_FILE, added_db)
                else:
                    services_db.setdefault(new_cat, {})[sid] = val
                save_json(SERVICES_FILE, services_db)
                moved = True
                break

    if not moved:
        bot.send_message(ADMIN_ID, f"❌ <b>ꜱᴇʀᴠɪᴄᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ:</b> <code>{html.escape(sid)}</code>", parse_mode="HTML")
        return

    new_label = new_cat
    for cfg in ADD_SERVICE_CATS.values():
        if new_cat in cfg.get("subs", {}):
            new_label = cfg["subs"][new_cat]
            break
    if new_ig_follow_type:
        new_label = f"{new_label} / {_IG_FOLLOW_TYPE_LABELS.get(new_ig_follow_type, new_ig_follow_type)}"

    bot.send_message(
        ADMIN_ID,
        "✅ <b>ꜱᴇʀᴠɪᴄᴇ ꜱʜɪꜰᴛᴇᴅ</b>\n\n"
        f"🆔 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{html.escape(sid)}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(str(name))}\n"
        f"📁 <b>ᴏʟᴅ »</b> <code>{html.escape(str(old_cat))}</code>\n"
        f"📁 <b>ɴᴇᴡ »</b> {new_label}",
        parse_mode="HTML"
    )
    admin_state.pop(ADMIN_ID, None)


def process_shift_service_category(message):
    # Old manual method bhi rakha hai: 5031 ig_followers
    if message.chat.id != ADMIN_ID:
        return

    raw = (message.text or "").replace(",", " ").strip()
    if not raw:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ɪɴᴘᴜᴛ</b>", parse_mode="HTML")
        return

    try:
        if "=" in raw and len(raw.split()) == 1:
            sid, new_cat = raw.split("=", 1)
        else:
            parts = raw.split()
            sid, new_cat = parts[0], parts[1]
        sid = str(sid).strip()
        new_cat = str(new_cat).strip()
    except Exception:
        bot.send_message(ADMIN_ID, "❌ <b>ꜰᴏʀᴍᴀᴛ:</b> <code>5031 ig_followers</code>", parse_mode="HTML")
        return

    admin_state[ADMIN_ID] = {"shift_sid": sid}
    finish_service_shift(message, new_cat)

def show_panel_balance():
    """Panel balance show karta hai agar panel API support kare."""
    try:
        response = requests.post(SMM_API_URL, data={"key": SMM_API_KEY, "action": "balance"}, timeout=15).json()
        balance = response.get("balance", response.get("funds", "Unknown"))
        currency = response.get("currency", "")
        bot.send_message(ADMIN_ID, f"💳 <b>ᴘᴀɴᴇʟ ʙᴀʟᴀɴᴄᴇ</b>\n\n💰 <b>ʙᴀʟᴀɴᴄᴇ:</b> {balance} {currency}", parse_mode="HTML")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>ᴘᴀɴᴇʟ ʙᴀʟᴀɴᴄᴇ ᴇʀʀᴏʀ:</b> {html.escape(str(e))}", parse_mode="HTML")


def log_admin_action(action, details=""):
    try:
        logs = load_json(ADMIN_LOG_FILE)
        key = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
        logs[key] = {
            "action": str(action),
            "details": str(details)[:1000]
        }
        # last 300 logs only
        if len(logs) > 300:
            logs = dict(list(logs.items())[-300:])
        save_json(ADMIN_LOG_FILE, logs)
    except Exception as e:
        print("admin log error:", e)


def show_admin_action_logs():
    logs = load_json(ADMIN_LOG_FILE)
    if not logs:
        bot.send_message(ADMIN_ID, "📝 <b>ᴀᴅᴍɪɴ ʟᴏɢꜱ ᴇᴍᴘᴛʏ</b>", parse_mode="HTML")
        return

    msg = "📝 <b>ᴀᴅᴍɪɴ ᴀᴄᴛɪᴏɴ ʟᴏɢꜱ</b>\n\n"
    for t, row in list(logs.items())[-30:]:
        msg += f"📅 <b>{html.escape(str(t))}</b>\n"
        msg += f"⚙️ {html.escape(str(row.get('action','')))}\n"
        if row.get("details"):
            msg += f"📌 {html.escape(str(row.get('details','')))}\n"
        msg += "\n"
    safe_send_long(ADMIN_ID, msg)


def clean_admin_logs():
    save_json(ADMIN_LOG_FILE, {})
    bot.send_message(ADMIN_ID, "🧹 <b>ᴀᴅᴍɪɴ ʟᴏɢꜱ ᴄʟᴇᴀɴᴇᴅ</b>", parse_mode="HTML")


def start_bulk_margin_editor(message):
    msg = bot.send_message(
        ADMIN_ID,
        "🧮 <b>ʙᴜʟᴋ ᴍᴀʀɢɪɴ ᴇᴅɪᴛᴏʀ</b>\n\n"
        "Format:\n"
        "<code>1051=2 559=12 4123=1.5</code>\n\n"
        "Ya same margin:\n"
        "<code>1051 559 4123 | 2</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_bulk_margin_update)


def process_bulk_margin_update(message):
    if message.chat.id != ADMIN_ID:
        return

    raw = (message.text or "").strip()
    if not raw:
        bot.send_message(ADMIN_ID, "❌ <b>ᴇᴍᴘᴛʏ ɪɴᴘᴜᴛ</b>", parse_mode="HTML")
        return

    updates = {}
    try:
        if "|" in raw:
            left, margin_text = raw.split("|", 1)
            margin = float(margin_text.strip())
            ids = left.replace(",", " ").replace("\n", " ").split()
            for sid in ids:
                updates[str(sid).strip()] = margin
        else:
            for part in raw.replace(",", " ").replace("\n", " ").split():
                if "=" not in part:
                    continue
                sid, margin = part.split("=", 1)
                updates[str(sid).strip()] = float(margin.strip())
    except Exception:
        bot.send_message(ADMIN_ID, "❌ <b>ɪɴᴠᴀʟɪᴅ ʙᴜʟᴋ ᴍᴀʀɢɪɴ ꜰᴏʀᴍᴀᴛ</b>", parse_mode="HTML")
        return

    if not updates:
        bot.send_message(ADMIN_ID, "❌ <b>ɴᴏ ᴠᴀʟɪᴅ ᴜᴘᴅᴀᴛᴇꜱ</b>", parse_mode="HTML")
        return

    margins = load_json(MARGINS_FILE)
    msg = "✅ <b>ʙᴜʟᴋ ᴍᴀʀɢɪɴ ᴜᴘᴅᴀᴛᴇᴅ</b>\n\n"
    done = 0
    for sid, margin in updates.items():
        if not find_service(sid):
            msg += f"❌ <code>{sid}</code> » ɴᴏᴛ ꜰᴏᴜɴᴅ\n"
            continue
        margins[str(sid)] = float(margin)
        done += 1
        msg += f"✅ <code>{sid}</code> » ×{float(margin):.2f}\n"

    save_json(MARGINS_FILE, margins)
    log_admin_action("bulk_margin", f"{done} services updated")
    safe_send_long(ADMIN_ID, msg)


def show_service_health_report():
    all_services = get_all_bot_services_map()
    panel = get_all_panel_services()
    panel_ids = {str(s.get("service")) for s in panel}
    panel_rates = {str(s.get("service")): float(s.get("rate", 0) or 0) for s in panel}

    missing = []
    zero_price = []
    no_margin = []
    high_margin = []

    for sid, item in all_services.items():
        sid = str(sid)
        if sid not in panel_ids:
            missing.append((sid, item.get("name", "Unknown")))
        if sid in panel_rates and panel_rates[sid] <= 0:
            zero_price.append((sid, item.get("name", "Unknown")))
        margin = get_service_multiplier(sid)
        if margin <= 1:
            no_margin.append((sid, margin))
        if margin >= 100:
            high_margin.append((sid, margin))

    msg = (
        "🩺 <b>ꜱᴇʀᴠɪᴄᴇ ʜᴇᴀʟᴛʜ ʀᴇᴘᴏʀᴛ</b>\n\n"
        f"📦 <b>ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇꜱ:</b> {len(all_services)}\n"
        f"❌ <b>ᴘᴀɴᴇʟ ᴍɪꜱꜱɪɴɢ:</b> {len(missing)}\n"
        f"0️⃣ <b>ᴢᴇʀᴏ ᴘʀɪᴄᴇ:</b> {len(zero_price)}\n"
        f"⚠️ <b>ɴᴏ/ʟᴏᴡ ᴍᴀʀɢɪɴ:</b> {len(no_margin)}\n"
        f"🔥 <b>ʜɪɢʜ ᴍᴀʀɢɪɴ:</b> {len(high_margin)}\n\n"
    )

    if missing:
        msg += "❌ <b>ᴍɪꜱꜱɪɴɢ ꜱᴀᴍᴘʟᴇ</b>\n"
        for sid, name in missing[:30]:
            msg += f"🆔 <code>{sid}</code> » {html.escape(str(name))}\n"
        msg += "\n"

    if no_margin:
        msg += "⚠️ <b>ʟᴏᴡ ᴍᴀʀɢɪɴ ꜱᴀᴍᴘʟᴇ</b>\n"
        for sid, margin in no_margin[:30]:
            msg += f"🆔 <code>{sid}</code> » ×{float(margin):.2f}\n"

    safe_send_long(ADMIN_ID, msg)


def export_services_csv():
    try:
        all_services = get_all_bot_services_map()
        csv_name = f"services_export_{datetime.now().strftime('%d%m%Y_%H%M%S')}.csv"
        with open(csv_name, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["service_id", "name", "subcat", "source", "margin", "price"])
            for sid, item in all_services.items():
                writer.writerow([
                    sid,
                    item.get("name", ""),
                    item.get("subcat", ""),
                    item.get("source", ""),
                    get_service_multiplier(sid),
                    item.get("price", "")
                ])
        with open(csv_name, "rb") as doc:
            bot.send_document(ADMIN_ID, doc, caption="📤 <b>ꜱᴇʀᴠɪᴄᴇꜱ ᴇxᴘᴏʀᴛ</b>", parse_mode="HTML")
        os.remove(csv_name)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ <b>ᴇxᴘᴏʀᴛ ᴇʀʀᴏʀ:</b> {html.escape(str(e))}", parse_mode="HTML")


def process_pin_service(message):
    if message.chat.id != ADMIN_ID:
        return
    ids = (message.text or "").replace(",", " ").split()
    pinned = load_json(PINNED_SERVICES_FILE)
    added = 0
    for sid in ids:
        sid = str(sid).strip()
        if find_service(sid):
            pinned[sid] = datetime.now().strftime("%d-%m-%Y %I:%M %p")
            added += 1
    save_json(PINNED_SERVICES_FILE, pinned)
    bot.send_message(ADMIN_ID, f"📌 <b>{added} ꜱᴇʀᴠɪᴄᴇꜱ ᴘɪɴɴᴇᴅ</b>", parse_mode="HTML")


def process_remove_pin_service(message):
    if message.chat.id != ADMIN_ID:
        return

    ids = (message.text or "").replace(",", " ").split()
    pinned = load_json(PINNED_SERVICES_FILE)
    removed = 0

    for sid in ids:
        sid = str(sid).strip()
        if sid in pinned:
            pinned.pop(sid, None)
            removed += 1

    save_json(PINNED_SERVICES_FILE, pinned)
    bot.send_message(ADMIN_ID, f"🗑️ <b>{removed} ᴘɪɴɴᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ ʀᴇᴍᴏᴠᴇᴅ</b>", parse_mode="HTML")


def show_pinned_services(user_id):
    pinned = load_json(PINNED_SERVICES_FILE)
    if not pinned:
        bot.send_message(user_id, "📌 <b>ɴᴏ ᴘɪɴɴᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ</b>", parse_mode="HTML")
        return

    msg = "📌 <b>ᴘɪɴɴᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n\n"
    valid_ids = []

    for sid in list(pinned.keys())[:50]:
        s = find_service(sid)
        if not s:
            continue

        valid_ids.append(str(sid))
        price = get_selling_price_for_user(sid, user_id) or (s[1] if isinstance(s, list) and len(s) > 1 else 0)
        msg += f"🆔 <code>{sid}</code> » <b>{html.escape(str(s[0]))}</b>\n💎 ₹{float(price):.2f}/1000\n\n"

    if not valid_ids:
        bot.send_message(user_id, "📌 <b>ɴᴏ ᴠᴀʟɪᴅ ᴘɪɴɴᴇᴅ ꜱᴇʀᴠɪᴄᴇꜱ</b>", parse_mode="HTML")
        return

    search_results[user_id] = valid_ids

    markup = types.InlineKeyboardMarkup(row_width=1)
    if len(valid_ids) == 1:
        markup.add(types.InlineKeyboardButton("🛒 ʙᴜʏ ɴᴏᴡ", callback_data=f"srv_{valid_ids[0]}"))
    else:
        markup.add(types.InlineKeyboardButton("🛒 ʙᴜʏ ɴᴏᴡ", callback_data="search_buy_now"))

    bot.send_message(user_id, msg[:4000], parse_mode="HTML", reply_markup=markup)


def record_recent_service(user_id, sid):
    try:
        db = load_json(RECENT_SERVICES_FILE)
        uid = str(user_id)
        arr = db.get(uid, [])
        sid = str(sid)
        if sid in arr:
            arr.remove(sid)
        arr.insert(0, sid)
        db[uid] = arr[:20]
        save_json(RECENT_SERVICES_FILE, db)
    except Exception as e:
        print("recent service error:", e)


def show_recent_services(user_id):
    db = load_json(RECENT_SERVICES_FILE)
    arr = db.get(str(user_id), [])
    if not arr:
        bot.send_message(user_id, "🕒 <b>ɴᴏ ʀᴇᴄᴇɴᴛ ꜱᴇʀᴠɪᴄᴇꜱ</b>", parse_mode="HTML")
        return
    msg = "🕒 <b>ʀᴇᴄᴇɴᴛ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n\n"
    for sid in arr[:20]:
        s = find_service(sid)
        if not s:
            continue
        msg += f"🆔 <code>{sid}</code> » <b>{html.escape(str(s[0]))}</b>\n"
    safe_send_long(user_id, msg)


def add_favorite_service(user_id, sid):
    db = load_json(FAVORITES_FILE)
    uid = str(user_id)
    sid = str(sid)
    arr = db.get(uid, [])

    if sid not in arr:
        arr.insert(0, sid)

    db[uid] = arr[:50]
    save_json(FAVORITES_FILE, db)


def remove_favorite_service(user_id, sid):
    db = load_json(FAVORITES_FILE)
    uid = str(user_id)
    sid = str(sid)
    arr = db.get(uid, [])

    if sid in arr:
        arr.remove(sid)

    db[uid] = arr
    save_json(FAVORITES_FILE, db)


def show_favorite_services(user_id):
    db = load_json(FAVORITES_FILE)
    arr = db.get(str(user_id), [])

    if not arr:
        bot.send_message(user_id, "⭐ <b>ᴀʙʜɪ ᴋᴏɪ ꜰᴀᴠᴏᴜʀɪᴛᴇ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ʜᴀɪ.</b>", parse_mode="HTML")
        return

    msg = "⭐ <b>ʏᴏᴜʀ ꜰᴀᴠᴏᴜʀɪᴛᴇ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n\n"
    valid_ids = []

    for sid in arr[:30]:
        s = find_service(sid)
        if not s:
            continue

        valid_ids.append(str(sid))
        price = get_selling_price_for_user(sid, user_id) or (s[1] if isinstance(s, list) and len(s) > 1 else 0)
        name = html.escape(str(s[0]))
        msg += f"🆔 <code>{sid}</code> » <b>{name}</b>\n💎 ₹{float(price):.2f}/1000\n\n"

    if not valid_ids:
        bot.send_message(user_id, "⭐ <b>ᴀʙʜɪ ᴋᴏɪ ᴠᴀʟɪᴅ ꜰᴀᴠᴏᴜʀɪᴛᴇ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ʜᴀɪ.</b>", parse_mode="HTML")
        return

    search_results[user_id] = valid_ids

    markup = types.InlineKeyboardMarkup(row_width=1)
    if len(valid_ids) == 1:
        markup.add(types.InlineKeyboardButton("🛒 ʙᴜʏ ɴᴏᴡ", callback_data=f"srv_{valid_ids[0]}"))
    else:
        markup.add(types.InlineKeyboardButton("🛒 ʙᴜʏ ɴᴏᴡ", callback_data="search_buy_now"))
    markup.add(types.InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ", callback_data="fav_remove_menu"))

    bot.send_message(user_id, msg[:4000], parse_mode="HTML", reply_markup=markup)


def process_favorite_remove_id(message):
    user_id = message.chat.id

    if not getattr(message, "text", None):
        return

    sid = str(message.text).strip()
    favs = load_json(FAVORITES_FILE)
    arr = favs.get(str(user_id), [])

    if sid not in arr:
        bot.send_message(user_id, "❌ <b>ʏᴇ ꜱᴇʀᴠɪᴄᴇ ᴀᴀᴘᴋᴇ ꜰᴀᴠᴏᴜʀɪᴛᴇ ᴍᴇ ɴᴀʜɪ ʜᴀɪ.</b>", parse_mode="HTML")
        return

    remove_favorite_service(user_id, sid)
    bot.send_message(user_id, f"🗑️ <b>ꜱᴇʀᴠɪᴄᴇ ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{sid}</code>", parse_mode="HTML")
    show_favorite_services(user_id)


def show_user_top_services(user_id):
    orders = load_json(ORDERS_FILE)
    counter = Counter()

    for uid, user_orders_list in orders.items():
        for order in user_orders_list:
            sid = str(order.get("srv_id") or order.get("service") or "")
            if sid:
                counter[sid] += 1

    if not counter:
        bot.send_message(user_id, "🔥 <b>ɴᴏ ᴛᴏᴘ ꜱᴇʀᴠɪᴄᴇꜱ ʏᴇᴛ</b>", parse_mode="HTML")
        return

    top_ids = []
    msg = "🔥 <b>ᴛᴏᴘ ꜱᴇʀᴠɪᴄᴇꜱ</b>\n\n"

    for rank, (sid, total) in enumerate(counter.most_common(10), 1):
        s = find_service(sid)
        if not s:
            continue

        top_ids.append(str(sid))
        name = html.escape(str(s[0]))
        price = get_selling_price_for_user(sid, user_id) or (s[1] if isinstance(s, list) and len(s) > 1 else 0)
        msg += (
            f"{rank}. 🆔 <code>{sid}</code> » <b>{name}</b>\n"
            f"💎 <b>ᴘʀɪᴄᴇ:</b> ₹{float(price):.2f}/1000\n"
            f"📦 <b>ᴏʀᴅᴇʀꜱ:</b> {total}\n\n"
        )

    if not top_ids:
        bot.send_message(user_id, "🔥 <b>ɴᴏ ᴠᴀʟɪᴅ ᴛᴏᴘ ꜱᴇʀᴠɪᴄᴇꜱ</b>", parse_mode="HTML")
        return

    search_results[user_id] = top_ids

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🛒 ʙᴜʏ ɴᴏᴡ", callback_data="search_buy_now"))

    bot.send_message(user_id, msg[:4000], parse_mode="HTML", reply_markup=markup)



def show_ticket_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ ᴄʀᴇᴀᴛᴇ ᴛɪᴄᴋᴇᴛ", callback_data="ticket_create"),
        types.InlineKeyboardButton("📋 ᴄʜᴇᴄᴋ ᴛɪᴄᴋᴇᴛ ꜱᴛᴀᴛᴜꜱ", callback_data="ticket_status")
    )
    bot.send_message(
        user_id,
        "🎫 <b>ᴛɪᴄᴋᴇᴛ ꜱᴜᴘᴘᴏʀᴛ</b>\n\n"
        "➕ <b>ᴄʀᴇᴀᴛᴇ ᴛɪᴄᴋᴇᴛ</b> » ɴᴇᴡ ᴘʀᴏʙʟᴇᴍ ʙʜᴇᴊᴇɴ\n"
        "📋 <b>ᴄʜᴇᴄᴋ ꜱᴛᴀᴛᴜꜱ</b> » ᴀᴅᴍɪɴ ʀᴇᴘʟʏ ᴅᴇᴋʜᴇɴ",
        parse_mode="HTML",
        reply_markup=markup
    )


def start_create_ticket(message):
    user_id = message.chat.id
    bot.clear_step_handler_by_chat_id(user_id)
    msg = bot.send_message(
        user_id,
        "✍️ <b>ᴀᴘɴɪ ᴘʀᴏʙʟᴇᴍ / ᴍᴇꜱꜱᴀɢᴇ ʟɪᴋʜᴇɴ:</b>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_create_ticket)


def process_create_ticket(message):
    user_id = message.chat.id

    if not getattr(message, "text", None):
        bot.send_message(user_id, "❌ <b>ᴛᴇxᴛ ᴍᴇꜱꜱᴀɢᴇ ʙʜᴇᴊᴏ.</b>", parse_mode="HTML")
        return

    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return

    db = load_json(TICKETS_FILE)
    ticket_id = str(int(time.time())) + str(user_id)[-4:]

    user_name = message.from_user.first_name or "Unknown"
    username = message.from_user.username or "No Username"
    text = message.text.strip()

    db[ticket_id] = {
        "user_id": str(user_id),
        "name": user_name,
        "username": username,
        "message": text,
        "reply": "",
        "status": "open",
        "created": datetime.now().strftime("%d-%m-%Y %I:%M %p"),
        "updated": datetime.now().strftime("%d-%m-%Y %I:%M %p")
    }
    save_json(TICKETS_FILE, db)

    bot.send_message(
        user_id,
        f"✅ <b>ᴛɪᴄᴋᴇᴛ ᴄʀᴇᴀᴛᴇᴅ</b>\n\n🆔 <b>ᴛɪᴄᴋᴇᴛ ɪᴅ:</b> <code>{ticket_id}</code>\n⏳ <b>ꜱᴛᴀᴛᴜꜱ:</b> ᴏᴘᴇɴ",
        parse_mode="HTML"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("✍️ ʀᴇᴘʟʏ", callback_data=f"admin_reply_ticket_{ticket_id}"))

    bot.send_message(
        ADMIN_ID,
        f"🎫 <b>ɴᴇᴡ ᴛɪᴄᴋᴇᴛ</b>\n\n"
        f"🆔 <b>ᴛɪᴄᴋᴇᴛ:</b> <code>{ticket_id}</code>\n"
        f"👤 <b>ᴜꜱᴇʀ:</b> {html.escape(user_name)} (@{html.escape(username)})\n"
        f"🆔 <b>ᴜɪᴅ:</b> <code>{user_id}</code>\n\n"
        f"💬 <b>ᴍᴇꜱꜱᴀɢᴇ:</b>\n{format_relay_text_html(text)}",
        parse_mode="HTML",
        reply_markup=markup
    )


def show_ticket_status(user_id):
    db = load_json(TICKETS_FILE)
    user_tickets = []

    for tid, item in db.items():
        if str(item.get("user_id")) == str(user_id):
            user_tickets.append((tid, item))

    if not user_tickets:
        bot.send_message(user_id, "📋 <b>ᴀʙʜɪ ᴋᴏɪ ᴛɪᴄᴋᴇᴛ ɴᴀʜɪ ʜᴀɪ.</b>", parse_mode="HTML")
        return

    msg = "📋 <b>ʏᴏᴜʀ ᴛɪᴄᴋᴇᴛ ꜱᴛᴀᴛᴜꜱ</b>\n\n"
    for tid, item in user_tickets[-10:]:
        status = item.get("status", "open")
        reply = item.get("reply", "")
        msg += (
            f"🆔 <b>ᴛɪᴄᴋᴇᴛ:</b> <code>{tid}</code>\n"
            f"📌 <b>ꜱᴛᴀᴛᴜꜱ:</b> {format_relay_text_html(status)}\n"
            f"💬 <b>ʏᴏᴜ:</b> {format_relay_text_html(item.get('message', ''))[:1200]}\n"
        )
        if reply:
            msg += f"👨‍💻 <b>ᴀᴅᴍɪɴ ʀᴇᴘʟʏ:</b> {format_relay_text_html(reply)[:1800]}\n"
        msg += "\n"

    safe_send_long(user_id, msg)


def start_admin_ticket_reply(ticket_id):
    db = load_json(TICKETS_FILE)
    if ticket_id not in db:
        bot.send_message(ADMIN_ID, "❌ <b>ᴛɪᴄᴋᴇᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        return

    admin_state[ADMIN_ID] = {"ticket_reply_id": ticket_id}
    msg = bot.send_message(
        ADMIN_ID,
        f"✍️ <b>ᴇɴᴛᴇʀ ʀᴇᴘʟʏ ꜰᴏʀ ᴛɪᴄᴋᴇᴛ:</b> <code>{ticket_id}</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_admin_ticket_reply)


def process_admin_ticket_reply(message):
    if message.chat.id != ADMIN_ID:
        return

    if not getattr(message, "text", None):
        return

    if message.text in MENU_BUTTONS:
        handle_menu_redirection(message)
        return

    state = admin_state.get(ADMIN_ID, {})
    ticket_id = state.get("ticket_reply_id")
    if not ticket_id:
        return

    db = load_json(TICKETS_FILE)
    if ticket_id not in db:
        bot.send_message(ADMIN_ID, "❌ <b>ᴛɪᴄᴋᴇᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ</b>", parse_mode="HTML")
        admin_state.pop(ADMIN_ID, None)
        return

    reply = message.text.strip()
    db[ticket_id]["reply"] = reply
    db[ticket_id]["status"] = "answered"
    db[ticket_id]["updated"] = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    save_json(TICKETS_FILE, db)

    target_uid = int(db[ticket_id]["user_id"])
    bot.send_message(
        target_uid,
        f"🎫 <b>ᴛɪᴄᴋᴇᴛ ʀᴇᴘʟʏ</b>\n\n🆔 <b>ᴛɪᴄᴋᴇᴛ:</b> <code>{ticket_id}</code>\n\n👨‍💻 <b>ᴀᴅᴍɪɴ:</b> {format_relay_text_html(reply)}",
        parse_mode="HTML"
    )
    bot.send_message(ADMIN_ID, "✅ <b>ʀᴇᴘʟʏ ꜱᴇɴᴛ</b>", parse_mode="HTML")
    admin_state.pop(ADMIN_ID, None)

def maintenance_menu(msg):
    kb = types.InlineKeyboardMarkup()

    kb.row(
        types.InlineKeyboardButton("🟢 ON", callback_data="maint_on"),
        types.InlineKeyboardButton("🔴 OFF", callback_data="maint_off")
    )

    bot.send_message(
        ADMIN_ID,
        "🛠️ <b>ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )

def export_funds():
    bot.send_document(
        ADMIN_ID,
        open(FUNDS_HISTORY_FILE, "rb"),
        caption="📁 Funds Export"
    )

def export_orders():
    bot.send_document(
        ADMIN_ID,
        open(ORDERS_FILE, "rb"),
        caption="📁 Orders Export"
    )

def show_price_history():

    db = load_json(PRICE_HISTORY_FILE)

    if not db:
        bot.send_message(
            ADMIN_ID,
            "❌ No History Found"
        )
        return

    msg = "📈 <b>ᴘʀɪᴄᴇ ʜɪꜱᴛᴏʀʏ</b>\n\n"

    for date, item in list(db.items())[-5:]:

        msg += f"📅 <b>{date}</b>\n"

        for x in item["increased"]:
            msg += "⬆️ " + x + "\n"

        for x in item["decreased"]:
            msg += "⬇️ " + x + "\n"

        msg += "\n"

    bot.send_message(
        ADMIN_ID,
        msg[:4000],
        parse_mode="HTML"
    )

def check_missing_services():
    try:
        panel_services = requests.post(
            SMM_API_URL,
            data={"key": SMM_API_KEY, "action": "services"},
            timeout=15
        ).json()

        panel_ids = [str(s.get("service")) for s in panel_services]

        missing = []

        for cat, items in SERVICES.items():
            for sid, info in items.items():
                if str(sid) not in panel_ids:
                    missing.append(f"🆔 {sid} » {info[0]}")

        if not missing:
            bot.send_message(ADMIN_ID, "✅ ɴᴏ ᴍɪꜱꜱɪɴɢ ꜱᴇʀᴠɪᴄᴇꜱ")
            return

        msg = "⚠️ ᴍɪꜱꜱɪɴɢ ꜱᴇʀᴠɪᴄᴇꜱ\n\n" + "\n".join(missing[:100])
        bot.send_message(ADMIN_ID, msg)

    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ ᴇʀʀᴏʀ: {e}")

def process_admin_search_user(message):
    if message.chat.id != ADMIN_ID:
        return

    uid = str(message.text).strip()
    db = load_json(DB_FILE)
    orders_db = load_json(ORDERS_FILE)

    if uid not in db:
        bot.send_message(ADMIN_ID, "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
        return

    user = db[uid]
    orders = orders_db.get(uid, [])

    status = "🟢 ᴀᴄᴛɪᴠᴇ" if user.get("active", True) else "🔴 ʙᴀɴɴᴇᴅ"

    msg = (
        f"🔍 ᴜꜱᴇʀ ᴅᴇᴛᴀɪʟꜱ\n\n"
        f"🆔 ᴜꜱᴇʀ ɪᴅ : {uid}\n"
        f"👤 ɴᴀᴍᴇ : {user.get('name', 'Unknown')}\n"
        f"📛 ᴜꜱᴇʀɴᴀᴍᴇ : {user.get('username', 'No Username')}\n"
        f"💰 ʙᴀʟᴀɴᴄᴇ : ₹{user.get('balance', 0)}\n"
        f"📦 ᴛᴏᴛᴀʟ ᴏʀᴅᴇʀꜱ : {len(orders)}\n"
        f"👥 ᴛᴏᴛᴀʟ ʀᴇꜰᴇʀʀᴀʟꜱ : {user.get('referrals_count', 0)}\n"
        f"👥 ʀᴇꜰᴇʀʀᴇᴅ ʙʏ : {user.get('referred_by', 'None')}\n"
        f"📅 ʀᴇɢɪꜱᴛᴇʀᴇᴅ : {user.get('join_date', 'Unknown')}\n"
        f"🟢 ꜱᴛᴀᴛᴜꜱ:{status}"
    )

    bot.send_message(ADMIN_ID, msg)

def process_ban_user(message):
    uid = str(message.text).strip()
    db = load_json(DB_FILE)

    if uid not in db:
        bot.send_message(
            ADMIN_ID,
            "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ"
        )
        return

    db[uid]["active"] = False
    save_json(DB_FILE, db)

    bot.send_message(
        ADMIN_ID,
        f"🚫 ᴜꜱᴇʀ ʙᴀɴɴᴇᴅ\n🆔 {uid}"
    )

    try:
         bot.send_message(
        int(uid),
        "🚫 ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ʙᴀɴɴᴇᴅ ꜰʀᴏᴍ ᴜꜱɪɴɢ ᴛʜɪꜱ ʙᴏᴛ."
    )
    except:
        pass

def process_unban_user(message):
    uid = str(message.text).strip()
    db = load_json(DB_FILE)

    if uid not in db:
        bot.send_message(
            ADMIN_ID,
            "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ"
        )
        return

    db[uid]["active"] = True
    save_json(DB_FILE, db)

    bot.send_message(
        ADMIN_ID,
        f"✅ ᴜꜱᴇʀ ᴜɴʙᴀɴɴᴇᴅ\n🆔 {uid}"
    )
    try:
        bot.send_message(
        int(uid),
        "✅ ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ᴜɴʙᴀɴɴᴇᴅ.\nɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ᴜꜱᴇ ᴛʜᴇ ʙᴏᴛ."
    )
    except:
        pass

def process_msg_user(message):
    if message.chat.id != ADMIN_ID:
        return

    uid = message.text.strip()

    admin_state[ADMIN_ID] = {"target_uid": uid}

    msg = bot.send_message(
        ADMIN_ID,
        "📨 <b>ᴍᴇꜱꜱᴀɢᴇ ʏᴀ ᴘʜᴏᴛᴏ ʙʜᴇᴊᴏ:</b>\n\n"
        "📝 ᴛᴇxᴛ ʏᴀ ᴘʜᴏᴛᴏ + ᴄᴀᴘᴛɪᴏɴ ᴅᴏɴᴏ ꜱᴜᴘᴘᴏʀᴛᴇᴅ.",
        parse_mode="HTML"
    )

    bot.register_next_step_handler(msg, send_to_user)

def send_to_user(message):
    if message.chat.id != ADMIN_ID:
        return

    if ADMIN_ID not in admin_state:
        return

    uids = admin_state[ADMIN_ID]["target_uid"].split(",")

    sent = 0
    failed = 0

    for uid in uids:
        uid = uid.strip()

        if not uid.isdigit():
            failed += 1
            continue

        try:
            if message.content_type == "photo":
                bot.send_photo(
                    int(uid),
                    message.photo[-1].file_id,
                    caption=message.caption or "",
                    parse_mode="HTML"
                )

            elif message.content_type == "text":
                bot.send_message(
                    int(uid),
                    message.text,
                    parse_mode="HTML"
                )

            sent += 1

        except Exception:
            failed += 1

    bot.send_message(
        ADMIN_ID,
        f"""✅ <b>ᴍᴇꜱꜱᴀɢᴇ ꜱᴇɴᴛ!</b>

📤 <b>ꜱᴇɴᴛ :</b> {sent}
❌ <b>ꜰᴀɪʟᴇᴅ :</b> {failed}""",
        parse_mode="HTML"
    )

    admin_state.pop(ADMIN_ID, None)

def process_mass_add(message):
    try:
        ids_part, amount_part = message.text.split("|", 1)
        amount = float(amount_part.strip())
        uids = [x.strip() for x in ids_part.split(",")]

        db = load_json(DB_FILE)
        success = 0

        for uid in uids:
            if uid in db:
                db[uid]["balance"] = round(float(db[uid].get("balance", 0)) + amount, 2)
                success += 1

                try:
                    bot.send_message(
                        int(uid),
                            f"🎁 ʙᴀʟᴀɴᴄᴇ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!\n\n"
                            f"💰 ᴀᴍᴏᴜɴᴛ : ₹{amount:.2f}\n"
                            f"💳 ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ : ₹{db[uid]['balance']:.2f}\n\n"
                            f"🤖 ʟᴇɢᴇɴᴅᴀʀʏ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💎"
                    )
                except:
                    pass

                    save_json(DB_FILE, db)
                    bot.send_message(ADMIN_ID, f"✅ ᴍᴀꜱꜱ ᴀᴅᴅ ᴅᴏɴᴇ\n👥 Success: {success}\n💰 Amount: ₹{amount:.2f}")

    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ ᴇʀʀᴏʀ\n{e}")


def process_delete_user(message):
    uid = str(message.text).strip()
    db = load_json(DB_FILE)
    deleted_db = load_json(DELETED_USERS_FILE)

    if uid not in db:
        bot.send_message(ADMIN_ID, "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
        return

    user_data = db.pop(uid, {})
    user_data["deleted_at"] = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    user_data["active"] = False
    deleted_db[uid] = user_data

    save_json(DB_FILE, db)
    save_json(DELETED_USERS_FILE, deleted_db)

    bot.send_message(ADMIN_ID, f"🗑️ <b>ᴜꜱᴇʀ ᴅᴇʟᴇᴛᴇᴅ & ʙʟᴏᴄᴋᴇᴅ</b>\n🆔 <code>{uid}</code>", parse_mode="HTML")

    try:
        bot.send_message(int(uid), "🚫 <b>ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ʜᴀꜱ ʙᴇᴇɴ ᴅᴇʟᴇᴛᴇᴅ. ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ.</b>", parse_mode="HTML")
    except Exception:
        pass


def show_deleted_users_for_restore():
    deleted_db = load_json(DELETED_USERS_FILE)

    if not deleted_db:
        bot.send_message(ADMIN_ID, "✅ <b>ɴᴏ ᴅᴇʟᴇᴛᴇᴅ ᴜꜱᴇʀꜱ</b>", parse_mode="HTML")
        return

    msg_text = "♻️ <b>ᴅᴇʟᴇᴛᴇᴅ ᴜꜱᴇʀꜱ</b>\n\n"

    for uid, user in deleted_db.items():
        name = html.escape(str(user.get("name", "Unknown")))
        username = html.escape(str(user.get("username", "No Username")))
        deleted_at = user.get("deleted_at", "Unknown")
        msg_text += (
            f"🆔 <code>{uid}</code>\n"
            f"👤 <b>ɴᴀᴍᴇ:</b> {name}\n"
            f"📛 <b>ᴜꜱᴇʀɴᴀᴍᴇ:</b> @{username}\n"
            f"🕒 <b>ᴅᴇʟᴇᴛᴇᴅ:</b> {deleted_at}\n\n"
        )

    msg_text += "♻️ <b>ʀᴇꜱᴛᴏʀᴇ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ᴜꜱᴇʀ ɪᴅ ʙʜᴇᴊᴏ.</b>"
    msg = bot.send_message(ADMIN_ID, msg_text[:4000], parse_mode="HTML")
    bot.register_next_step_handler(msg, process_restore_user)


def process_restore_user(message):
    if message.chat.id != ADMIN_ID:
        return

    uid = str(message.text).strip()
    db = load_json(DB_FILE)
    deleted_db = load_json(DELETED_USERS_FILE)

    if uid not in deleted_db:
        bot.send_message(ADMIN_ID, "❌ <b>ᴅᴇʟᴇᴛᴇᴅ ʟɪꜱᴛ ᴍᴇ ʏᴇ ᴜꜱᴇʀ ɴᴀʜɪ ᴍɪʟᴀ.</b>", parse_mode="HTML")
        return

    user_data = deleted_db.pop(uid)
    user_data["active"] = True
    user_data.pop("deleted_at", None)
    db[uid] = user_data

    save_json(DB_FILE, db)
    save_json(DELETED_USERS_FILE, deleted_db)

    bot.send_message(ADMIN_ID, f"♻️ <b>ᴜꜱᴇʀ ʀᴇꜱᴛᴏʀᴇᴅ</b>\n🆔 <code>{uid}</code>", parse_mode="HTML")

    try:
        bot.send_message(int(uid), "✅ <b>ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ʜᴀꜱ ʙᴇᴇɴ ʀᴇꜱᴛᴏʀᴇᴅ. ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ᴜꜱᴇ ᴛʜᴇ ʙᴏᴛ.</b>", parse_mode="HTML")
    except Exception:
        pass


def export_users_csv():
    db = load_json(DB_FILE)

    filename = "users.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "USER ID",
            "NAME",
            "USERNAME",
            "BALANCE",
            "STATUS"
        ])

        for uid, user in db.items():
            writer.writerow([
                uid,
                user.get("name", "Unknown"),
                user.get("username", "No Username"),
                user.get("balance", 0),
                "ACTIVE" if user.get("active", True) else "BANNED"
            ])

    with open(filename, "rb") as f:
        bot.send_document(ADMIN_ID, f)

def process_add_vip(message):
    uid = str(message.text).strip()
    db = load_json(DB_FILE)

    if uid not in db:
        bot.send_message(ADMIN_ID, "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
        return

    db[uid]["vip"] = True
    save_json(DB_FILE, db)

    bot.send_message(
        ADMIN_ID,
        f"👑 ᴠɪᴘ ᴍᴇᴍʙᴇʀ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ! 💎\n\n"
        f"🎉 ᴛʜɪꜱ ᴜꜱᴇʀ ʜᴀꜱ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴘʀᴏᴍᴏᴛᴇᴅ ᴛᴏ ᴠɪᴘ ᴍᴇᴍʙᴇʀꜱʜɪᴘ ᴡɪᴛʜ ꜰᴜʟʟ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ.\n\n"
        f"🆔 ᴜꜱᴇʀ ɪᴅ » <code>{uid}</code>\n"
        f"👑 ᴍᴇᴍʙᴇʀꜱʜɪᴘ » ᴠɪᴘ\n"
        f"⚡ ꜱᴛᴀᴛᴜꜱ » ᴀᴄᴛɪᴠᴇ\n"
        f"✨ ᴀʟʟ ᴠɪᴘ ʙᴇɴᴇꜰɪᴛꜱ ᴀʀᴇ ɴᴏᴡ ᴇɴᴀʙʟᴇᴅ.",
        parse_mode="HTML"
    )

    try:
        bot.send_message(
            int(uid),
            "👑 ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴜᴘɢʀᴀᴅᴇᴅ ᴛᴏ ᴏᴜʀ ᴏꜰꜰɪᴄɪᴀʟ ᴠɪᴘ ᴍᴇᴍʙᴇʀꜱʜɪᴘ! 💎\n"
            "🎉 ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ʙᴇᴄᴏᴍɪɴɢ ᴀ ᴠᴀʟᴜᴇᴅ ᴠɪᴘ ᴍᴇᴍʙᴇʀ ᴏꜰ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ.\n"
            "✨ ʏᴏᴜʀ ᴠɪᴘ ꜱᴛᴀᴛᴜꜱ ɪꜱ ɴᴏᴡ ꜰᴜʟʟʏ ᴀᴄᴛɪᴠᴇ, ᴀɴᴅ ʏᴏᴜ ᴄᴀɴ ᴇɴᴊᴏʏ ᴘʀᴇᴍɪᴜᴍ ꜱᴇʀᴠɪᴄᴇꜱ, ꜰᴀꜱᴛᴇʀ ᴏʀᴅᴇʀ ᴘʀᴏᴄᴇꜱꜱɪɴɢ, ᴘʀɪᴏʀɪᴛʏ ꜱᴜᴘᴘᴏʀᴛ, ᴀɴᴅ ᴍᴀɴʏ ᴍᴏʀᴇ ᴇxᴄʟᴜꜱɪᴠᴇ ʙᴇɴᴇꜰɪᴛꜱ.\n"
            "🚀 ᴡᴇ ᴀʀᴇ ᴄᴏᴍᴍɪᴛᴛᴇᴅ ᴛᴏ ᴘʀᴏᴠɪᴅɪɴɢ ʏᴏᴜ ᴡɪᴛʜ ᴛʜᴇ ʙᴇꜱᴛ ᴇxᴘᴇʀɪᴇɴᴄᴇ ᴀɴᴅ ᴛᴏᴘ-Qᴜᴀʟɪᴛʏ ꜱᴇʀᴠɪᴄᴇꜱ.\n"
            "💖 ᴏɴᴄᴇ ᴀɢᴀɪɴ, ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ ᴀɴᴅ ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴄʜᴏᴏꜱɪɴɢ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ. ❤️\n"
        )
    except:
        pass


def process_remove_vip(message):
    uid = str(message.text).strip()
    db = load_json(DB_FILE)

    if uid not in db:
        bot.send_message(ADMIN_ID, "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
        return

    db[uid]["vip"] = False
    save_json(DB_FILE, db)

    bot.send_message(
        ADMIN_ID,
        f"🚫 <b>ᴠɪᴘ ᴍᴇᴍʙᴇʀꜱʜɪᴘ ʀᴇᴍᴏᴠᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n"
        f"⚠️ ᴛʜᴇ ᴜꜱᴇʀ'ꜱ ᴠɪᴘ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ʀᴇᴠᴏᴋᴇᴅ.\n\n"
        f"🆔 <b>ᴜꜱᴇʀ ɪᴅ :</b> <code>{uid}</code>\n"
        f"💎 <b>ᴘʀᴇᴠɪᴏᴜꜱ ꜱᴛᴀᴛᴜꜱ :</b> ᴠɪᴘ\n"
        f"📌 <b>ᴄᴜʀʀᴇɴᴛ ꜱᴛᴀᴛᴜꜱ :</b> ɴᴏʀᴍᴀʟ\n"
        f"✅ <b>ᴀᴄᴛɪᴏɴ :</b> ᴠɪᴘ ʀᴇᴍᴏᴠᴇᴅ",
        parse_mode="HTML"
    )

    try:
        bot.send_message(
            int(uid),
            "🚫 ʏᴏᴜʀ ᴠɪᴘ ᴍᴇᴍʙᴇʀꜱʜɪᴘ ʜᴀꜱ ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ.\n"
            "⚠️ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ɪꜱ ɴᴏᴡ ᴏɴ ᴛʜᴇ ɴᴏʀᴍᴀʟ ᴘʟᴀɴ.\n"
            "📌 ʏᴏᴜ ᴡɪʟʟ ɴᴏ ʟᴏɴɢᴇʀ ʜᴀᴠᴇ ᴀᴄᴄᴇꜱꜱ ᴛᴏ ᴠɪᴘ ᴇxᴄʟᴜꜱɪᴠᴇ ꜰᴇᴀᴛᴜʀᴇꜱ, ᴘʀᴇᴍɪᴜᴍ ʙᴇɴᴇꜰɪᴛꜱ, ᴀɴᴅ ᴘʀɪᴏʀɪᴛʏ ꜱᴜᴘᴘᴏʀᴛ.\n"
            "💎 ɪꜰ ʏᴏᴜ ᴡɪꜱʜ ᴛᴏ ʀᴇɢᴀɪɴ ᴠɪᴘ ᴀᴄᴄᴇꜱꜱ, ᴘʟᴇᴀꜱᴇ ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴀᴅᴍɪɴ.\n"
            "🙏 ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ʙᴇɪɴɢ ᴀ ᴘᴀʀᴛ ᴏꜰ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ. ᴡᴇ ʜᴏᴘᴇ ᴛᴏ ꜱᴇᴇ ʏᴏᴜ ᴀꜱ ᴀ ᴠɪᴘ ᴍᴇᴍʙᴇʀ ᴀɢᴀɪɴ ꜱᴏᴏɴ! ❤️"
        )
    except:
        pass

def process_coupon(message):
    user_id = message.chat.id
    code = message.text.strip().upper()

    auto_expire_coupons_once(notify=False)
    coupons = load_json(COUPON_FILE)

    if code not in coupons:
        bot.send_message(user_id, "❌ ɪɴᴠᴀʟɪᴅ ᴄᴏᴜᴘᴏɴ")
        return

    if is_coupon_expired(coupons.get(code, {})):
        coupons.pop(code, None)
        save_json(COUPON_FILE, coupons)
        bot.send_message(user_id, "❌ ᴄᴏᴜᴘᴏɴ ᴇxᴘɪʀᴇᴅ")
        return

    if str(user_id) in coupons[code].get("used_by", []):
        bot.send_message(user_id, "❌ ᴄᴏᴜᴘᴏɴ ᴀʟʀᴇᴀᴅʏ ᴜꜱᴇᴅ")
        return

    if len(coupons[code].get("used_by", [])) >= coupons[code].get("max_uses", 999999):
        bot.send_message(
            user_id,
            "❌ ᴄᴏᴜᴘᴏɴ ᴇxᴘɪʀᴇᴅ ᴏʀ ᴜꜱᴇ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ"
        )
        return

    amount = float(coupons[code]["amount"])

    update_balance(user_id, amount)
    log_wallet(user_id, amount, "ꜰᴜɴᴅ ᴀᴅᴅᴇᴅ")

    coupons[code]["used_by"].append(str(user_id))
    save_json(COUPON_FILE, coupons)

    bot.send_message(
        user_id,
        f"🎉 ᴄᴏᴜᴘᴏɴ ᴀᴘᴘʟɪᴇᴅ!\n"
        f"💰 ₹{amount:.2f} ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʙᴀʟʟᴀɴᴄᴇ"
    )

def log_wallet(user_id, amount, reason, order_id=None, service_id=None):
    data = load_json(WALLET_HISTORY_FILE)
    uid = str(user_id)

    if uid not in data:
        data[uid] = []

    data[uid].append({
        "amount": round(float(amount), 2),
        "reason": reason,
        "order_id": order_id,
        "service_id": service_id,
        "date": datetime.now().strftime("%d-%m-%Y %I:%M %p")
    })

    save_json(WALLET_HISTORY_FILE, data)


def get_service_name(service_id):
    s_info = find_service(str(service_id))
    return s_info[0] if s_info else "UNKNOWN SERVICE"


def is_maintenance_on():
    settings = load_json(SETTINGS_FILE)
    return settings.get("maintenance", False)


def set_maintenance(status):
    settings = load_json(SETTINGS_FILE)
    settings["maintenance"] = status
    save_json(SETTINGS_FILE, settings)

def show_statistics_dashboard():
    db = load_json(DB_FILE)
    orders_db = load_json(ORDERS_FILE)
    funds_db = load_json(FUNDS_HISTORY_FILE)

    total_users = len(db)
    active_users = sum(1 for u in db.values() if u.get("active", True))
    banned_users = total_users - active_users
    vip_users = sum(1 for u in db.values() if u.get("vip", False))

    total_orders = sum(len(v) for v in orders_db.values())
    total_revenue = 0

    for orders in orders_db.values():
        for o in orders:
            total_revenue += float(o.get("charge", 0))

    total_funds = 0
    for txns in funds_db.values():
        for t in txns:
            total_funds += float(t.get("amount", 0))

    today = datetime.now().strftime("%d-%m-%Y")
    today_users = sum(1 for u in db.values() if u.get("join_date") == today)

    msg = (
        "📊 <b>ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ</b>\n\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ :</b> {total_users}\n"
        f"🟢 <b>ᴀᴄᴛɪᴠᴇ ᴜꜱᴇʀꜱ :</b> {active_users}\n"
        f"🚫 <b>ʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ :</b> {banned_users}\n"
        f"👑 <b>ᴠɪᴘ ᴜꜱᴇʀꜱ :</b> {vip_users}\n\n"
        f"📦 <b>ᴛᴏᴛᴀʟ ᴏʀᴅᴇʀꜱ :</b> {total_orders}\n"
        f"💰 <b>ᴛᴏᴛᴀʟ ʀᴇᴠᴇɴᴜᴇ :</b> ₹{total_revenue:.2f}\n"
        f"💳 <b>ᴛᴏᴛᴀʟ ꜰᴜɴᴅꜱ :</b> ₹{total_funds:.2f}\n\n"
        f"📅 <b>ᴛᴏᴅᴀʏ ᴜꜱᴇʀꜱ :</b> {today_users}"
    )

    bot.send_message(ADMIN_ID, msg, parse_mode="HTML")


def _fund_status_label(status):
    status = str(status or "approved").lower()
    if status == "rejected":
        return "🔴 ʀᴇᴊᴇᴄᴛᴇᴅ"
    if status == "pending":
        return "🟡 ᴘᴇɴᴅɪɴɢ"
    return "🟢 ᴀᴘᴘʀᴏᴠᴇᴅ"


def _format_fund_history_text(user_id, page=1, per_page=10):
    data = load_json(FUNDS_HISTORY_FILE)
    history = data.get(str(user_id), [])

    if not history:
        return (
            "💳 <b>ᴍʏ ꜰᴜɴᴅ ʜɪꜱᴛᴏʀʏ</b>\n\n"
            "📭 <b>ɴᴏ ꜰᴜɴᴅ ʜɪꜱᴛᴏʀʏ ꜰᴏᴜɴᴅ.</b>\n\n"
            "➕ <b>ᴀᴅᴅ ꜰᴜɴᴅ ᴛᴏ ꜱᴇᴇ ʏᴏᴜʀ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ʜɪꜱᴛᴏʀʏ.</b>"
        ), None

    total_requests = len(history)
    approved = sum(1 for r in history if str(r.get("status", "approved")).lower() == "approved")
    rejected = sum(1 for r in history if str(r.get("status", "approved")).lower() == "rejected")
    total_approved = sum(float(r.get("amount", 0) or 0) for r in history if str(r.get("status", "approved")).lower() == "approved")

    history_newest = list(reversed(history))
    total_pages = max(1, (len(history_newest) + per_page - 1) // per_page)
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * per_page
    rows = history_newest[start:start + per_page]

    msg = (
        "💳 <b>ᴍʏ ꜰᴜɴᴅ ʜɪꜱᴛᴏʀʏ</b>\n\n"
        "📊 <b>ᴏᴠᴇʀᴀʟʟ ꜱᴛᴀᴛꜱ</b>\n\n"
        f"📨 <b>ᴛᴏᴛᴀʟ ʀᴇQᴜᴇꜱᴛꜱ :</b> {total_requests}\n"
        f"✅ <b>ᴀᴘᴘʀᴏᴠᴇᴅ :</b> {approved}\n"
        f"❌ <b>ʀᴇᴊᴇᴄᴛᴇᴅ :</b> {rejected}\n"
        f"💰 <b>ᴛᴏᴛᴀʟ ᴀᴘᴘʀᴏᴠᴇᴅ :</b> ₹{total_approved:.2f}\n\n"
    )

    circled = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
    for idx, txn in enumerate(rows):
        number = circled[idx] if idx < len(circled) else f"{idx+1}."
        amount = float(txn.get("amount", 0) or 0)
        date = html.escape(str(txn.get("date", "N/A")))
        utr = str(txn.get("utr", "") or "").strip()
        has_photo = bool(txn.get("has_photo", False))
        status = _fund_status_label(txn.get("status", "approved"))

        msg += f"{number} 💰 <b>₹{amount:.2f}</b>\n"
        msg += f"📅 <b>{date}</b>\n"
        if utr:
            msg += f"🆔 <b>ᴜᴛʀ :</b> <code>{html.escape(utr)}</code>\n"
        elif has_photo:
            msg += "📷 <b>ꜱᴄʀᴇᴇɴꜱʜᴏᴛ ꜱᴜʙᴍɪᴛᴛᴇᴅ</b>\n"
        else:
            msg += "🧾 <b>ᴘᴀʏᴍᴇɴᴛ ᴘʀᴏᴏꜰ : ɴ/ᴀ</b>\n"
        msg += f"{status}\n\n"

    markup = None
    if total_pages > 1:
        markup = types.InlineKeyboardMarkup(row_width=3)
        buttons = []
        if page > 1:
            buttons.append(types.InlineKeyboardButton("⬅️ ᴘʀᴇᴠɪᴏᴜꜱ", callback_data=f"fundhist_{page-1}"))
        buttons.append(types.InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data=f"fundhist_{page}"))
        if page < total_pages:
            buttons.append(types.InlineKeyboardButton("ɴᴇxᴛ ➡️", callback_data=f"fundhist_{page+1}"))
        markup.add(*buttons)

    return msg[:3900], markup


def show_fund_history(user_id, page=1, edit_message=None):
    text, markup = _format_fund_history_text(user_id, page=page)
    if edit_message is not None:
        try:
            bot.edit_message_text(text, chat_id=user_id, message_id=edit_message.message_id, parse_mode="HTML", reply_markup=markup)
            return
        except Exception as e:
            if "message is not modified" in str(e).lower():
                return
    bot.send_message(user_id, text, parse_mode="HTML", reply_markup=markup)

def show_wallet_history(user_id):
    data = load_json(WALLET_HISTORY_FILE)
    history = data.get(str(user_id), [])

    if not history:
        bot.send_message(user_id, "❌ ɴᴏ ᴡᴀʟʟᴇᴛ ʜɪꜱᴛᴏʀʏ ꜰᴏᴜɴᴅ")
        return

    msg = "💳 <b>ᴡᴀʟʟᴇᴛ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴꜱ</b>\n\n"

    for txn in history[-10:][::-1]:
        amount = float(txn.get("amount", 0))
        sign = "➕" if amount > 0 else "➖"

        msg += (
            f"{sign} <b>₹{abs(amount):.2f}</b>\n"
            f"📌 <b>ʀᴇᴀꜱᴏɴ :</b> {txn.get('reason')}\n"
        )

        if txn.get("order_id"):
            msg += f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ :</b> {txn.get('order_id')}\n"

        if txn.get("service_id"):
            msg += f"📦 <b>ꜱᴇʀᴠɪᴄᴇ :</b> {get_service_name(txn.get('service_id'))}\n"

        msg += f"📅 <b>ᴅᴀᴛᴇ :</b> {txn.get('date')}\n\n"

    bot.send_message(user_id, msg[:4000], parse_mode="HTML")

def start_schedule_broadcast(message):
    msg = bot.send_message(
        ADMIN_ID,
        "📝 <b>ᴇɴᴛᴇʀ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴍᴇꜱꜱᴀɢᴇ:</b>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, schedule_broadcast_message)


def schedule_broadcast_message(message):
    if message.chat.id != ADMIN_ID:
        return

    admin_state[ADMIN_ID] = {
        "schedule_text": message.text
    }

    msg = bot.send_message(
        ADMIN_ID,
        "🕒 <b>ᴇɴᴛᴇʀ ᴅᴀᴛᴇ & ᴛɪᴍᴇ:</b>\n\n"
        "Format: <code>DD-MM-YYYY HH:MM</code>\n"
        "Example: <code>29-06-2026 18:30</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, schedule_broadcast_time)


def schedule_broadcast_time(message):
    if message.chat.id != ADMIN_ID:
        return

    try:
        datetime.strptime(message.text.strip(), "%d-%m-%Y %H:%M")
    except:
        bot.send_message(ADMIN_ID, "❌ ɪɴᴠᴀʟɪᴅ ᴅᴀᴛᴇ ᴛɪᴍᴇ")
        return

    data = load_json(SCHEDULED_FILE)

    sid = str(int(datetime.now().timestamp()))

    data[sid] = {
        "text": admin_state[ADMIN_ID]["schedule_text"],
        "time": message.text.strip(),
        "sent": False
    }

    save_json(SCHEDULED_FILE, data)

    bot.send_message(
        ADMIN_ID,
        "✅ <b>ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱᴄʜᴇᴅᴜʟᴇᴅ</b>",
        parse_mode="HTML"
    )

    admin_state.pop(ADMIN_ID, None)

def scheduled_broadcast_checker():
    while True:
        try:
            data = load_json(SCHEDULED_FILE)
            db = load_json(DB_FILE)

            now = datetime.now()

            for sid, item in data.items():
                if item.get("sent"):
                    continue

                target_time = datetime.strptime(item["time"], "%d-%m-%Y %H:%M")

                if now >= target_time:
                    success = 0
                    failed = 0

                    for uid in db.keys():
                        try:
                            bot.send_message(
                                int(uid),
                                format_relay_text_html(item["text"]),
                                parse_mode="HTML"
                            )
                            success += 1
                        except:
                            failed += 1

                    item["sent"] = True
                    data[sid] = item
                    save_json(SCHEDULED_FILE, data)

                    bot.send_message(
                        ADMIN_ID,
                        f"📤 <b>ꜱᴄʜᴇᴅᴜʟᴇᴅ ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱᴇɴᴛ</b>\n\n"
                        f"✅ ꜱᴜᴄᴄᴇꜱꜱ : {success}\n"
                        f"❌ ꜰᴀɪʟᴇᴅ : {failed}",
                        parse_mode="HTML"
                    )

        except Exception as e:
            print("Scheduled broadcast error:", e)

        time.sleep(60)


threading.Thread(target=scheduled_broadcast_checker, daemon=True).start()



# --- USER PREMIUM TEXT FEATURES (NO IMAGE CARDS) ---
def _parse_order_datetime(value):
    for fmt in ("%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value), fmt)
        except Exception:
            pass
    return None

def _user_total_spent(user_id):
    orders = load_json(ORDERS_FILE)
    total = 0.0
    for o in orders.get(str(user_id), []):
        try:
            total += float(o.get("charge", 0) or 0)
        except Exception:
            pass
    return total

def _user_order_count(user_id):
    orders = load_json(ORDERS_FILE)
    return len(orders.get(str(user_id), []))

def _user_rank(user_id):
    spend = _user_total_spent(user_id)
    orders = _user_order_count(user_id)
    if spend >= 5000 or orders >= 100:
        return "💎 ᴅɪᴀᴍᴏɴᴅ"
    if spend >= 1000 or orders >= 50:
        return "🥇 ɢᴏʟᴅ"
    if spend >= 500 or orders >= 25:
        return "🥈 ꜱɪʟᴠᴇʀ"
    if orders >= 1:
        return "🥉 ʙʀᴏɴᴢᴇ"
    return "🌱 ɴᴇᴡ"

def show_vip_progress(user_id):
    spend = _user_total_spent(user_id)
    target = 500.0
    left = max(target - spend, 0)
    percent = min(100, int((spend / target) * 100)) if target else 0
    filled = min(10, int(percent / 10))
    bar = "█" * filled + "░" * (10 - filled)
    user = load_json(DB_FILE).get(str(user_id), {})
    vip = bool(user.get("vip", False))
    msg = (
        "💎 <b>ᴠɪᴘ ᴘʀᴏɢʀᴇꜱꜱ</b>\n\n"
        f"{bar} <b>{percent}%</b>\n\n"
        f"💸 <b>ᴛᴏᴛᴀʟ ꜱᴘᴇɴᴅ »</b> ₹{spend:.2f}\n"
        f"🎯 <b>ᴠɪᴘ ᴛᴀʀɢᴇᴛ »</b> ₹{target:.2f}\n"
        f"⏳ <b>ʀᴇᴍᴀɪɴɪɴɢ »</b> ₹{left:.2f}\n"
        f"👑 <b>ꜱᴛᴀᴛᴜꜱ »</b> {'ᴠɪᴘ ᴀᴄᴛɪᴠᴇ' if vip else 'ɴᴏʀᴍᴀʟ ᴜꜱᴇʀ'}\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>"
    )
    bot.send_message(user_id, msg, parse_mode="HTML")

def show_user_rank(user_id):
    rank = _user_rank(user_id)
    spend = _user_total_spent(user_id)
    orders = _user_order_count(user_id)
    bot.send_message(user_id, (
        "🥇 <b>ᴍʏ ʀᴀɴᴋ</b>\n\n"
        f"🏆 <b>ʀᴀɴᴋ »</b> {rank}\n"
        f"📦 <b>ᴏʀᴅᴇʀꜱ »</b> {orders}\n"
        f"💸 <b>ꜱᴘᴇɴᴅ »</b> ₹{spend:.2f}\n\n"
        "ᴍᴏʀᴇ ᴏʀᴅᴇʀꜱ = ʙᴇᴛᴛᴇʀ ʀᴀɴᴋ ✨"
    ), parse_mode="HTML")

def unlock_achievement(user_id, key, title, detail):
    data = load_json(ACHIEVEMENTS_FILE)
    if not isinstance(data, dict):
        data = {}
    uid = str(user_id)
    arr = data.get(uid, [])
    if key in arr:
        return False
    arr.append(key)
    data[uid] = arr
    save_json(ACHIEVEMENTS_FILE, data)
    try:
        bot.send_message(user_id, (
            "🏆 <b>ᴀᴄʜɪᴇᴠᴇᴍᴇɴᴛ ᴜɴʟᴏᴄᴋᴇᴅ!</b>\n\n"
            f"✨ <b>{html.escape(title)}</b>\n"
            f"📌 {html.escape(detail)}\n\n"
            "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>"
        ), parse_mode="HTML")
    except Exception:
        pass
    return True

def check_user_achievements(user_id):
    orders = _user_order_count(user_id)
    spend = _user_total_spent(user_id)
    if orders >= 1: unlock_achievement(user_id, "first_order", "ꜰɪʀꜱᴛ ᴏʀᴅᴇʀ", "ᴀᴀᴘᴋᴀ ᴘᴇʜʟᴀ ᴏʀᴅᴇʀ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴘʟᴀᴄᴇᴅ.")
    if orders >= 10: unlock_achievement(user_id, "orders_10", "10 ᴏʀᴅᴇʀꜱ", "ᴀᴀᴘɴᴇ 10 ᴏʀᴅᴇʀꜱ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋɪʏᴇ.")
    if orders >= 50: unlock_achievement(user_id, "orders_50", "50 ᴏʀᴅᴇʀꜱ", "ᴀᴀᴘ ᴘʀᴏ ᴜꜱᴇʀ ʙᴀɴ ʀᴀʜᴇ ʜᴀɪɴ.")
    if orders >= 100: unlock_achievement(user_id, "orders_100", "100 ᴏʀᴅᴇʀꜱ", "ʙɪɢ ᴍɪʟᴇꜱᴛᴏɴᴇ ᴜɴʟᴏᴄᴋᴇᴅ.")
    if spend >= 500: unlock_achievement(user_id, "spend_500", "₹500 ꜱᴘᴇɴᴅ", "ᴠɪᴘ ᴛᴀʀɢᴇᴛ ᴄᴏᴍᴘʟᴇᴛᴇ.")
    if spend >= 5000: unlock_achievement(user_id, "spend_5000", "₹5000 ꜱᴘᴇɴᴅ", "ᴇʟɪᴛᴇ ᴄᴜꜱᴛᴏᴍᴇʀ ᴍɪʟᴇꜱᴛᴏɴᴇ.")

def show_achievements(user_id):
    data = load_json(ACHIEVEMENTS_FILE)
    arr = data.get(str(user_id), []) if isinstance(data, dict) else []
    names = {"first_order":"🥉 ꜰɪʀꜱᴛ ᴏʀᴅᴇʀ", "orders_10":"🏅 10 ᴏʀᴅᴇʀꜱ", "orders_50":"🥇 50 ᴏʀᴅᴇʀꜱ", "orders_100":"🏆 100 ᴏʀᴅᴇʀꜱ", "spend_500":"👑 ₹500 ꜱᴘᴇɴᴅ", "spend_5000":"💎 ₹5000 ꜱᴘᴇɴᴅ"}
    if not arr:
        bot.send_message(user_id, "🏆 <b>ᴀʙʜɪ ᴋᴏɪ ᴀᴄʜɪᴇᴠᴇᴍᴇɴᴛ ᴜɴʟᴏᴄᴋ ɴᴀʜɪ ʜᴜᴀ.</b>", parse_mode="HTML")
        return
    msg = "🏆 <b>ʏᴏᴜʀ ᴀᴄʜɪᴇᴠᴇᴍᴇɴᴛꜱ</b>\n\n" + "\n".join(names.get(x, x) for x in arr)
    bot.send_message(user_id, msg, parse_mode="HTML")

def show_monthly_report(user_id):
    now = datetime.now()
    orders = load_json(ORDERS_FILE).get(str(user_id), [])
    month_orders = []
    for o in orders:
        dt = _parse_order_datetime(o.get("date", ""))
        if dt and dt.month == now.month and dt.year == now.year:
            month_orders.append(o)
    spend = sum(float(o.get("charge", 0) or 0) for o in month_orders)
    counter = Counter(str(o.get("srv_id", "")) for o in month_orders if o.get("srv_id"))
    top_sid = counter.most_common(1)[0][0] if counter else "ɴᴏɴᴇ"
    bot.send_message(user_id, (
        f"📊 <b>{now.strftime('%B %Y')} ʀᴇᴘᴏʀᴛ</b>\n\n"
        f"📦 <b>ᴏʀᴅᴇʀꜱ »</b> {len(month_orders)}\n"
        f"💸 <b>ꜱᴘᴇɴᴅ »</b> ₹{spend:.2f}\n"
        f"⭐ <b>ᴛᴏᴘ ꜱᴇʀᴠɪᴄᴇ »</b> {top_sid}\n"
        f"💰 <b>ᴡᴀʟʟᴇᴛ »</b> ₹{get_balance(user_id):.2f}\n\n"
        "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>"
    ), parse_mode="HTML")

def validate_order_link_for_service(service_id, link):
    link = str(link or "").strip()
    if not link:
        return False, "❌ <b>ʟɪɴᴋ ᴇᴍᴘᴛʏ ʜᴀɪ.</b>"
    if " " in link or "\n" in link or "\t" in link:
        return False, "❌ <b>ʟɪɴᴋ ᴍᴇ ꜱᴘᴀᴄᴇ/ɴᴇᴡ ʟɪɴᴇ ɴᴀʜɪ ʜᴏɴᴀ ᴄʜᴀʜɪʏᴇ.</b>"
    if not (link.startswith("http://") or link.startswith("https://") or link.startswith("@")):
        return False, "❌ <b>ᴠᴀʟɪᴅ ʟɪɴᴋ ᴅᴇɪɴ.</b>"
    s_info = find_service(service_id)
    name = str(s_info[0]).lower() if s_info else ""
    low = link.lower()
    checks = [("instagram", "instagram.com"), ("youtube", "youtu"), ("telegram", "t.me"), ("facebook", "facebook.com"), ("tiktok", "tiktok.com"), ("twitter", "twitter.com"), ("x /", "x.com")]
    for key, domain in checks:
        if key in name and domain not in low and not link.startswith("@"):
            return False, f"❌ <b>ᴡʀᴏɴɢ ᴘʟᴀᴛꜰᴏʀᴍ ʟɪɴᴋ.</b>\n\n📌 <b>ᴛʜɪꜱ ꜱᴇʀᴠɪᴄᴇ ʟᴀɢᴛᴀ ʜᴀɪ {key.title()} ᴋᴇ ʟɪʏᴇ ʜᴀɪ.</b>"
    return True, ""

def notify_service_back_users(sid):
    data = load_json(SERVICE_NOTIFY_FILE)
    if not isinstance(data, dict):
        return
    users = data.get(str(sid), [])
    if not users:
        return
    name = _bot_service_name(sid)
    for uid in list(users):
        try:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🛒 ᴏʀᴅᴇʀ ɴᴏᴡ", callback_data=f"srv_{sid}"))
            bot.send_message(int(uid), f"🔔 <b>ꜱᴇʀᴠɪᴄᴇ ʙᴀᴄᴋ ᴏɴʟɪɴᴇ</b>\n\n🆔 <code>{sid}</code>\n📦 <b>{html.escape(str(name))}</b>\n\n✅ <b>ᴀʙ ᴀᴀᴘ ᴏʀᴅᴇʀ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ.</b>", parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    data.pop(str(sid), None)
    save_json(SERVICE_NOTIFY_FILE, data)

def subscribe_service_back_alert(user_id, sid):
    data = load_json(SERVICE_NOTIFY_FILE)
    if not isinstance(data, dict):
        data = {}
    arr = [str(x) for x in data.get(str(sid), [])]
    if str(user_id) not in arr:
        arr.append(str(user_id))
    data[str(sid)] = arr
    save_json(SERVICE_NOTIFY_FILE, data)

def notify_favorite_price_drop(sid, old_rate, new_rate):
    favs = load_json(FAVORITES_FILE)
    if not isinstance(favs, dict):
        return
    name = _bot_service_name(sid)
    for uid, arr in favs.items():
        if str(sid) in [str(x) for x in arr]:
            try:
                bot.send_message(int(uid), f"📉 <b>ᴘʀɪᴄᴇ ᴅʀᴏᴘ ᴀʟᴇʀᴛ</b>\n\n🆔 <code>{sid}</code>\n📦 <b>{html.escape(str(name))}</b>\n💰 <b>ᴄᴜʀʀᴇɴᴛ ᴘʀɪᴄᴇ :</b> ₹{float(price):.2f}/1000\n\n⭐ <b>ʏᴇ ᴀᴀᴘᴋᴇ ꜰᴀᴠᴏᴜʀɪᴛᴇꜱ ᴍᴇ ʜᴀɪ.</b>", parse_mode="HTML")
            except Exception:
                pass

def maybe_give_lucky_reward(user_id, order_id):
    """Fixed milestone bonus only. Random lucky reward removed."""
    try:
        orders = _user_order_count(user_id)
        milestones = {50: 5.0, 100: 10.0, 1000: 100.0}
        reward = milestones.get(int(orders))
        if not reward:
            return
        # one-time protection through wallet history text
        wh = load_json(WALLET_HISTORY_FILE)
        user_rows = wh.get(str(user_id), []) if isinstance(wh, dict) else []
        marker = f"ᴏʀᴅᴇʀ ᴍɪʟᴇꜱᴛᴏɴᴇ {orders}"
        if any(marker in str(row) for row in user_rows):
            return
        update_balance(user_id, reward)
        log_wallet(user_id, reward, marker, order_id=order_id)
        bot.send_message(
            user_id,
            f"🎁 <b>ᴏʀᴅᴇʀ ᴍɪʟᴇꜱᴛᴏɴᴇ ʙᴏɴᴜꜱ!</b>\n\n"
            f"📦 <b>{orders}ᴛʜ ᴏʀᴅᴇʀ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n"
            f"💰 <b>₹{reward:.2f} ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ.</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        print("milestone bonus error:", e)

def check_order_delay_notifications_once():
    orders_db = load_json(ORDERS_FILE)
    if not isinstance(orders_db, dict):
        return
    changed = False
    now = datetime.now()
    for uid, arr in orders_db.items():
        if not isinstance(arr, list):
            continue
        for order in arr:
            status = str(order.get("status", "")).lower()
            if status not in ("processing", "pending", "in progress"):
                continue
            if order.get("delay_notified"):
                continue
            dt = _parse_order_datetime(order.get("date", ""))
            if not dt:
                continue
            if (now - dt).total_seconds() >= 3600:
                try:
                    bot.send_message(int(uid), f"⚠️ <b>ᴏʀᴅᴇʀ ᴅᴇʟᴀʏ ᴀʟᴇʀᴛ</b>\n\n🆔 <b>ᴏʀᴅᴇʀ ɪᴅ »</b> <code>{order.get('order_id')}</code>\n📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{order.get('srv_id')}</code>\n\n⏳ <b>ᴏʀᴅᴇʀ ᴀʙʜɪ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ᴍᴇ ʜᴀɪ. ʙᴏᴛ ᴀᴜᴛᴏ ᴍᴏɴɪᴛᴏʀ ᴋᴀʀ ʀᴀʜᴀ ʜᴀɪ.</b>", parse_mode="HTML")
                except Exception:
                    pass
                order["delay_notified"] = True
                changed = True
    if changed:
        save_json(ORDERS_FILE, orders_db)

def order_delay_checker():
    while True:
        try:
            check_order_delay_notifications_once()
        except Exception as e:
            print("order delay checker error:", e)
        time.sleep(900)
# --- END USER PREMIUM TEXT FEATURES ---

def _panel_service_for_order(service_id):
    """Panel service metadata safely fetch karo; API unavailable ho to empty dict."""
    sid = str(service_id)
    try:
        for item in get_all_panel_services() or []:
            if str(item.get("service")) == sid:
                return item if isinstance(item, dict) else {}
    except Exception as e:
        print("Order metadata fetch error:", sid, e)
    return {}


def _clean_service_type(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "default").strip().lower()).strip("_") or "default"


def _detect_order_schema(service_id):
    """Panel type + name + description se required order fields decide karta hai."""
    panel = _panel_service_for_order(service_id)
    service = find_service(service_id)
    bot_name = service[0] if service else ""
    raw_type = panel.get("type") or panel.get("service_type") or "Default"
    stype = _clean_service_type(raw_type)
    hay = " ".join(str(panel.get(k, "")) for k in ("name", "description", "desc", "details", "type"))
    hay = (hay + " " + str(bot_name)).lower()

    schema = {
        "service_type": stype,
        "panel_type": str(raw_type),
        "panel_meta": panel,
        "fields": [],
        "api_field_map": {},
        "package": False,
    }

    # Standard SMM API service types
    if "subscription" in stype or "subscription" in hay:
        schema["fields"] = ["username", "min", "max", "posts", "delay", "expiry"]
        schema["api_field_map"] = {k: k for k in schema["fields"]}
    elif "mentions_custom_list" in stype or ("mention" in hay and ("custom list" in hay or "usernames" in hay)):
        schema["fields"] = ["quantity", "usernames"]
        schema["api_field_map"] = {"quantity": "quantity", "usernames": "usernames"}
    elif "mentions" in stype or "mention" in hay:
        schema["fields"] = ["username", "quantity"]
        schema["api_field_map"] = {"username": "username", "quantity": "quantity"}
    elif "custom_comments" in stype or "custom comment" in hay or "custom_comments" in hay:
        schema["fields"] = ["quantity", "comments"]
        schema["api_field_map"] = {"quantity": "quantity", "comments": "comments"}
    elif "seo" in stype or "seo" in hay or "keyword" in hay:
        schema["fields"] = ["quantity", "keywords"]
        schema["api_field_map"] = {"quantity": "quantity", "keywords": "keywords"}
    elif "poll" in stype or "poll" in hay or "answer number" in hay or "answer_number" in hay:
        schema["fields"] = ["answer_number", "quantity"]
        schema["api_field_map"] = {"answer_number": "answer_number", "quantity": "quantity"}
    elif "package" in stype or stype == "package":
        schema["fields"] = []
        schema["package"] = True
    elif "emoji" in hay and ("reaction" in hay or "custom" in hay):
        # Most SMM panels custom emoji/reaction ko comments parameter me accept karte hain.
        schema["fields"] = ["quantity", "comments"]
        schema["api_field_map"] = {"quantity": "quantity", "comments": "comments"}
    else:
        schema["fields"] = ["quantity"]
        schema["api_field_map"] = {"quantity": "quantity"}

    return schema


_DYNAMIC_FIELD_INFO = {
    "quantity": ("🔢", "ǫᴜᴀɴᴛɪᴛʏ", "🔢 <b>ᴋɪᴛɴɪ ǫᴜᴀɴᴛɪᴛʏ ᴄʜᴀʜɪʏᴇ?</b>\n\n💡 <b>ᴇxᴀᴍᴘʟᴇ » 1000</b>"),
    "answer_number": ("🗳️", "ᴀɴꜱᴡᴇʀ", "🗳️ <b>ᴘᴏʟʟ ᴀɴꜱᴡᴇʀ/ᴏᴘᴛɪᴏɴ ɴᴜᴍʙᴇʀ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>\n\n1️⃣ = ꜰɪʀꜱᴛ ᴏᴘᴛɪᴏɴ\n2️⃣ = ꜱᴇᴄᴏɴᴅ ᴏᴘᴛɪᴏɴ\n3️⃣ = ᴛʜɪʀᴅ ᴏᴘᴛɪᴏɴ\n4️⃣ = ꜰᴏᴜʀᴛʜ ᴏᴘᴛɪᴏɴ"),
    "comments": ("💬", "ᴄᴏᴍᴍᴇɴᴛꜱ/ᴇᴍᴏᴊɪ", "💬 <b>ᴄᴏᴍᴍᴇɴᴛꜱ ʏᴀ ᴇᴍᴏᴊɪ ꜱᴇɴᴅ ᴋᴀʀᴏ:</b>\n\n📌 <b>ʜᴀʀ ᴄᴏᴍᴍᴇɴᴛ ɴᴇᴡ ʟɪɴᴇ ᴍᴇ ʟɪᴋʜᴏ.</b>"),
    "usernames": ("👥", "ᴜꜱᴇʀɴᴀᴍᴇꜱ", "👥 <b>ᴜꜱᴇʀɴᴀᴍᴇ ʟɪꜱᴛ ꜱᴇɴᴅ ᴋᴀʀᴏ:</b>\n\n📌 <b>ʜᴀʀ ᴜꜱᴇʀɴᴀᴍᴇ ɴᴇᴡ ʟɪɴᴇ ᴍᴇ.</b>"),
    "username": ("👤", "ᴜꜱᴇʀɴᴀᴍᴇ", "👤 <b>ᴜꜱᴇʀɴᴀᴍᴇ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>"),
    "keywords": ("🔎", "ᴋᴇʏᴡᴏʀᴅꜱ", "🔎 <b>ᴋᴇʏᴡᴏʀᴅꜱ ꜱᴇɴᴅ ᴋᴀʀᴏ:</b>\n\n📌 <b>ʜᴀʀ ᴋᴇʏᴡᴏʀᴅ ɴᴇᴡ ʟɪɴᴇ ᴍᴇ.</b>"),
    "min": ("📉", "ᴍɪɴ", "📉 <b>ᴍɪɴɪᴍᴜᴍ ǫᴜᴀɴᴛɪᴛʏ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>"),
    "max": ("📈", "ᴍᴀx", "📈 <b>ᴍᴀxɪᴍᴜᴍ ǫᴜᴀɴᴛɪᴛʏ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>"),
    "posts": ("📮", "ᴘᴏꜱᴛꜱ", "📮 <b>ᴋɪᴛɴᴇ ɴᴇᴡ ᴘᴏꜱᴛꜱ ᴘᴀʀ ꜱᴇʀᴠɪᴄᴇ ᴄʜᴀʜɪʏᴇ?</b>"),
    "delay": ("⏱️", "ᴅᴇʟᴀʏ", "⏱️ <b>ᴅᴇʟᴀʏ ɪɴ ᴍɪɴᴜᴛᴇꜱ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>"),
    "expiry": ("📅", "ᴇxᴘɪʀʏ", "📅 <b>ᴇxᴘɪʀʏ ᴅᴀᴛᴇ ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>\n\n💡 <b>ꜰᴏʀᴍᴀᴛ » ᴅ/ᴍ/ʏ</b>"),
}


def _dynamic_field_prompt(field):
    return _DYNAMIC_FIELD_INFO.get(field, ("📝", to_mini_text(field), f"📝 <b>{to_mini_text(field)} ᴇɴᴛᴇʀ ᴋᴀʀᴏ:</b>"))[2]


def _dynamic_field_display(field, value):
    icon, label, _ = _DYNAMIC_FIELD_INFO.get(field, ("📝", to_mini_text(field), ""))
    raw = str(value or "")
    # Link/username/code-like values ko exact rakho; user-written prose ko mini display me badlo.
    if field in ("comments", "keywords"):
        shown = html.escape(to_mini_text(raw))
    else:
        shown = html.escape(raw)
    if "\n" in shown:
        shown = "\n".join(f"▫️ {line}" for line in shown.splitlines() if line.strip())
        return f"{icon} <b>{label} :</b>\n{shown}\n"
    return f"{icon} <b>{label} :</b> {shown}\n"


def _validate_dynamic_field(field, raw, order_data):
    value = str(raw or "").strip()
    if not value:
        return False, None, "❌ <b>ᴛʜɪꜱ ꜰɪᴇʟᴅ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ.</b>"
    if field in ("quantity", "answer_number", "min", "max", "posts", "delay"):
        try:
            number = int(value)
            if field == "delay":
                if number < 0:
                    raise ValueError
            elif number <= 0:
                raise ValueError
        except Exception:
            return False, None, "❌ <b>ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ᴇɴᴛᴇʀ ᴋᴀʀᴏ.</b>"
        if field == "max" and int(order_data.get("extra_fields", {}).get("min", 0) or 0) > number:
            return False, None, "❌ <b>ᴍᴀx ǫᴜᴀɴᴛɪᴛʏ, ᴍɪɴ ꜱᴇ ᴄʜʜᴏᴛɪ ɴᴀʜɪ ʜᴏ ꜱᴀᴋᴛɪ.</b>"
        return True, number, None
    return True, value, None


def _count_nonempty_lines(value):
    return len([x for x in str(value or "").splitlines() if x.strip()])


def _finish_dynamic_order_input(user_id):
    data = user_orders.get(user_id)
    if not data:
        return
    schema = data.get("schema") or _detect_order_schema(data.get("service_id"))
    extras = data.get("extra_fields", {})

    if schema.get("package"):
        billing_quantity = 1000
        display_quantity = None
    elif "quantity" in extras:
        billing_quantity = int(extras.get("quantity") or 0)
        display_quantity = billing_quantity
    elif "max" in extras:
        billing_quantity = int(extras.get("max") or 0)
        display_quantity = billing_quantity
    elif "comments" in extras:
        billing_quantity = max(1, _count_nonempty_lines(extras.get("comments")))
        display_quantity = billing_quantity
    elif "usernames" in extras:
        billing_quantity = max(1, _count_nonempty_lines(extras.get("usernames")))
        display_quantity = billing_quantity
    else:
        billing_quantity = 1000
        display_quantity = None

    service_id = data.get("service_id")
    selling_price = get_selling_price_for_user(service_id, user_id)
    if selling_price is None:
        bot.send_message(user_id, "❌ <b>ᴘʀɪᴄᴇ ꜰᴇᴛᴄʜ ᴇʀʀᴏʀ. ᴛʀʏ ᴀɢᴀɪɴ.</b>", parse_mode="HTML")
        user_orders.pop(user_id, None)
        return

    total_cost = round((billing_quantity / 1000) * float(selling_price), 2)
    if get_balance(user_id) < total_cost:
        bot.send_message(user_id, f"❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!</b>\n\n💰 <b>ᴄᴏꜱᴛ :</b> ₹{total_cost:.2f}\n💳 <b>ᴡᴀʟʟᴇᴛ :</b> ₹{get_balance(user_id):.2f}", parse_mode="HTML")
        user_orders.pop(user_id, None)
        return

    data["quantity"] = billing_quantity
    data["display_quantity"] = display_quantity
    data["selling_price"] = float(selling_price)
    data["total_cost"] = total_cost
    # Backward compatibility
    if "answer_number" in extras:
        data["answer_number"] = str(extras["answer_number"])
    send_order_confirm_message(user_id)


def _ask_next_dynamic_field(user_id):
    data = user_orders.get(user_id)
    if not data:
        return
    fields = data.get("schema", {}).get("fields", [])
    index = int(data.get("field_index", 0))
    if index >= len(fields):
        _finish_dynamic_order_input(user_id)
        return
    field = fields[index]
    msg = bot.send_message(user_id, _dynamic_field_prompt(field), parse_mode="HTML")
    bot.register_next_step_handler(msg, process_dynamic_order_field)


def process_dynamic_order_field(message):
    user_id = message.chat.id
    if getattr(message, "text", None) in MENU_BUTTONS:
        handle_menu_redirection(message)
        return
    data = user_orders.get(user_id)
    if not data:
        return
    fields = data.get("schema", {}).get("fields", [])
    index = int(data.get("field_index", 0))
    if index >= len(fields):
        _finish_dynamic_order_input(user_id)
        return
    field = fields[index]
    ok, value, error = _validate_dynamic_field(field, getattr(message, "text", ""), data)
    if not ok:
        msg = bot.send_message(user_id, error + "\n\n" + _dynamic_field_prompt(field), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_dynamic_order_field)
        return
    data.setdefault("extra_fields", {})[field] = value
    data["field_index"] = index + 1
    _ask_next_dynamic_field(user_id)


def process_link(message):
    user_id = message.chat.id
    if getattr(message, "text", None) in MENU_BUTTONS:
        handle_menu_redirection(message)
        return
    if user_id not in user_orders:
        return
    link = str(getattr(message, "text", "") or "").strip()
    service_id = user_orders[user_id].get("service_id")
    existing_schema = user_orders[user_id].get("schema") or _detect_order_schema(service_id)
    user_orders[user_id]["schema"] = existing_schema
    if "subscription" in existing_schema.get("service_type", ""):
        user_orders[user_id]["link"] = link
        user_orders[user_id]["extra_fields"] = {"username": link}
        user_orders[user_id]["field_index"] = 1
        _ask_next_dynamic_field(user_id)
        return
    user_orders[user_id]["link"] = link
    ok_link, link_error = validate_order_link_for_service(service_id, link)
    if not ok_link:
        msg = bot.send_message(user_id, link_error + "\n\n🔗 <b>ᴄᴏʀʀᴇᴄᴛ ʟɪɴᴋ ᴀɢᴀɪɴ ꜱᴇɴᴅ ᴋᴀʀᴏ:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_link)
        return
    schema = _detect_order_schema(service_id)
    user_orders[user_id]["schema"] = schema
    user_orders[user_id]["extra_fields"] = {}
    user_orders[user_id]["field_index"] = 0
    _ask_next_dynamic_field(user_id)


def process_answer_number(message):
    # Old callback compatibility: dynamic handler hi use hoga.
    process_dynamic_order_field(message)


def order_confirm_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ ᴄᴏɴꜰɪʀᴍ", callback_data="order_confirm"),
        types.InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="order_cancel")
    )
    return kb


def _order_extra_lines(order_data):
    extras = order_data.get("extra_fields") or {}
    lines = ""
    for field, value in extras.items():
        if field == "quantity":
            continue
        lines += _dynamic_field_display(field, value)
    return lines


def send_order_confirm_message(user_id):
    order_data = user_orders.get(user_id, {})
    service_id = order_data.get("service_id")
    link = order_data.get("link")
    quantity = order_data.get("display_quantity")
    total_cost = float(order_data.get("total_cost", 0) or 0)
    selling_price = float(order_data.get("selling_price", 0) or 0)
    s_info = find_service(service_id)
    service_name = html.escape(to_mini_text(s_info[0])) if s_info else "ᴜɴᴋɴᴏᴡɴ ꜱᴇʀᴠɪᴄᴇ"
    quantity_line = f"🔢 <b>ǫᴜᴀɴᴛɪᴛʏ :</b> {quantity}\n" if quantity is not None else ""
    extra_lines = _order_extra_lines(order_data)
    text = (
        "🧾 <b>ᴄᴏɴꜰɪʀᴍ ʏᴏᴜʀ ᴏʀᴅᴇʀ</b>\n\n"
        f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ :</b> <code>{service_id}</code>\n"
        f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ :</b> {service_name}\n"
        f"🔗 <b>ʟɪɴᴋ :</b> {html.escape(str(link))}\n"
        f"{quantity_line}{extra_lines}"
        f"💸 <b>ʀᴀᴛᴇ :</b> ₹{selling_price:.2f}/1000\n"
        f"💰 <b>ᴛᴏᴛᴀʟ ᴄᴏꜱᴛ :</b> ₹{total_cost:.2f}\n"
        f"💳 <b>ᴡᴀʟʟᴇᴛ :</b> ₹{get_balance(user_id):.2f}\n\n"
        "✅ <b>ᴄᴏɴꜰɪʀᴍ ᴘᴀʀ ᴏʀᴅᴇʀ ʟᴀɢ ᴊᴀʏᴇɢᴀ.</b>\n"
        "❌ <b>ᴄᴀɴᴄᴇʟ ᴘᴀʀ ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟ ʜᴏ ᴊᴀʏᴇɢᴀ.</b>"
    )
    bot.send_message(user_id, text, parse_mode="HTML", reply_markup=order_confirm_keyboard())


def place_confirmed_order(user_id):
    order_data = user_orders.get(user_id)
    if not order_data:
        return False, "❌ ᴏʀᴅᴇʀ ᴅᴇᴛᴀɪʟꜱ ᴇxᴘɪʀᴇᴅ. ᴘʟᴇᴀꜱᴇ ᴛʀʏ ᴀɢᴀɪɴ."
    service_id = order_data.get("service_id")
    link = order_data.get("link")
    quantity = int(order_data.get("quantity", 0) or 0)
    display_quantity = order_data.get("display_quantity")
    total_cost = float(order_data.get("total_cost", 0) or 0)
    selling_price = float(order_data.get("selling_price", 0) or 0)
    extras = order_data.get("extra_fields") or {}
    schema = order_data.get("schema") or _detect_order_schema(service_id)
    s_info = find_service(service_id)
    if not s_info:
        user_orders.pop(user_id, None)
        return False, "❌ ꜱᴇʀᴠɪᴄᴇ ɴᴀʜɪ ᴍɪʟɪ."
    if get_balance(user_id) < total_cost:
        user_orders.pop(user_id, None)
        return False, f"❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!</b>\n\n💰 <b>ᴄᴏꜱᴛ :</b> ₹{total_cost:.2f}\n💳 <b>ᴡᴀʟʟᴇᴛ :</b> ₹{get_balance(user_id):.2f}"

    api_payload = {"key": SMM_API_KEY, "action": "add", "service": service_id, "link": link}
    for field, api_key in (schema.get("api_field_map") or {}).items():
        if field in extras:
            api_payload[api_key] = extras[field]
    if not schema.get("package") and "quantity" not in api_payload and schema.get("service_type") == "default":
        api_payload["quantity"] = quantity

    try:
        response = _api_post(api_payload, timeout=(4, 10)).json()
        if "order" not in response:
            err_text = str(response.get("error", response))
            if any(x in err_text.lower() for x in ["disabled", "not found", "unavailable", "inactive"]):
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("🔔 ɴᴏᴛɪꜰʏ ᴍᴇ", callback_data=f"notify_service_{service_id}"))
                bot.send_message(user_id, f"🚫 <b>ꜱᴇʀᴠɪᴄᴇ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ</b>\n\n📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ »</b> <code>{service_id}</code>\n📦 <b>ꜱᴇʀᴠɪᴄᴇ »</b> {html.escape(to_mini_text(s_info[0]))}", parse_mode="HTML", reply_markup=kb)
            return False, f"❌ <b>ᴘᴀɴᴇʟ ᴇʀʀᴏʀ:</b> {html.escape(to_mini_text(err_text))}"

        update_balance(user_id, -total_cost)
        log_wallet(user_id, -total_cost, "ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇᴅ", order_id=response["order"], service_id=service_id)
        saved_order = {
            "order_id": response["order"], "srv_id": service_id, "link": link,
            "qty": quantity, "display_qty": display_quantity, "charge": total_cost,
            "rate": selling_price, "answer_number": extras.get("answer_number"),
            "extra_fields": extras, "service_type": schema.get("service_type"),
            "panel_type": schema.get("panel_type"),
            "date": datetime.now().strftime("%d-%m-%Y %I:%M %p"), "status": "processing",
            "completed_notified": False, "cancelled_notified": False, "partial_notified": False,
            "refill_notified": False, "cancel_request_notified": False, "refunded": False
        }
        orders_db = load_json(ORDERS_FILE)
        orders_db.setdefault(str(user_id), []).append(saved_order)
        save_json(ORDERS_FILE, orders_db)

        service_name = html.escape(to_mini_text(s_info[0]))
        quantity_line = f"🔢 <b>ǫᴜᴀɴᴛɪᴛʏ :</b> {display_quantity}\n" if display_quantity is not None else ""
        extra_lines = _order_extra_lines(order_data)
        success_order_msg = (
            "📦 <b>ᴏʀᴅᴇʀ ᴘʟᴀᴄᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n"
            f"🆔 <b>ᴏʀᴅᴇʀ ɪᴅ :</b> <code>{response['order']}</code>\n"
            f"📌 <b>ꜱᴇʀᴠɪᴄᴇ ɪᴅ :</b> <code>{service_id}</code>\n"
            f"📦 <b>ꜱᴇʀᴠɪᴄᴇ ɴᴀᴍᴇ :</b> {service_name}\n"
            f"🔗 <b>ʟɪɴᴋ :</b> {html.escape(str(link))}\n"
            f"{quantity_line}{extra_lines}"
            f"💰 <b>ᴄʜᴀʀɢᴇ :</b> ₹{total_cost:.2f}\n"
            "🔄 <b>ꜱᴛᴀᴛᴜꜱ :</b> ᴘʀᴏᴄᴇꜱꜱɪɴɢ\n\n"
            "💎 <b>ᴀᴍᴏᴜɴᴛ ᴅᴇᴅᴜᴄᴛᴇᴅ ꜰʀᴏᴍ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ</b>\n"
            "🤖 <b>ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ 💪🏻</b>"
        )
        bot.send_message(user_id, success_order_msg, parse_mode="HTML")
        try:
            check_user_achievements(user_id); maybe_give_lucky_reward(user_id, response["order"])
        except Exception as e:
            print("post order user rewards error:", e)
        send_order_log_to_channel(user_id, response["order"], service_id, service_name, link, display_quantity if display_quantity is not None else "ᴘᴀᴄᴋᴀɢᴇ", total_cost)
        user_orders.pop(user_id, None)
        return True, None
    except Exception as e:
        print("Dynamic order error:", e)
        return False, "❌ <b>ᴄᴏɴɴᴇᴄᴛɪᴏɴ ᴇʀʀᴏʀ. ᴘᴀɴᴇʟ ʀᴇꜱᴘᴏɴᴅ ɴᴀʜɪ ᴋᴀʀ ʀᴀʜᴀ.</b>"


def process_quantity(message):
    # Old registered handlers / restored sessions compatibility.
    user_id = message.chat.id
    if user_id in user_orders:
        data = user_orders[user_id]
        data.setdefault("schema", {"fields": ["quantity"], "api_field_map": {"quantity": "quantity"}, "service_type": "default", "package": False})
        data.setdefault("extra_fields", {})
        data["field_index"] = 0
    process_dynamic_order_field(message)


# --- SAFE SERVICE MASTER SYNC ---
def sync_service_metadata_into_services():
    """Service related JSON ka useful data services.json me metadata ke roop me sync karta hai.
    Old JSON delete nahi karta, taaki purana flow safe rahe.
    """
    try:
        services_db = load_json(SERVICES_FILE)
        if not isinstance(services_db, dict):
            return
        margins = load_json(MARGINS_FILE); margins = margins if isinstance(margins, dict) else {}
        vip = load_json(VIP_MARGINS_FILE); vip = vip if isinstance(vip, dict) else {}
        pins = load_json(PINNED_SERVICES_FILE)
        pin_set = set(str(x) for x in (pins.keys() if isinstance(pins, dict) else pins if isinstance(pins, list) else []))
        changed = False
        for cat, items in list(services_db.items()):
            if not isinstance(items, dict):
                continue
            for sid, val in list(items.items()):
                sid = str(sid)
                if isinstance(val, list):
                    while len(val) < 2:
                        val.append(0)
                    if len(val) < 3 or not isinstance(val[2], dict):
                        val.append({})
                    meta = val[2]
                    if sid in margins:
                        meta["margin"] = margins[sid]
                    if sid in vip:
                        meta["vip_margin"] = vip[sid]
                    meta["pinned"] = sid in pin_set
                    meta["subcat"] = cat
                    items[sid] = val
                    changed = True
        if changed:
            save_json(SERVICES_FILE, services_db)
    except Exception as e:
        print("service master sync error:", e)
# --- END SAFE SERVICE MASTER SYNC ---

if __name__ == "__main__":
    ensure_json_files()
    sync_service_metadata_into_services()
    backup_json_files()
    threading.Thread(target=auto_order_notification_checker, daemon=True).start()
    threading.Thread(target=auto_panel_service_alert_checker, daemon=True).start()
    threading.Thread(target=auto_ticket_close_checker, daemon=True).start()
    threading.Thread(target=auto_vip_upgrade_checker, daemon=True).start()
    threading.Thread(target=auto_coupon_expire_checker, daemon=True).start()
    threading.Thread(target=order_delay_checker, daemon=True).start()
    print("ʟᴇɢᴇɴᴅᴀʀʏ ʀᴇʜᴀɴ ꜱᴍᴍ ʙᴏᴛ ɪꜱ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʀᴜɴ...")
    bot.infinity_polling(
        skip_pending=True,
        none_stop=True,
        interval=0,
        timeout=3,
        long_polling_timeout=3
    )
