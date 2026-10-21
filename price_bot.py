#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات کانال قیمت لحظه‌ای ارز، طلا، سکه و نقره (منبع قیمت: tgju) — نسخه‌ی ۱٫۳

پیام‌های ثابت (بی‌صدا، با ویرایش خودکار اگر قیمت تغییری نکرده):
  ۱) قیمت ارزها (دلار، یورو، پوند، درهم، لیر ترکیه) + بیت‌کوین، اونس جهانی طلا، نفت برنت و نفت خام
  ۲) قیمت طلا، سکه (با حباب) و نقره

برنامه‌ی روزانه (به وقت تهران):
  ۲۱:۰۰  آموزش کوتاه شبانه (از فایل lessons.json)
  ۲۲:۳۰  جمع‌بندی کمترین و بیشترین قیمت امروز، بلافاصله بعدش نظرسنجی (آخرین پیام شب)،
         سپس سکوت تا ۰۱:۰۰ بامداد. اگر نظرسنجی در این بازه نرفت، اولین فرصت بعد از ۰۱:۰۰ می‌رود.

اجرا:
  pip install requests
  export BOT_TOKEN="توکن ربات از BotFather"
  export CHANNEL_ID="@your_channel"      # ربات باید مدیر کانال باشد
  python3 price_bot.py --once            # یک بار اجرا (برای گیت‌هاب)
  python3 price_bot.py --once --summary  # ارسال فوری جمع‌بندی (فقط تست)
  python3 price_bot.py --once --poll     # ارسال فوری نظرسنجی (فقط تست)
  python3 price_bot.py --once --lesson   # ارسال فوری آموزش بعدی (فقط تست)
  python3 price_bot.py                   # همیشه روشن، هر ۵ دقیقه
