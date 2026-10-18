#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات قیمت لحظه‌ای ارز، طلا و نقره برای کانال تلگرام (منبع قیمت: tgju)

طرز کار:
  1) یک سرویس کوچک (tgju-api-go) قیمت‌ها را از سایت tgju می‌خواند و به شکل JSON می‌دهد.
  2) این اسکریپت از آن سرویس قیمت می‌گیرد و پیام ثابت کانال را ویرایش می‌کند.

اجرای سرویس قیمت (یک بار):
  docker run -d --restart always -p 8080:8080 ghcr.io/amiranmanesh/tgju-api-go:latest

اجرای ربات:
  pip install requests
  export BOT_TOKEN="توکن ربات از BotFather"
  export CHANNEL_ID="@your_channel"      # ربات باید مدیر کانال باشد
  python3 price_bot.py
"""

import os
import sys
import json
import time
from datetime import datetime

import requests

# ---------------- تنظیمات ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
TGJU_API_URL = os.environ.get("TGJU_API_URL", "http://localhost:8080")

INTERVAL_SECONDS = 300          # هر ۵ دقیقه
STATE_FILE = "state.json"

# (نام نمایشی، کلید tgju)
# کلیدهای دلار، یورو، طلای ۱۸ و ۲۴ عیار، نقره ۹۲۵ و سکه در مستندات پروژه آمده‌اند.
# کلید پوند و درهم را حدس زده‌ام؛ اگر پیدا نشدند ربات فقط از آن‌ها می‌گذرد
# و در خروجی برنامه اسمشان را می‌نویسد. فهرست همه کلیدها:
#   curl http://localhost:8080/v1/snapshot
ITEMS = [
    ("دلار آمریکا", "price_dollar_rl"),
    ("یورو", "price_eur"),
    ("پوند", "price_gbp"),
    ("درهم امارات", "price_aed"),
    ("طلای ۱۸ عیار (هر گرم)", "geram18"),
    ("طلای ۲۴ عیار (هر گرم)", "geram24"),
    ("سکه", "sekee"),
    ("نقره ۹۲۵ (هر گرم)", "silver_925"),
]


# ---------------- دریافت قیمت‌ها ----------------
def fetch_prices():
    """
    برای هر کلید یک درخواست به سرویس می‌زند.
    قیمت‌های tgju به ریال هستند؛ اینجا به تومان تبدیل می‌شوند.
    خروجی: {کلید: (قیمت به تومان، جهت تغییر)}
    """
    result = {}
    for _title, key in ITEMS:
        try:
            resp = requests.get(f"{TGJU_API_URL}/v1/items/{key}", timeout=15)
            if resp.status_code == 404:
                print(f"کلید پیدا نشد (از آن گذشتم): {key}")
                continue
            resp.raise_for_status()
            item = resp.json()
            toman = item["price"]["value"] / 10
            direction = item.get("change", {}).get("status", "")
            result[key] = (toman, direction)
        except Exception as e:
            print(f"خطا در گرفتن {key}: {e}")
    return result


# ---------------- ساخت متن پیام ----------------
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


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
    now = datetime.now().strftime("%Y/%m/%d  %H:%M").translate(PERSIAN_DIGITS)
    lines += ["", f"🕒 آخرین بروزرسانی: {now}"]
    return "\n".join(lines)


# ---------------- تلگرام ----------------
def tg(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return requests.post(url, json=payload, timeout=15).json()


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def publish(text):
    state = load_state()
    message_id = state.get("message_id")

    if message_id:
        result = tg("editMessageText", {
            "chat_id": CHANNEL_ID,
            "message_id": message_id,
            "text": text,
        })
        if result.get("ok"):
            return
        if "message is not modified" in str(result.get("description", "")):
            return
        print("ویرایش ناموفق بود:", result)

    result = tg("sendMessage", {"chat_id": CHANNEL_ID, "text": text})
    if result.get("ok"):
        state["message_id"] = result["result"]["message_id"]
        save_state(state)
    else:
        print("ارسال ناموفق بود:", result)


# ---------------- اجرا ----------------
def run_once():
    """یک بار قیمت می‌گیرد و پیام کانال را بروز می‌کند. اگر قیمتی نیامد False برمی‌گرداند."""
    prices = fetch_prices()
    if not prices:
        print("هیچ قیمتی دریافت نشد؛ پیام کانال تغییر نکرد.")
        return False
    publish(build_message(prices))
    return True


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
