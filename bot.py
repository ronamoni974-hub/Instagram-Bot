import os
import json
import time
import random
import string
import io
import threading
import requests
from datetime import datetime, timezone
from flask import Flask

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from faker import Faker
import pyotp
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. CONFIGURATION & SETUP
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8782856209:AAFyDqj1owGHut0ivuobBJxyg9j2PXpNrW4") # আপনার বটের টোকেন
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6670461311"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
try:
    BOT_USERNAME = bot.get_me().username
except:
    BOT_USERNAME = "@myinstatask_bot"

fake = Faker()
user_sessions = {}

# --- Firebase Initialization ---
firebase_cred_json = os.environ.get("FIREBASE_CRED")
try:
    if firebase_cred_json:
        cred_dict = json.loads(firebase_cred_json)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate("firebase_credentials.json")
        
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase connected successfully!")
except Exception as e:
    print(f"❌ Firebase Error: {e}")

# ==========================================
# 2. DATABASE FUNCTIONS
# ==========================================
def init_settings():
    settings_ref = db.collection('settings').document('app_settings')
    if not settings_ref.get().exists:
        settings_ref.set({'task_rate': 3.00, 'ref_commission': 1.00, 'check_delay_minutes': 5})

init_settings()

def get_settings():
    return db.collection('settings').document('app_settings').get().to_dict()

def init_user(chat_id, referrer_id=None):
    user_ref = db.collection('users').document(str(chat_id))
    if not user_ref.get().exists:
        user_ref.set({
            'balance': 0.0, 'total_earned': 0.0, 'withdrawn': 0.0,
            'submitted': 0, 'approved': 0, 'rejected': 0,
            'referred_users': 0, 'referral_earnings': 0.0,
            'invited_by': str(referrer_id) if referrer_id else None,
            'banned': False, 'lang': 'bn'
        })
        if referrer_id and str(referrer_id) != str(chat_id):
            ref_ref = db.collection('users').document(str(referrer_id))
            if ref_ref.get().exists:
                ref_com = get_settings().get('ref_commission', 1.00)
                ref_ref.update({
                    'referred_users': firestore.Increment(1),
                    'balance': firestore.Increment(ref_com),
                    'referral_earnings': firestore.Increment(ref_com)
                })

def check_ban(chat_id):
    user_doc = db.collection('users').document(str(chat_id)).get()
    return user_doc.exists and user_doc.to_dict().get('banned', False)

# ==========================================
# 3. KEYBOARDS & MENUS
# ==========================================
def main_menu(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🚀 Start Task"), KeyboardButton("👤 Profile"))
    markup.add(KeyboardButton("🏆 Top 10"), KeyboardButton("👥 Referral"))
    markup.add(KeyboardButton("🌐 Language"))
    if is_admin: markup.add(KeyboardButton("⚙️ Admin Panel"))
    return markup

def task_menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(KeyboardButton("🔐 Instagram 2FA"), KeyboardButton("❌ Cancel"))
    return m

def start_action_menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(KeyboardButton("▶️ Start"), KeyboardButton("❌ Cancel"))
    return m

def step_2fa_menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(KeyboardButton("🔑 2FA Input"), KeyboardButton("❌ Cancel"))
    return m

def final_menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(KeyboardButton("✅ Account Registered"), KeyboardButton("❌ Cancel"))
    return m

# ==========================================
# 4. INSTAGRAM ACCOUNT CHECKER & NOTIFIER
# ==========================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
]

def check_ig_alive(username):
    url = f"https://www.instagram.com/{username}/"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200: return True
        elif response.status_code == 404: return False
        else: return None
    except:
        return None

