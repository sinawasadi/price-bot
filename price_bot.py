#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات قیمت لحظه‌ای ارز، طلا و نقره برای کانال تلگرام (منبع قیمت: tgju)

طرز کار:
  - قیمت‌ها را از فید زنده‌ی خود tgju می‌گیرد (همان فیدی که سایت برای بروزرسانی لحظه‌ای استفاده می‌کند).
  - هر بار یک پیام جدید در کانال می‌فرستد.

اجرا:
  pip install requests
  export BOT_TOKEN="توکن ربات از BotFather"
  export CHANNEL_ID="@your_channel"      # ربات باید مدیر کانال باشد
  python3 price_bot.py --once            # یک بار اجرا (برای گیت‌هاب)
  python3 price_bot.py                   # همیشه روشن، هر ۱۰ دقیقه
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# ---------------- تنظیمات ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

INTERVAL_SECONDS = 600          # هر ۱۰ دقیقه (فقط در حالت سرور)

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

# (نام نمایشی، کلید tgju)
# کلید دلار، یورو، درهم، طلای ۱۸ عیار و سکه امامی در منابع تأیید شده‌اند.
# کلید پوند، طلای ۲۴ و نقره را حدس زده‌ام؛ اگر در فید نبودند فقط از آن‌ها می‌گذرد
# و در گزارش اجرا اسمشان را می‌نویسد.
ITEMS = [
    ("دلار آمریکا", "price_dollar_rl"),
    ("یورو", "price_eur"),
    ("پوند", "price_gbp"),
    ("درهم امارات", "price_aed"),
    ("طلای ۱۸ عیار (هر گرم)", "geram18"),
    ("طلای ۲۴ عیار (هر گرم)", "geram24"),
    ("سکه امامی", "sekee"),
    ("نقره ۹۲۵ (هر گرم)", "silver_925"),
]

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


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


def fetch_prices():
    """
    خروجی: {کلید: (قیمت به تومان، جهت تغییر)}
    قیمت‌های tgju به ریال هستند و اینجا به تومان تبدیل می‌شوند.
    """
    current = load_feed()
    if not current:
        return {}

    result = {}
    for _title, key in ITEMS:
        entry = current.get(key)
        if not entry:
            print(f"کلید در فید نبود (از آن گذشتم): {key}")
            continue
        try:
            toman = to_number(entry["p"]) / 10
            direction = entry.get("dt", "")
            result[key] = (toman, direction)
        except Exception as e:
            print(f"قیمت {key} خوانده نشد: {e} | داده: {entry}")
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


# ---------------- ساخت متن پیام ----------------
def fa(number):
    """عدد را با جداکننده هزارگان و رقم فارسی برمی‌گرداند."""
    return f"{int(number):,}".replace(",", "٬").translate(PERSIAN_DIGITS)


def build_message(prices):
    lines = ["📊 قیمت لحظه‌ای بازار", ""]
    for title, key in ITEMS:
        if key not in prices:
            continue
        toman, direction = prices[key]
        arrow = {"high": " 🔺", "low": " 🔻"}.get(direction, "")
        lines.append(f"▫️ {title}: {fa(toman)} تومان{arrow}")
    lines += ["", f"🕒 آخرین بروزرسانی: {jalali_stamp()} (به وقت تهران)"]
    return "\n".join(lines)


# ---------------- تلگرام ----------------
def tg(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return requests.post(url, json=payload, timeout=15).json()


def publish(text):
    """هر بار یک پیام جدید در کانال می‌فرستد. اگر موفق بود True برمی‌گرداند."""
    result = tg("sendMessage", {"chat_id": CHANNEL_ID, "text": text})
    if result.get("ok"):
        return True
    print("ارسال ناموفق بود:", result)
    return False


# ---------------- اجرا ----------------
def run_once():
    """یک بار قیمت می‌گیرد و یک پیام جدید در کانال می‌فرستد."""
    prices = fetch_prices()
    if not prices:
        print("هیچ قیمتی دریافت نشد؛ پیامی ارسال نشد.")
        return False
    return publish(build_message(prices))


def main():
    if not (BOT_TOKEN and CHANNEL_ID):
        raise SystemExit("BOT_TOKEN و CHANNEL_ID را تنظیم کنید.")

    # حالت یک‌بار اجرا (برای گیت‌هاب): python3 price_bot.py --once
    if "--once" in sys.argv:
        sys.exit(0 if run_once() else 1)

    # حالت همیشه روشن (برای سرور)
    while True:
        try:
            run_once()
        except Exception as e:
            print("خطا:", e)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
