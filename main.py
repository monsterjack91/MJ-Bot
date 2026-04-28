import asyncio
import requests
import re
import phonenumbers
from phonenumbers import geocoder
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
import hashlib
import json
import os

# =============== CONFIGURATION ===============
BOT_TOKEN = "8710436234:AAHVmpmTGSorQC_N587nN0OR_jvz-LgjM4g"   # APNA COMPLETE TOKEN YAHAN
GROUP_IDS = [-1003898262328]        # APNE GROUP IDS

API_URLS = [
    "https://number-panel-production-2c7c.up.railway.app/api/junaid?type=sms",
    "https://number-panel-production-2c7c.up.railway.app/api/junaidn?type=sms",
    "https://mis-panel-production.up.railway.app/api/Junaid?type=sms",
]

# Cache file to store last seen message IDs (order-independent)
CACHE_FILE = "seen_messages.json"

bot = Bot(token=BOT_TOKEN)

# =============== LOAD / SAVE CACHE ===============
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_cache(cache_set):
    with open(CACHE_FILE, "w") as f:
        json.dump(list(cache_set), f)

seen_ids = load_cache()

# =============== HELPER FUNCTIONS ===============

def extract_otp(message: str) -> str:
    if not message:
        return "N/A"
    patterns = [
        r'\b\d{3}-\d{3}\b', r'\b\d{6}\b', r'\b\d{4}\b',
        r'\b\d{5}\b', r'OTP[:\s]*(\d+)', r'code[:\s]*(\d+)'
    ]
    for pat in patterns:
        match = re.search(pat, message, re.IGNORECASE)
        if match:
            return match.group(0)
    return "N/A"

def mask_number(num: str) -> str:
    try:
        if not num.startswith('+'): num = '+' + num
        length = len(num)
        show_first = 5 if length >= 10 else 4
        show_last = 4 if length >= 10 else 2
        stars = '*' * (length - show_first - show_last)
        return f"{num[:show_first]}{stars}{num[-show_last:]}"
    except:
        return num

def get_country_flag(num: str):
    try:
        if not num.startswith('+'): num = '+' + num
        parsed = phonenumbers.parse(num)
        region = phonenumbers.region_code_for_number(parsed)
        if region:
            base = 127462 - ord('A')
            flag = chr(base + ord(region[0])) + chr(base + ord(region[1]))
            country = geocoder.description_for_number(parsed, "en")
            return country or "Unknown", flag
    except:
        pass
    return "Unknown", "🌍"

def generate_unique_id(record: dict) -> str:
    """Generate a unique ID for an OTP record (order-independent)"""
    # Use phone number + message first 50 chars + time (if exists)
    phone = record.get("number", "")
    msg = record.get("message", "")[:50]
    time = record.get("time", "")
    unique_str = f"{phone}|{msg}|{time}"
    return hashlib.md5(unique_str.encode()).hexdigest()

def parse_api_response(data):
    """Convert any API response to a list of dicts with keys: time, country, number, service, message"""
    records = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                records.append({
                    "time": item.get("time") or item.get("created_at") or "",
                    "country": item.get("country") or item.get("country_name") or "",
                    "number": item.get("number") or item.get("phone") or item.get("mobile") or "",
                    "service": item.get("service") or item.get("source") or "",
                    "message": item.get("message") or item.get("msg") or item.get("text") or "",
                })
            elif isinstance(item, list) and len(item) >= 5:
                records.append({
                    "time": item[0],
                    "country": item[1],
                    "number": item[2],
                    "service": item[3],
                    "message": item[4],
                })
    elif isinstance(data, dict):
        for key in ["aaData", "data", "records", "result"]:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        records.append({
                            "time": item.get("time") or item.get("created_at") or "",
                            "country": item.get("country") or "",
                            "number": item.get("number") or item.get("phone") or "",
                            "service": item.get("service") or "",
                            "message": item.get("message") or item.get("msg") or "",
                        })
                    elif isinstance(item, list) and len(item) >= 5:
                        records.append({
                            "time": item[0],
                            "country": item[1],
                            "number": item[2],
                            "service": item[3],
                            "message": item[4],
                        })
                break  # pehli valid key use karo
    return records

def get_all_otps(api_url):
    try:
        resp = requests.get(api_url, timeout=10)
        data = resp.json()
        return parse_api_response(data)
    except Exception as e:
        print(f"Error from {api_url}: {e}")
        return []

def is_new_record(record):
    uid = generate_unique_id(record)
    if uid in seen_ids:
        return False
    seen_ids.add(uid)
    save_cache(seen_ids)
    return True

def format_telegram(record):
    raw_msg = record["message"]
    otp = extract_otp(raw_msg)
    country_name, flag = get_country_flag(record["number"])
    masked = mask_number(record["number"])
    
    service_icon = "📱"
    svc = record["service"].lower()
    if "whatsapp" in svc: service_icon = "🟢"
    elif "telegram" in svc: service_icon = "🔵"
    elif "facebook" in svc: service_icon = "📘"
    
    return f"""
<b>{flag} New {country_name} {record['service']} OTP!</b>

<blockquote>🕰 Time: {record['time']}</blockquote>
<blockquote>{flag} Country: {country_name}</blockquote>
<blockquote>{service_icon} Service: {record['service']}</blockquote>
<blockquote>📞 Number: {masked}</blockquote>
<blockquote>🔑 OTP: <code>{otp}</code></blockquote>

<blockquote>📩 Full Message:</blockquote>
<pre>{raw_msg[:500]}</pre>

Powered by Monster Jack
"""

async def send_to_telegram(text):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📢 Channel", url="https://t.me/mjnumberchannelofficial"),
         InlineKeyboardButton("👨‍💻 Dev", url="t.me/Beginner_jack")]
    ])
    for gid in GROUP_IDS:
        try:
            await bot.send_message(gid, text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            print(f"Send error {gid}: {e}")

async def worker(api_url):
    print(f"✅ Worker started for {api_url}")
    while True:
        records = get_all_otps(api_url)
        for rec in records:
            if rec.get("number") and is_new_record(rec):
                msg = format_telegram(rec)
                await send_to_telegram(msg)
                print(f"📨 New OTP from {api_url}: {rec['number']}")
        await asyncio.sleep(5)

async def main():
    print("🚀 Bot started. Monitoring APIs (order-independent)...")
    tasks = [asyncio.create_task(worker(url)) for url in API_URLS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())