def notify_admin_for_manual_check(data, doc_id):
    username = data.get('username')
    user_id = data.get('created_by')
    
    msg = f"⚠️ <b>ম্যানুয়াল রিভিউ প্রয়োজন!</b>\n\n" \
          f"👤 User ID: <code>{user_id}</code>\n" \
          f"🆔 Username: <code>{username}</code>\n" \
          f"🔑 Password: <code>{data.get('password')}</code>\n" \
          f"🔐 2FA: <code>{data.get('2fa_secret')}</code>\n\n" \
          f"অটো-চেকার ব্যর্থ হয়েছে। ম্যানুয়ালি চেক করুন।"
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"man_app_{doc_id}_{user_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"man_rej_{doc_id}_{user_id}")
    )
    try:
        bot.send_message(ADMIN_ID, msg, reply_markup=markup)
    except Exception as e:
        print(f"Admin Notification Error: {e}")

# ==========================================
# 5. BACKGROUND AUTO-CHECKER THREAD
# ==========================================
def auto_checker_thread():
    while True:
        try:
            settings = get_settings()
            delay_mins = settings.get('check_delay_minutes', 5)
            task_rate = settings.get('task_rate', 3.00)
            now = datetime.now(timezone.utc)
            
            accounts = db.collection('instagram_accounts').where('status', '==', 'unchecked').stream()
            
            for acc in accounts:
                data = acc.to_dict()
                created_time = data.get('timestamp')
                if not created_time: continue
                
                time_diff_minutes = (now - created_time).total_seconds() / 60.0
                
                if time_diff_minutes >= delay_mins:
                    user_id = data.get('created_by')
                    username = data.get('username')
                    
                    is_valid = check_ig_alive(username)
                    
                    if is_valid is None:
                        db.collection('instagram_accounts').document(acc.id).update({'status': 'pending_manual'})
                        notify_admin_for_manual_check(data, acc.id)
                        try:
                            bot.send_message(user_id, f"⏳ আপনার একাউন্ট <code>{username}</code> নেটওয়ার্ক সমস্যার কারণে অটো-চেক করা সম্ভব হয়নি। এটি <b>ম্যানুয়াল রিভিউতে</b> পাঠানো হয়েছে।")
                        except: pass
                        continue 
                    
                    if is_valid:
                        db.collection('instagram_accounts').document(acc.id).update({'status': 'approved'})
                        db.collection('users').document(user_id).update({
                            'balance': firestore.Increment(task_rate),
                            'total_earned': firestore.Increment(task_rate),
                            'approved': firestore.Increment(1)
                        })
                        msg = f"✅ <b>Report approved, +{task_rate} BDT</b>\n✉ Comment: Account <code>{username}</code> is live."
                    else:
                        db.collection('instagram_accounts').document(acc.id).update({'status': 'rejected'})
                        db.collection('users').document(user_id).update({'rejected': firestore.Increment(1)})
                        msg = f"❌ <b>Report rejected.</b>\n✉ Comment: Account <code>{username}</code> is suspended."
                    
                    try: bot.send_message(user_id, msg)
                    except: pass
        except Exception as e:
            print(f"Checker Error: {e}")
            
        time.sleep(60)

# ==========================================
# 6. USER COMMANDS & WORKFLOW
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if check_ban(chat_id): return bot.send_message(chat_id, "⛔ আপনার একাউন্ট ব্যান করা হয়েছে।")
    
    text = message.text.split()
    referrer = text[1] if len(text) > 1 else None
    init_user(chat_id, referrer)
    
    bot.send_message(chat_id, "স্বাগতম! কাজ শুরু করতে নিচের বাটন ব্যবহার করুন।", reply_markup=main_menu(chat_id == ADMIN_ID))