"""

import os
import sys
import json
import math
import time
from datetime import datetime, timedelta, timezone

import requests

# ---------------- تنظیمات ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

# آیدی کانال که در پایان هر پیام نوشته می‌شود
CHANNEL_TAG = "@Hypertech_ir"

INTERVAL_SECONDS = 300          # فقط در حالت همیشه روشن
STATE_FILE = "state.json"       # شناسه‌ی پیام‌ها و وضعیت برنامه‌ی روزانه اینجا نگه داشته می‌شود
LESSONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lessons.json")

BOT_VERSION = "1.3"

# ساعت‌ها به وقت تهران (دقیقه از نیمه‌شب)
LESSON_MINUTE = 21 * 60         # ۲۱:۰۰ آموزش شبانه
SUMMARY_MINUTE = 22 * 60 + 30   # ۲۲:۳۰ جمع‌بندی، بعدش نظرسنجی، و شروع سکوت
QUIET_END_MINUTE = 1 * 60       # ۰۱:۰۰ پایان سکوت
POLL_FALLBACK_END_MINUTE = 10 * 60   # اگر نظرسنجی شب از دست رفت، تا ساعت ۱۰ صبح فردا هنوز فرستاده می‌شود

# تغییر قیمت این کلیدها به‌تنهایی پیام جدید نمی‌سازد؛ فقط پیام قبلی ویرایش می‌شود
# (نقره و بازار جهانی پرنوسان‌اند). اگر قیمت بقیه‌ی آیتم‌ها تغییر کند، پیام جدید می‌رود.
EDIT_ONLY_KEYS = {"silver_925", "silver_999", "crypto-bitcoin", "ons",
                  "energy-brent-oil", "energy-crude-oil"}

# اموجی جهت تغییر قیمت. اموجی «فلش سبز رو به بالا» وجود ندارد؛
# نزدیک‌ترین حالت دایره‌ی رنگی کنار فلش است.
UP_EMOJI = "🟢⬆️"
DOWN_EMOJI = "🔴⬇️"

# فید زنده‌ی tgju؛ آدرس دوم نسخه‌ی کمکی (آینه) همان فید است
FEED_URLS = [
    "https://call1.tgju.org/ajax.json",
    "https://call3.tgju.org/ajax.json",
]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://www.tgju.org/",
}

# ---------- فهرست‌ها: (اموجی، نام نمایشی، کلید tgju) ----------
CURRENCY_TITLE = "💱 قیمت لحظه‌ای ارز"
CURRENCY_SECTIONS = [
    [
        ("💵", "دلار آمریکا", "price_dollar_rl"),
        ("💶", "یورو", "price_eur"),
        ("💷", "پوند", "price_gbp"),
        ("🇦🇪", "درهم امارات", "price_aed"),
        ("🇹🇷", "لیر ترکیه", "price_try"),
    ],
    [
        ("₿", "بیت‌کوین", "crypto-bitcoin"),
        ("🌍", "اونس جهانی طلا", "ons"),
        ("🛢", "نفت برنت", "energy-brent-oil"),
        ("🛢", "نفت خام", "energy-crude-oil"),
    ],
]
# واحد قیمت این کلیدها را از روی اندازه‌ی عدد تشخیص می‌دهیم:
#   usd = معمولاً به دلار؛ اگر عدد غیرممکن (بسیار بزرگ) بود یعنی ریال است و به تومان تبدیل می‌شود
# عدد دوم: تعداد رقم اعشار نمایش (برای دلار)
GLOBAL_META = {
    "crypto-bitcoin": ("usd", 0),
    "ons": ("usd", 2),
    "energy-brent-oil": ("usd", 2),
    "energy-crude-oil": ("usd", 2),
}

GOLD_TITLE = "🥇 قیمت لحظه‌ای طلا، سکه و نقره"
GOLD_SECTIONS = [
    [
        ("🥇", "طلای ۱۸ عیار (هر گرم)", "geram18"),
        ("🥇", "طلای ۲۴ عیار (هر گرم)", "geram24"),
    ],
    [
        ("🪙", "سکه امامی", "sekee"),
        ("🫧", "حباب سکه امامی", "coin_blubber"),
        ("🪙", "سکه بهار آزادی", "sekeb"),
        ("🫧", "حباب سکه بهار آزادی", "sekeb_blubber"),
        ("🪙", "نیم‌سکه", "nim"),
        ("🫧", "حباب نیم‌سکه", "nim_blubber"),
        ("🪙", "ربع‌سکه", "rob"),
        ("🫧", "حباب ربع‌سکه", "rob_blubber"),
    ],
    [
        ("🥈", "نقره ۹۲۵ (هر گرم)", "silver_925"),
        ("🥈", "نقره ۹۹۹ (هر گرم)", "silver_999"),
    ],
]

# آیتم‌های جمع‌بندی شبانه: (اموجی، نام نمایشی، کلید tgju)
SUMMARY_TITLE = "📊 جمع‌بندی بازار امروز"
SUMMARY_ITEMS = [
    ("💵", "دلار آمریکا", "price_dollar_rl"),
    ("🥇", "طلای ۱۸ عیار (هر گرم)", "geram18"),
    ("🥈", "نقره ۹۲۵ (هر گرم)", "silver_925"),
    ("🥈", "نقره ۹۹۹ (هر گرم)", "silver_999"),
    ("🪙", "سکه امامی", "sekee"),
    ("🪙", "سکه بهار آزادی", "sekeb"),
]

# نظرسنجی روزانه: هر روز یک مورد از این فهرست (به ترتیب، دوباره از اول)
POLL_ASSETS = ["دلار", "طلای ۱۸ عیار", "سکه امامی", "بیت‌کوین", "اونس جهانی طلا"]
POLL_OPTIONS = ["📈 بالاتر می‌ره", "📉 پایین‌تر میاد", "➖ تقریباً ثابت می‌مونه"]

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def all_keys():
    sections = CURRENCY_SECTIONS + GOLD_SECTIONS
    return [k for sec in sections for (_e, _t, k) in sec]


# ---------------- دریافت قیمت‌ها ----------------
def load_feed():
    """فید زنده‌ی tgju را می‌گیرد. هر بار یک پارامتر تصادفی می‌فرستیم
    تا نسخه‌ی کهنه‌ی ذخیره‌شده (کش) تحویل ندهند."""
    for url in FEED_URLS:
        try:
            resp = requests.get(
                url,
                params={"rnd": str(time.time_ns())},
                headers=HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
            current = resp.json().get("current")
            if current:
                return current
            print(f"فید خالی بود: {url}")
        except Exception as e:
            print(f"خطا در گرفتن {url}: {e}")
    return None


def to_number(value):
    """عدد را از متن (احتمالاً با کاما یا رقم فارسی) درمی‌آورد."""
    text = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٬،", "0123456789,,"))
    return float(text.replace(",", "").strip())


def parse_item(key, entry):
    """
    یک آیتم فید را به دیکشنری تبدیل می‌کند:
      v: مقدار | unit: toman یا usd | dec: رقم اعشار | dir: high/low/"" | pct: درصد تغییر روزانه یا None
    قیمت‌های ریالی tgju به تومان تبدیل می‌شوند.
    """
    raw = to_number(entry["p"])
    kind, dec = GLOBAL_META.get(key, ("rial", 0))
    if kind == "rial":
        value, unit = raw / 10, "toman"
    elif kind == "usd":
        value, unit = (raw / 10, "toman") if raw > 50_000_000 else (raw, "usd")
    else:  # auto
        value, unit = (raw / 10, "toman") if raw >= 1000 else (raw, "usd")

    direction = entry.get("dt", "")
    pct = None
    if "blubber" not in key:                      # درصد تغییر حباب معنی‌دار نیست
        try:
            dp = to_number(entry["dp"])
            pct = abs(dp)
            if direction not in ("high", "low"):
                direction = "high" if dp > 0 else "low" if dp < 0 else ""
        except Exception:
            pct = None
    return {"v": value, "unit": unit, "dec": dec, "dir": direction, "pct": pct}


def fetch_prices(current=None):
    """خروجی: {کلید: دیکشنری آیتم}. اگر فید داده نشود، خودش می‌گیرد."""
    if current is None:
        current = load_feed()
    if not current:
        return {}

    result = {}
    missing = []
    for key in all_keys():
        entry = current.get(key)
        if not entry:
            missing.append(key)
            continue
        try:
            result[key] = parse_item(key, entry)
        except Exception as e:
            print(f"قیمت {key} خوانده نشد: {e} | داده: {entry}")

    if missing:
        print("کلیدهای زیر در فید نبودند (از آن‌ها گذشتم):", missing)
        hints = ("sek", "nim", "rob", "geram", "silver", "gold", "gbp", "aed",
                 "blubber", "bubble", "crypto", "bitcoin", "ons", "energy", "oil", "try")
        found = sorted(k for k in current if any(h in k.lower() for h in hints))
        print("کلیدهای مشابه موجود در فید:", found[:80])
    return result


# ---------------- تاریخ شمسی و وقت تهران ----------------
# نام روزهای هفته؛ ترتیب پایتون: دوشنبه = ۰ ... یکشنبه = ۶
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def tehran_now():
    """وقت فعلی به وقت تهران."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Tehran"))
    except Exception:
        # اگر پایگاه زمان در دسترس نبود: ۳:۳۰ جلوتر از جهانی
        return datetime.now(timezone(timedelta(hours=3, minutes=30)))


