#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات قیمت لحظه‌ای ارز، طلا، سکه و نقره برای کانال تلگرام (منبع قیمت: tgju)

هر بار دو پیام می‌سازد:
  ۱) قیمت ارزها
  ۲) قیمت طلا، سکه (با حباب) و نقره

اگر قیمت‌های یک پیام نسبت به آخرین پیام ارسال‌شده تغییری نکرده باشد،
پیام تازه نمی‌فرستد و فقط «آخرین بروزرسانی» همان پیام قبلی را ویرایش می‌کند.

اجرا:
  pip install requests
  export BOT_TOKEN="توکن ربات از BotFather"
  export CHANNEL_ID="@your_channel"      # ربات باید مدیر کانال باشد
  python3 price_bot.py --once            # یک بار اجرا (برای گیت‌هاب)
  python3 price_bot.py --once --summary  # ارسال فوری جمع‌بندی شبانه (فقط برای تست)
  python3 price_bot.py                   # همیشه روشن، هر ۵ دقیقه
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone

import requests

# ---------------- تنظیمات ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

# آیدی کانال که در پایان هر پیام نوشته می‌شود
CHANNEL_TAG = "@Hypertech_ir"

INTERVAL_SECONDS = 300          # فقط در حالت همیشه روشن

# جمع‌بندی شبانه: از این ساعت (به وقت تهران) یک پیام جمع‌بندی می‌رود و تا ساعت پایان سکوت
# هیچ پیام قیمتی ارسال یا ویرایش نمی‌شود.
SUMMARY_MINUTE = 22 * 60 + 30   # ۲۲:۳۰
QUIET_END_MINUTE = 1 * 60       # ۰۱:۰۰ بامداد
STATE_FILE = "state.json"       # شناسه و قیمت آخرین پیام‌ها اینجا نگه داشته می‌شود

# اموجی جهت تغییر قیمت. اموجی «فلش سبز رو به بالا» وجود ندارد؛
# نزدیک‌ترین حالت دایره‌ی رنگی کنار فلش است. اگر خواستید اینجا عوضش کنید.
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
    ],
]

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

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


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


def all_keys():
    keys = [k for sec in CURRENCY_SECTIONS + GOLD_SECTIONS for (_e, _t, k) in sec]
    return keys


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


def fetch_prices(current=None):
    """
    خروجی: {کلید: (قیمت به تومان، جهت تغییر)}
    قیمت‌های tgju به ریال هستند و اینجا به تومان تبدیل می‌شوند.
    اگر فید داده نشود، خودش می‌گیرد.
    """
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
            result[key] = (to_number(entry["p"]) / 10, entry.get("dt", ""))
        except Exception as e:
            print(f"قیمت {key} خوانده نشد: {e} | داده: {entry}")

    if missing:
        print("کلیدهای زیر در فید نبودند (از آن‌ها گذشتم):", missing)
        hints = ("sek", "nim", "rob", "geram", "silver", "gold", "gbp", "aed", "blubber", "bubble")
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


# ---------------- ساخت متن پیام‌ها ----------------
def fa(number):
    """عدد را با جداکننده هزارگان و رقم فارسی برمی‌گرداند (منفی هم پشتیبانی می‌شود)."""
    sign = "−" if number < 0 else ""
    text = f"{abs(int(round(number))):,}".replace(",", "٬")
    return sign + text.translate(PERSIAN_DIGITS)


def arrow(direction):
    if direction == "high":
        return " " + UP_EMOJI
    if direction == "low":
        return " " + DOWN_EMOJI
    return ""


def build_group(title, sections, prices):
    """متن بدنه‌ی پیام (بدون خط زمان) و امضای قیمت‌ها را برمی‌گرداند.
    اگر هیچ قیمتی از این گروه نبود، None برمی‌گرداند."""
    blocks = []
    signature = {}
    for section in sections:
        lines = []
        for emoji, name, key in section:
            if key not in prices:
                continue
            toman, direction = prices[key]
            signature[key] = int(round(toman))
            lines.append(f"{emoji} {name}: {fa(toman)} تومان{arrow(direction)}")
        if lines:
            blocks.append("\n".join(lines))
    if not blocks:
        return None
    body = title + "\n\n" + "\n\n".join(blocks)
    return body, signature


def with_footer(body):
    return f"{body}\n\n🕒 آخرین بروزرسانی: {jalali_stamp()} (به وقت تهران)\n\n{CHANNEL_TAG}"


# ---------------- تلگرام ----------------
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


def send_new(name, text, signature, state):
    result = tg("sendMessage", {"chat_id": CHANNEL_ID, "text": text})
    if result.get("ok"):
        state[name] = {"message_id": result["result"]["message_id"], "sig": signature}
        return True
    print(f"ارسال پیام «{name}» ناموفق بود:", result)
    return False


def publish_group(name, body, signature, state):
    """
    اگر قیمت‌ها با آخرین پیام یکی بود، همان پیام را ویرایش می‌کند (فقط زمان بروزرسانی).
    وگرنه پیام جدید می‌فرستد.
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
def jalali_date_key(t):
    """کلید روز شمسی برای ذخیره در state، مثل 1405/07/26"""
    jy, jm, jd = gregorian_to_jalali(t.year, t.month, t.day)
    return f"{jy}/{jm:02d}/{jd:02d}"


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
    return header + "\n\n" + "\n\n".join(blocks) + f"\n\n{CHANNEL_TAG}"


def send_summary(current, t):
    """جمع‌بندی را به کانال می‌فرستد. اگر فرستاده شد True برمی‌گرداند."""
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


# ---------------- اجرا ----------------
def run_once(force_summary=False):
    t = tehran_now()
    minutes = t.hour * 60 + t.minute
    evening = minutes >= SUMMARY_MINUTE                       # ۲۲:۳۰ تا ۲۳:۵۹
    quiet = evening or minutes < QUIET_END_MINUTE             # ۲۲:۳۰ تا ۰۱:۰۰

    # ارسال فوری جمع‌بندی برای تست (وضعیت ذخیره نمی‌شود، جمع‌بندی واقعی شب هم ارسال می‌شود)
    if force_summary:
        return send_summary(load_feed(), t)

    state = load_state()

    # ---- ساعت سکوت: فقط جمع‌بندی (یک بار در روز)، بقیه‌ی پیام‌ها متوقف ----
    if quiet:
        today = jalali_date_key(t)
        if evening and state.get("summary_date") != today:
            if send_summary(load_feed(), t):
                state["summary_date"] = today
                save_state(state)
                return True
            return False
        print("ساعت سکوت (۲۲:۳۰ تا ۰۱:۰۰)؛ پیام قیمت ارسال یا ویرایش نشد.")
        return True

    # ---- روال عادی ----
    prices = fetch_prices()
    if not prices:
        print("هیچ قیمتی دریافت نشد؛ پیامی ارسال نشد.")
        return False

    before = json.dumps(state, sort_keys=True)
    ok = True

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

    if json.dumps(state, sort_keys=True) != before:
        save_state(state)
    return ok


def main():
    if not (BOT_TOKEN and CHANNEL_ID):
        raise SystemExit("BOT_TOKEN و CHANNEL_ID را تنظیم کنید.")

    # حالت یک‌بار اجرا (برای گیت‌هاب): python3 price_bot.py --once
    if "--once" in sys.argv:
        sys.exit(0 if run_once(force_summary="--summary" in sys.argv) else 1)

    # حالت همیشه روشن (برای سرور)
    while True:
        try:
            run_once()
        except Exception as e:
            print("خطا:", e)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