@bot.message_handler(func=lambda m: True)
def main_handler(message):
    chat_id = message.chat.id
    if check_ban(chat_id): return
    text = message.text

    if text == "👤 Profile":
        user_data = db.collection('users').document(str(chat_id)).get().to_dict()
        settings = get_settings()
        msg = f"👤 <b>প্রোফাইল</b>\n\n📥 জমা দিয়েছেন: {user_data.get('submitted', 0)}\n✅ অনুমোদিত: {user_data.get('approved', 0)}\n❌ বাতিল: {user_data.get('rejected', 0)}\n\n💵 প্রতি কাজ: {settings.get('task_rate', 0)} BDT\n💰 মোট আয়: {user_data.get('total_earned', 0):.2f} BDT\n\n📤 উত্তোলন: {user_data.get('withdrawn', 0):.2f} BDT\n\n💰 <b>ব্যালেন্স: {user_data.get('balance', 0):.2f} BDT</b>"
        bot.send_message(chat_id, msg)

    elif text == "🏆 Top 10":
        users = db.collection('users').order_by('approved', direction=firestore.Query.DESCENDING).limit(10).stream()
        msg = "🏆 <b>টপ ১০ ইউজার</b>\n\n"
        for idx, u in enumerate(users, 1): msg += f"{idx}. ID: <code>{u.id}</code> - ✅ {u.to_dict().get('approved', 0)} কাজ\n"
        bot.send_message(chat_id, msg)

    elif text == "👥 Referral":
        user_data = db.collection('users').document(str(chat_id)).get().to_dict()
        settings = get_settings()
        ref_link = f"https://t.me/{BOT_USERNAME}?start={chat_id}"
        msg = f"👥 <b>রেফারেল প্রোগ্রাম</b>\n\nপ্রতি রেফারে: {settings.get('ref_commission', 0)} BDT\nমোট রেফার: {user_data.get('referred_users', 0)} জন\nরেফার আয়: {user_data.get('referral_earnings', 0):.2f} BDT\n\n🔗 <b>লিংক:</b>\n<code>{ref_link}</code>"
        bot.send_message(chat_id, msg)

    elif text == "🌐 Language": bot.send_message(chat_id, "🌐 ভাষা পরিবর্তনের কাজ চলছে।")

    elif text == "⚙️ Admin Panel" and chat_id == ADMIN_ID:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("📄 Users", callback_data="adm_users"), InlineKeyboardButton("🔍 Search", callback_data="adm_search"))
        markup.add(InlineKeyboardButton("📊 Stats", callback_data="adm_stats"), InlineKeyboardButton("💰 Rates", callback_data="adm_rates"))
        markup.add(InlineKeyboardButton("⏳ Timer", callback_data="adm_timer"), InlineKeyboardButton("📢 Notice", callback_data="adm_notice"))
        markup.add(InlineKeyboardButton("📥 Download Report", callback_data="adm_ig"))
        bot.send_message(chat_id, "🛠️ <b>অ্যাডমিন ড্যাশবোর্ড</b>", reply_markup=markup)

    elif text == "🚀 Start Task": bot.send_message(chat_id, "পরবর্তী ধাপে যান:", reply_markup=task_menu())

    elif text == "🔐 Instagram 2FA":
        rules = "📌 <b>রুলস:</b>\n১. ডিটেইলস কপি করে একাউন্ট খুলুন।\n২. 2FA সেটআপ করুন।\n৩. ডাটা সাবমিট করুন।"
        bot.send_message(chat_id, rules, reply_markup=start_action_menu())

    elif text == "▶️ Start":
        first, last = fake.first_name(), fake.last_name()
        username = f"{first.lower()}_{last.lower()}{random.randint(1000, 99999)}"[:18]
        password = ''.join(random.choices(string.ascii_letters + string.digits + "@#$", k=12))
        name = f"{first} {last}"
        user_sessions[chat_id] = {'name': name, 'username': username, 'password': password}
        msg = f"✅ <b>আপনার ডিটেইলস</b>:\n\n👤 Name: <code>{name}</code>\n🆔 Username: <code>{username}</code>\n🔑 Password: <code>{password}</code>"
        bot.send_message(chat_id, msg, reply_markup=step_2fa_menu())

    elif text == "🔑 2FA Input":
        msg = bot.send_message(chat_id, "ইনস্টাগ্রামের <b>2FA Secret Code</b> দিন:", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, process_2fa_secret)

    elif text == "✅ Account Registered":
        if chat_id in user_sessions and '2fa_secret' in user_sessions[chat_id]:
            data = user_sessions[chat_id]
            db.collection('instagram_accounts').document(data['username']).set({
                'created_by': str(chat_id), 'name': data['name'], 'username': data['username'],
                'password': data['password'], '2fa_secret': data['2fa_secret'], 'status': 'unchecked',
                'timestamp': datetime.now(timezone.utc)
            })
            db.collection('users').document(str(chat_id)).update({'submitted': firestore.Increment(1)})
            settings = get_settings()
            bot.send_message(chat_id, f"🎉 একাউন্ট সেভ হয়েছে! {settings.get('check_delay_minutes')} মিনিট পর রিপোর্ট আসবে।", reply_markup=main_menu(chat_id == ADMIN_ID))
            del user_sessions[chat_id]
        else:
            bot.send_message(chat_id, "⚠️ সেশন পাওয়া যায়নি।", reply_markup=main_menu(chat_id == ADMIN_ID))

    elif text == "❌ Cancel":
        if chat_id in user_sessions: del user_sessions[chat_id]
        bot.send_message(chat_id, "ক্যানসেল করা হয়েছে।", reply_markup=main_menu(chat_id == ADMIN_ID))