def gregorian_to_jalali(gy, gm, gd):
    """تبدیل تاریخ میلادی به شمسی."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_stamp():
    """مثل: یکشنبه ۱۴۰۵/۰۷/۲۶  ۱۵:۴۱"""
    t = tehran_now()
    jy, jm, jd = gregorian_to_jalali(t.year, t.month, t.day)
    day_name = WEEKDAYS[t.weekday()]
    text = f"{jy}/{jm:02d}/{jd:02d}  {t.hour:02d}:{t.minute:02d}"
    return f"{day_name} " + text.translate(PERSIAN_DIGITS)


def jalali_date_key(t):
    """کلید روز شمسی برای ذخیره در state، مثل 1405/07/26"""
    jy, jm, jd = gregorian_to_jalali(t.year, t.month, t.day)
    return f"{jy}/{jm:02d}/{jd:02d}"


# ---------------- ساخت متن پیام‌ها ----------------
def fa(number):
    """عدد صحیح با جداکننده‌ی هزارگان و رقم فارسی."""
    return f"{int(round(number)):,}".replace(",", "٬").translate(PERSIAN_DIGITS)


def fa_dec(number, decimals):
    """عدد اعشاری با جداکننده‌ی هزارگان و رقم فارسی."""
    text = f"{number:,.{decimals}f}".replace(",", "٬").replace(".", "٫")
    return text.translate(PERSIAN_DIGITS)


def arrow_and_percent(item):
    parts = []
    if item["dir"] == "high":
        parts.append(UP_EMOJI)
    elif item["dir"] == "low":
        parts.append(DOWN_EMOJI)
    if item["pct"] is not None and (item["pct"] > 0 or parts):
        parts.append(fa_dec(item["pct"], 2) + "٪")
    return (" " + " ".join(parts)) if parts else ""


def value_text(item):
    if item["unit"] == "toman":
        return f"{fa(item['v'])} تومان"
    return f"{fa_dec(item['v'], item['dec'])} دلار"


def signature_value(item):
    """مقداری که برای تشخیص «تغییر نکرده» مقایسه می‌شود.
    قیمت‌های دلاری پرنوسان (بیت‌کوین و ...) با سه رقم معنی‌دار مقایسه می‌شوند
    تا هر تکان کوچک پیام جدید نسازد."""
    v = item["v"]
    if item["unit"] == "toman" or v <= 0:
        return int(round(v))
    step = 10 ** (math.floor(math.log10(v)) - 2)
    return int(round(v / step))


def build_group(title, sections, prices):
    """متن بدنه‌ی پیام (بدون خط زمان) و امضای قیمت‌ها را برمی‌گرداند.
    اگر هیچ قیمتی از این گروه نبود، None برمی‌گرداند."""
    blocks = []
    signature = {}
    for section in sections:
        lines = []
        for emoji, name, key in section:
            item = prices.get(key)
            if item is None:
                continue
            if key not in EDIT_ONLY_KEYS:
                signature[key] = signature_value(item)
            lines.append(f"{emoji} {name}: {value_text(item)}{arrow_and_percent(item)}")
        if lines:
            blocks.append("\n".join(lines))
    if not blocks:
        return None
    body = title + "\n\n" + "\n\n".join(blocks)
    return body, signature


RLM = "\u200f"   # نشانه‌ی راست‌به‌چپ (حرف راست‌به‌چپِ نامرئی)


def rtl(text):
    """
    اول هر خط یک نشانه‌ی راست‌به‌چپ می‌گذارد تا تلگرام همه‌ی خط‌ها را راست‌چین کند.
    بدون این، خطی که با اموجی پرچم (مثل 🇦🇪 و 🇹🇷) شروع شود چپ‌چین و درهم نمایش داده می‌شود،
    چون اموجی پرچم برای الگوریتم جهت‌دهی «حرف چپ‌به‌راست» حساب می‌شود.
    """
    return "\n".join((RLM + line) if line.strip() else line for line in text.split("\n"))


def with_footer(body):
    return rtl(f"{body}\n\n🕒 آخرین بروزرسانی: {jalali_stamp()} (به وقت تهران)\n\n{CHANNEL_TAG}")


# ---------------- تلگرام و وضعیت ----------------
def tg(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return requests.post(url, json=payload, timeout=15).json()


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


def send_new(name, text, signature, state, silent=True):
    """پیام جدید (بی‌صدا) می‌فرستد و شناسه‌اش را برای ویرایش‌های بعدی نگه می‌دارد."""
    payload = {"chat_id": CHANNEL_ID, "text": text}
    if silent:
        payload["disable_notification"] = True
    result = tg("sendMessage", payload)
    if result.get("ok"):
        state[name] = {"message_id": result["result"]["message_id"], "sig": signature}
        return True
    print(f"ارسال پیام «{name}» ناموفق بود:", result)
    return False


def publish_group(name, body, signature, state):
    """
    اگر قیمت‌ها با آخرین پیام یکی بود، همان پیام را ویرایش می‌کند (فقط زمان بروزرسانی).
    وگرنه پیام جدید (بی‌صدا) می‌فرستد.
    """
    text = with_footer(body)
    last = state.get(name) or {}
    message_id = last.get("message_id")

    if message_id and last.get("sig") == signature:
        result = tg("editMessageText", {
            "chat_id": CHANNEL_ID,
            "message_id": message_id,
            "text": text,
        })
        desc = str(result.get("description", "")).lower()
        if result.get("ok") or "not modified" in desc:
            print(f"«{name}»: قیمت‌ها تغییری نکرده؛ فقط زمان بروزرسانی ویرایش شد.")
            return True
        if "not found" in desc or "can't be edited" in desc or "message_id_invalid" in desc:
            print(f"«{name}»: پیام قبلی پیدا نشد؛ پیام جدید می‌فرستم.")
            return send_new(name, text, signature, state)
        print(f"ویرایش «{name}» ناموفق بود:", result)
        return False

    return send_new(name, text, signature, state)


# ---------------- جمع‌بندی شبانه ----------------
def build_summary(current, t):
    """
    متن جمع‌بندی: کمترین و بیشترین قیمت امروز هر آیتم، از فیلدهای l و h فید tgju.
    اگر هیچ آیتمی کمترین و بیشترین نداشت None برمی‌گرداند.
    """
    blocks = []
    for emoji, name, key in SUMMARY_ITEMS:
        entry = current.get(key)
        if not entry:
            print(f"جمع‌بندی: کلید {key} در فید نبود.")
            continue
        try:
            low = to_number(entry["l"]) / 10
            high = to_number(entry["h"]) / 10
        except Exception as e:
            print(f"جمع‌بندی: کمترین/بیشترین {key} خوانده نشد: {e} | داده: {entry}")
            continue
        if low <= 0 or high < low:
            print(f"جمع‌بندی: مقدار نامعتبر برای {key}: کمترین={low} بیشترین={high}")
            continue
        blocks.append(
            f"{emoji} {name}\n"
            f"{DOWN_EMOJI} کمترین: {fa(low)} تومان\n"
            f"{UP_EMOJI} بیشترین: {fa(high)} تومان"
        )
    if not blocks:
        return None
    day_name = WEEKDAYS[t.weekday()]
    date_text = jalali_date_key(t).translate(PERSIAN_DIGITS)
    header = f"{SUMMARY_TITLE}\n🗓 {day_name} {date_text}"
    return rtl(header + "\n\n" + "\n\n".join(blocks) + f"\n\n{CHANNEL_TAG}")


def send_summary(current, t):
    """جمع‌بندی را (با اعلان) به کانال می‌فرستد. اگر فرستاده شد True برمی‌گرداند."""
    if not current:
        print("فید tgju در دسترس نبود؛ جمع‌بندی ارسال نشد.")
        return False
    text = build_summary(current, t)
    if text is None:
        print("هیچ آیتمی برای جمع‌بندی پیدا نشد؛ ارسال نشد.")
        return False
    result = tg("sendMessage", {"chat_id": CHANNEL_ID, "text": text})
    if result.get("ok"):
        print("جمع‌بندی شبانه ارسال شد.")
        return True
    print("ارسال جمع‌بندی ناموفق بود:", result)
    return False


# ---------------- نظرسنجی و آموزش روزانه ----------------
def send_poll(state, record=True):
    """نظرسنجی روزانه (ناشناس). نتیجه‌ی آرا بعد از رأی دادن برای هر کاربر نمایش داده می‌شود."""
    idx = state.get("poll_index", 0) % len(POLL_ASSETS)
    asset = POLL_ASSETS[idx]
    payload = {
        "chat_id": CHANNEL_ID,
        "question": f"📊 پیش‌بینی شما: قیمت {asset} در ۲۴ ساعت آینده چه تغییری می‌کنه؟",
        "options": [{"text": o} for o in POLL_OPTIONS],
        "is_anonymous": True,
        "allows_multiple_answers": False,
    }
    result = tg("sendPoll", payload)
    if result.get("ok"):
        print(f"نظرسنجی روزانه ارسال شد ({asset}).")
        if record:
            state["poll_index"] = idx + 1
        return True
    print("ارسال نظرسنجی ناموفق بود:", result)
    return False


def load_lessons():
    try:
        with open(LESSONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [x for x in data if x.get("title") and x.get("body")]
    except Exception as e:
        print(f"فایل آموزش‌ها خوانده نشد ({LESSONS_FILE}): {e}")
        return []


def send_lesson(state, record=True):
    """آموزش شبانه: هر شب مورد بعدی از lessons.json؛ بعد از آخرین، دوباره از اول."""
    lessons = load_lessons()
    if not lessons:
        return True          # فایل نیست؛ خطا حساب نمی‌شود
    idx = state.get("lesson_index", 0) % len(lessons)
    lesson = lessons[idx]
    text = rtl(f"📚 آموزش امشب\n\n{lesson['title']}\n\n{lesson['body']}\n\n"
               f"⚠️ مطلب آموزشی عمومی است و توصیه‌ی مالی نیست.\n\n{CHANNEL_TAG}")
    result = tg("sendMessage", {"chat_id": CHANNEL_ID, "text": text})
    if result.get("ok"):
        print(f"آموزش شماره‌ی {idx + 1} ارسال شد.")
        if record:
            state["lesson_index"] = idx + 1
        return True
    print("ارسال آموزش ناموفق بود:", result)
    return False


def send_daily_items(t, minutes, state):
    """آموزش شبانه را اگر وقتش رسیده و امروز فرستاده نشده، می‌فرستد."""
    today = jalali_date_key(t)
    if minutes >= LESSON_MINUTE and state.get("lesson_date") != today:
        if send_lesson(state):
            state["lesson_date"] = today
            return True
        return False
    return True


def poll_slot_date(t, minutes):
    """نظرسنجی کدام روز را پوشش می‌دهد: از ۲۲:۳۰ همان روز تا ۱۰ صبحِ فردا. بیرون از این بازه None."""
    if minutes >= SUMMARY_MINUTE:
        return jalali_date_key(t)
    if minutes < POLL_FALLBACK_END_MINUTE:
        return jalali_date_key(t - timedelta(days=1))
    return None


def maybe_send_poll(t, minutes, state, wait_for_summary):
    """
    نظرسنجی روزانه را (با اعلان) می‌فرستد، اگر برای این «شب» هنوز فرستاده نشده.
    در ساعت سکوت منتظر می‌ماند تا جمع‌بندی رفته باشد (تا نظرسنجی آخرین پیام شب باشد).
    بعد از ۰۱:۰۰ اگر هنوز نرفته بود، همان لحظه می‌فرستد تا از دست نرود.
    """
    slot = poll_slot_date(t, minutes)
    if slot is None or state.get("poll_date") == slot:
        return True
    if wait_for_summary and state.get("summary_date") != slot:
        return True
    if send_poll(state):
        state["poll_date"] = slot
        return True
    return False


# ---------------- اجرا ----------------
def run_once(force=None):
    """force: None | "summary" | "poll" | "lesson" (ارسال فوری برای تست؛ وضعیت ذخیره نمی‌شود)"""
    t = tehran_now()
    minutes = t.hour * 60 + t.minute
    evening = minutes >= SUMMARY_MINUTE                       # ۲۲:۳۰ تا ۲۳:۵۹
    quiet = evening or minutes < QUIET_END_MINUTE             # ۲۲:۳۰ تا ۰۱:۰۰

    if force == "summary":
        return send_summary(load_feed(), t)
    if force == "poll":
        return send_poll(load_state(), record=False)
    if force == "lesson":
        return send_lesson(load_state(), record=False)

    state = load_state()

    # ---- ساعت سکوت: جمع‌بندی، بعدش نظرسنجی (آخرین پیام شب)؛ بقیه‌ی پیام‌ها متوقف ----
    if quiet:
        before_q = json.dumps(state, sort_keys=True)
        today = jalali_date_key(t)
        ok = True
        if evening and state.get("summary_date") != today:
            if send_summary(load_feed(), t):
                state["summary_date"] = today
                save_state(state)
            else:
                return False
        try:
            ok = maybe_send_poll(t, minutes, state, wait_for_summary=True)
        except Exception as e:
            print(f"خطا در نظرسنجی: {e}")
            ok = False
        if json.dumps(state, sort_keys=True) != before_q:
            save_state(state)
        else:
            print("ساعت سکوت (۲۲:۳۰ تا ۰۱:۰۰)؛ پیام قیمت ارسال یا ویرایش نشد.")
        return ok

    # ---- روال عادی ----
    before = json.dumps(state, sort_keys=True)
    ok = True

    prices = fetch_prices()
    if prices:
        groups = [
            ("currency", CURRENCY_TITLE, CURRENCY_SECTIONS),
            ("gold", GOLD_TITLE, GOLD_SECTIONS),
        ]
        for name, title, sections in groups:
            built = build_group(title, sections, prices)
            if built is None:
                print(f"برای «{name}» هیچ قیمتی نبود؛ رد شد.")
                continue
            body, signature = built
            try:
                ok = publish_group(name, body, signature, state) and ok
            except Exception as e:
                print(f"خطا در «{name}»: {e}")
                ok = False
    else:
        print("هیچ قیمتی دریافت نشد؛ پیام قیمت ارسال نشد.")
        ok = False

    # آموزش و نظرسنجی به فید وابسته نیستند. نظرسنجی اینجا فقط «جبرانی» است:
    # اگر شب قبل نرفته بود، اولین فرصت بعد از ۰۱:۰۰ (تا ۱۰ صبح) می‌رود و آخرین پیام می‌شود.
    try:
        ok = send_daily_items(t, minutes, state) and ok
        ok = maybe_send_poll(t, minutes, state, wait_for_summary=False) and ok
    except Exception as e:
        print(f"خطا در برنامه‌ی روزانه: {e}")
        ok = False

    if json.dumps(state, sort_keys=True) != before:
        save_state(state)
    return ok


def main():
    if not (BOT_TOKEN and CHANNEL_ID):
        raise SystemExit("BOT_TOKEN و CHANNEL_ID را تنظیم کنید.")

    print(f"price_bot نسخه‌ی {BOT_VERSION}")
    force = next((f[2:] for f in ("--summary", "--poll", "--lesson") if f in sys.argv), None)

    # حالت یک‌بار اجرا (برای گیت‌هاب): python3 price_bot.py --once
    if "--once" in sys.argv:
        sys.exit(0 if run_once(force) else 1)

    # حالت همیشه روشن (برای سرور)
    while True:
        try:
            run_once()
        except Exception as e:
            print("خطا:", e)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