def process_2fa_secret(message):
    chat_id = message.chat.id
    secret = message.text.replace(" ", "")
    try:
        otp_code = pyotp.TOTP(secret).now()
        user_sessions.setdefault(chat_id, {})['2fa_secret'] = secret
        bot.send_message(chat_id, f"✅ <b>OTP জেনারেট হয়েছে</b>:\n\n<code>{otp_code}</code>", reply_markup=final_menu())
    except:
        msg = bot.send_message(chat_id, "❌ Secret Code ভুল। আবার দিন:")
        bot.register_next_step_handler(msg, process_2fa_secret)

# ==========================================
# 7. ADMIN HANDLERS & MANUAL REVIEW
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("man_"))
def manual_review_handler(call):
    if call.message.chat.id != ADMIN_ID: return
    parts = call.data.split('_')
    action, doc_id, user_id = parts[1], parts[2], parts[3]
    task_rate = get_settings().get('task_rate', 3.00)

    if action == "app":
        db.collection('instagram_accounts').document(doc_id).update({'status': 'approved'})
        db.collection('users').document(user_id).update({
            'balance': firestore.Increment(task_rate), 'total_earned': firestore.Increment(task_rate), 'approved': firestore.Increment(1)
        })
        try: bot.send_message(user_id, f"✅ <b>Report approved (Manual), +{task_rate} BDT</b>\nএকাউন্টটি অনুমোদিত হয়েছে।")
        except: pass
        bot.edit_message_text(f"✅ Approved: {doc_id}", call.message.chat.id, call.message.message_id)

    elif action == "rej":
        db.collection('instagram_accounts').document(doc_id).update({'status': 'rejected'})
        db.collection('users').document(user_id).update({'rejected': firestore.Increment(1)})
        try: bot.send_message(user_id, f"❌ <b>Report rejected (Manual)</b>\nএকাউন্টটি বাতিল করা হয়েছে।")
        except: pass
        bot.edit_message_text(f"❌ Rejected: {doc_id}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID: return

    if call.data == "adm_users":
        content = "ID | Balance | Banned\n" + "-"*20 + "\n"
        for u in db.collection('users').stream():
            content += f"{u.id} | {u.to_dict().get('balance',0)} | {u.to_dict().get('banned',False)}\n"
        bio = io.BytesIO(content.encode('utf-8'))
        bio.name = "users.txt"
        bot.send_document(chat_id, bio)

    elif call.data == "adm_ig":
        content = "Username,Password,2FA,Status,UserID\n"
        for a in db.collection('instagram_accounts').stream():
            d = a.to_dict()
            content += f"{d.get('username')},{d.get('password')},{d.get('2fa_secret')},{d.get('status')},{d.get('created_by')}\n"
        bio = io.BytesIO(content.encode('utf-8'))
        bio.name = "reports.csv"
        bot.send_document(chat_id, bio)

    elif call.data == "adm_stats":
        u_count = len(list(db.collection('users').stream()))
        ig_count = len(list(db.collection('instagram_accounts').stream()))
        bot.send_message(chat_id, f"📊 <b>পরিসংখ্যান</b>\n\nইউজার: {u_count}\nজমাকৃত কাজ: {ig_count}")

    elif call.data == "adm_rates":
        msg = bot.send_message(chat_id, "টাস্ক রেট এবং রেফার রেট স্পেস দিয়ে দিন (উদাঃ 3.5 1.5):")
        bot.register_next_step_handler(msg, lambda m: update_db_setting(m, 'rates'))

    elif call.data == "adm_timer":
        msg = bot.send_message(chat_id, "চেকার ডিলে টাইম দিন (মিনিটে):")
        bot.register_next_step_handler(msg, lambda m: update_db_setting(m, 'timer'))

    elif call.data == "adm_notice":
        msg = bot.send_message(chat_id, "নোটিশ লিখুন:")
        bot.register_next_step_handler(msg, send_global_notice)
        
    elif call.data == "adm_search":
        msg = bot.send_message(chat_id, "Telegram ID দিন:")
        bot.register_next_step_handler(msg, search_user)

def update_db_setting(message, type):
    try:
        if type == 'rates':
            task, ref = map(float, message.text.split())
            db.collection('settings').document('app_settings').update({'task_rate': task, 'ref_commission': ref})
            bot.send_message(message.chat.id, f"✅ আপডেট সম্পন্ন!\nTask: {task}, Ref: {ref}")
        elif type == 'timer':
            mins = int(message.text)
            db.collection('settings').document('app_settings').update({'check_delay_minutes': mins})
            bot.send_message(message.chat.id, f"⏳ টাইমার {mins} মিনিটে সেট করা হয়েছে।")
    except: bot.send_message(message.chat.id, "❌ ইনপুট ভুল হয়েছে।")

def send_global_notice(message):
    bot.send_message(message.chat.id, "⏳ পাঠানো হচ্ছে...")
    count = 0
    for u in db.collection('users').stream():
        try:
            bot.send_message(u.id, f"📢 <b>অ্যাডমিন নোটিশ:</b>\n\n{message.text}")
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ {count} জনকে পাঠানো হয়েছে।")

def search_user(message):
    uid = message.text
    doc = db.collection('users').document(uid).get()
    if doc.exists:
        d = doc.to_dict()
        markup = InlineKeyboardMarkup()
        action = "unban" if d.get('banned') else "ban"
        markup.add(InlineKeyboardButton(f"🚫 {action.title()} User", callback_data=f"usr_{action}_{uid}"))
        bot.send_message(message.chat.id, f"👤 <b>Info ({uid})</b>\n\nBalance: {d.get('balance')}\nBanned: {d.get('banned')}", reply_markup=markup)
    else: bot.send_message(message.chat.id, "❌ পাওয়া যায়নি।")

@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_"))
def user_ban_handler(call):
    action, uid = call.data.split('_')[1], call.data.split('_')[2]
    db.collection('users').document(uid).update({'banned': action == "ban"})
    bot.edit_message_text(f"✅ User {uid} is {action}ned.", call.message.chat.id, call.message.message_id)

# ==========================================
# 8. FLASK WEB SERVER & RUN BOT
# ==========================================
app = Flask(__name__)

@app.route('/')
def index():
    return "🚀 Instagram Micro-Job Bot is Live and Running Successfully!"

def run_bot_polling():
    print("🚀 Premium Bot is running...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    # ১. অটো-চেকার ব্যাকগ্রাউন্ডে চালু করা
    checker = threading.Thread(target=auto_checker_thread, daemon=True)
    checker.start()
    
    # ২. টেলিগ্রাম বট ব্যাকগ্রাউন্ডে চালু করা
    bot_thread = threading.Thread(target=run_bot_polling, daemon=True)
    bot_thread.start()
    
    # ৩. Flask ওয়েব সার্ভার মেইন থ্রেডে চালু করা (যাতে Render খুশি থাকে)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
