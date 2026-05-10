import os
import json
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from faker import Faker
import random
import string
import pyotp
import firebase_admin
from firebase_admin import credentials, firestore
import io
import csv

# --- কনফিগারেশন ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8782856209:AAFyDqj1owGHut0ivuobBJxyg9j2PXpNrW4")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6670461311"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
bot_info = bot.get_me()
BOT_USERNAME = bot_info.username

fake = Faker()
user_sessions = {}

# --- Firebase সেটআপ ---
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
    print("Firebase connected successfully!")
except Exception as e:
    print(f"Firebase Error: {e}")

# --- সেটিংস এবং ডাটাবেস ইনিশিয়ালাইজেশন ---
def init_settings():
    settings_ref = db.collection('settings').document('app_settings')
    if not settings_ref.get().exists:
        settings_ref.set({'task_rate': 3.00, 'ref_commission': 1.00})

init_settings()

def get_settings():
    return db.collection('settings').document('app_settings').get().to_dict()

def init_user(chat_id, referrer_id=None):
    user_ref = db.collection('users').document(str(chat_id))
    if not user_ref.get().exists:
        user_ref.set({
            'balance': 0.0,
            'total_earned': 0.0,
            'withdrawn': 0.0,
            'submitted': 0,
            'approved': 0,
            'rejected': 0,
            'referred_users': 0,
            'referral_earnings': 0.0,
            'invited_by': str(referrer_id) if referrer_id else None,
            'banned': False,
            'lang': 'bn' # bn or en
        })
        if referrer_id:
            ref_ref = db.collection('users').document(str(referrer_id))
            if ref_ref.get().exists:
                ref_data = ref_ref.get().to_dict()
                settings = get_settings()
                ref_com = settings.get('ref_commission', 1.00)
                ref_ref.update({
                    'referred_users': firestore.Increment(1),
                    'balance': firestore.Increment(ref_com),
                    'referral_earnings': firestore.Increment(ref_com)
                })

def check_ban(chat_id):
    user_doc = db.collection('users').document(str(chat_id)).get()
    if user_doc.exists and user_doc.to_dict().get('banned', False):
        return True
    return False

# --- কীবোর্ড মেনু ---
def main_menu(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🚀 Start Task"), KeyboardButton("👤 Profile"))
    markup.add(KeyboardButton("🏆 Top 10"), KeyboardButton("👥 Referral"))
    markup.add(KeyboardButton("🌐 Language"))
    if is_admin:
        markup.add(KeyboardButton("⚙️ Admin Panel"))
    return markup

# (আগের task_menu, start_action_menu, step_2fa_menu, final_menu অপরিবর্তিত থাকবে)
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

# --- ডাটা জেনারেটর ---
def generate_ig_details():
    first, last = fake.first_name(), fake.last_name()
    username = f"{first.lower()}_{last.lower()}{random.randint(1000, 99999)}"[:18]
    password = ''.join(random.choices(string.ascii_letters + string.digits + "@#$", k=12))
    return f"{first} {last}", username, password

# --- ইউজার কমান্ড ও ফিচার ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if check_ban(chat_id):
        bot.send_message(chat_id, "⛔ আপনার একাউন্ট ব্যান করা হয়েছে।")
        return

    text = message.text.split()
    referrer = text[1] if len(text) > 1 else None
    init_user(chat_id, referrer)
    
    bot.send_message(chat_id, "স্বাগতম! কাজ শুরু করতে নিচের বাটন ব্যবহার করুন।", reply_markup=main_menu(chat_id == ADMIN_ID))

@bot.message_handler(func=lambda m: True)
def main_handler(message):
    chat_id = message.chat.id
    if check_ban(chat_id):
        return bot.send_message(chat_id, "⛔ আপনার একাউন্ট ব্যান করা হয়েছে।")

    text = message.text

    if text == "👤 Profile":
        user_data = db.collection('users').document(str(chat_id)).get().to_dict()
        settings = get_settings()
        msg = f"""👤 <b>প্রোফাইল</b>\n
📥 জমা দিয়েছেন: {user_data.get('submitted', 0)}
✅ অনুমোদিত: {user_data.get('approved', 0)}
❌ বাতিল: {user_data.get('rejected', 0)}\n
💵 প্রতি কাজ: {settings.get('task_rate', 0)} BDT
💰 মোট আয়: {user_data.get('total_earned', 0)} BDT\n
📤 উত্তোলন: {user_data.get('withdrawn', 0)} BDT\n
💰 <b>ব্যালেন্স: {user_data.get('balance', 0)} BDT</b>"""
        bot.send_message(chat_id, msg)

    elif text == "🏆 Top 10":
        users = db.collection('users').order_by('approved', direction=firestore.Query.DESCENDING).limit(10).stream()
        msg = "🏆 <b>টপ ১০ ইউজার (সর্বোচ্চ অনুমোদিত কাজ)</b>\n\n"
        for idx, u in enumerate(users, 1):
            msg += f"{idx}. ID: <code>{u.id}</code> - ✅ {u.to_dict().get('approved', 0)} কাজ\n"
        bot.send_message(chat_id, msg)

    elif text == "👥 Referral":
        user_data = db.collection('users').document(str(chat_id)).get().to_dict()
        settings = get_settings()
        ref_link = f"https://t.me/{BOT_USERNAME}?start={chat_id}"
        msg = f"""👥 <b>রেফারেল প্রোগ্রাম</b>\n
প্রতি রেফারে পাবেন: {settings.get('ref_commission', 0)} BDT
আপনার রেফার সংখ্যা: {user_data.get('referred_users', 0)} জন
রেফার থেকে আয়: {user_data.get('referral_earnings', 0)} BDT\n
🔗 <b>আপনার রেফারেল লিংক:</b>\n<code>{ref_link}</code>"""
        bot.send_message(chat_id, msg)

    elif text == "🌐 Language":
        bot.send_message(chat_id, "🌐 ভাষা পরিবর্তনের কাজ চলছে। (বর্তমানে শুধু বাংলা সমর্থিত)")

    elif text == "⚙️ Admin Panel" and chat_id == ADMIN_ID:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📄 User List", callback_data="adm_users"),
            InlineKeyboardButton("🔍 Search User", callback_data="adm_search")
        )
        markup.add(
            InlineKeyboardButton("📊 Statistics", callback_data="adm_stats"),
            InlineKeyboardButton("💰 Edit Rates", callback_data="adm_rates")
        )
        markup.add(
            InlineKeyboardButton("📢 Send Notice", callback_data="adm_notice"),
            InlineKeyboardButton("📥 Download IG Report", callback_data="adm_ig")
        )
        bot.send_message(chat_id, "🛠️ <b>অ্যাডমিন ড্যাশবোর্ড</b>", reply_markup=markup)

    # --- আগের টাস্কের ওয়ার্কফ্লো ---
    elif text == "🚀 Start Task":
        bot.send_message(chat_id, "পরবর্তী ধাপে যেতে ক্লিক করুন:", reply_markup=task_menu())

    elif text == "🔐 Instagram 2FA":
        rules = "📌 <b>রুলস:</b>\n১. ডিটেইলস কপি করে একাউন্ট খুলুন।\n২. 2FA সেটআপ করুন।\n৩. ডাটা সাবমিট করুন।"
        bot.send_message(chat_id, rules, reply_markup=start_action_menu())

    elif text == "▶️ Start":
        name, username, password = generate_ig_details()
        user_sessions[chat_id] = {'name': name, 'username': username, 'password': password}
        msg = f"✅ <b>আপনার ডিটেইলস</b>:\n\n👤 Name: <code>{name}</code>\n🆔 Username: <code>{username}</code>\n🔑 Password: <code>{password}</code>"
        bot.send_message(chat_id, msg, reply_markup=step_2fa_menu())

    elif text == "🔑 2FA Input":
        msg = bot.send_message(chat_id, "ইনস্টাগ্রামের <b>2FA Secret Code</b> দিন:", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, process_2fa_secret)

    elif text == "✅ Account Registered":
        if chat_id in user_sessions and '2fa_secret' in user_sessions[chat_id]:
            data = user_sessions[chat_id]
            doc_ref = db.collection('instagram_accounts').document(data['username'])
            doc_ref.set({
                'created_by': str(chat_id), 'name': data['name'], 'username': data['username'],
                'password': data['password'], '2fa_secret': data['2fa_secret'], 'status': 'unchecked',
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            db.collection('users').document(str(chat_id)).update({'submitted': firestore.Increment(1)})
            bot.send_message(chat_id, "🎉 একাউন্ট সেভ হয়েছে! চেকার বট চেক করার পর ব্যালেন্স যোগ হবে।", reply_markup=main_menu(chat_id == ADMIN_ID))
            del user_sessions[chat_id]
        else:
            bot.send_message(chat_id, "⚠️ সেশন পাওয়া যায়নি।", reply_markup=main_menu(chat_id == ADMIN_ID))

    elif text == "❌ Cancel":
        if chat_id in user_sessions: del user_sessions[chat_id]
        bot.send_message(chat_id, "ক্যানসেল করা হয়েছে।", reply_markup=main_menu(chat_id == ADMIN_ID))

def process_2fa_secret(message):
    chat_id = message.chat.id
    secret = message.text.replace(" ", "")
    try:
        otp_code = pyotp.TOTP(secret).now()
        user_sessions.setdefault(chat_id, {})['2fa_secret'] = secret
        bot.send_message(chat_id, f"✅ <b>OTP জেনারেট হয়েছে</b>:\n\n<code>{otp_code}</code>", reply_markup=final_menu())
    except:
        msg = bot.send_message(chat_id, "❌ Secret Code ভুল। আবার দিন:")
        bot.register_next_step_handler(msg, process_2fa_secret)

# --- এডমিন ইনলাইন হ্যান্ডলার ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID: return

    if call.data == "adm_users":
        users = db.collection('users').stream()
        file_content = "User ID | Balance | Banned\n-------------------------\n"
        for u in users:
            d = u.to_dict()
            file_content += f"{u.id} | {d.get('balance',0)} | {d.get('banned',False)}\n"
        
        bio = io.BytesIO(file_content.encode('utf-8'))
        bio.name = "users_list.txt"
        bot.send_document(chat_id, bio)

    elif call.data == "adm_search":
        msg = bot.send_message(chat_id, "🔍 ইউজারের Telegram ID দিন:")
        bot.register_next_step_handler(msg, admin_search_user)

    elif call.data == "adm_stats":
        u_count = len(list(db.collection('users').stream()))
        ig_count = len(list(db.collection('instagram_accounts').stream()))
        bot.send_message(chat_id, f"📊 <b>পরিসংখ্যান</b>\n\nমোট ইউজার: {u_count}\nমোট জমাকৃত কাজ: {ig_count}")

    elif call.data == "adm_rates":
        msg = bot.send_message(chat_id, "নতুন টাস্ক রেট এবং রেফার রেট স্পেস দিয়ে লিখুন (উদাঃ 3.50 1.50):")
        bot.register_next_step_handler(msg, admin_update_rates)

    elif call.data == "adm_notice":
        msg = bot.send_message(chat_id, "📢 নোটিশের টেক্সট লিখুন:")
        bot.register_next_step_handler(msg, admin_send_notice)

    elif call.data == "adm_ig":
        accounts = db.collection('instagram_accounts').stream()
        file_content = "Username,Password,2FA_Secret,Status,Created_By\n"
        for a in accounts:
            d = a.to_dict()
            file_content += f"{d.get('username')},{d.get('password')},{d.get('2fa_secret')},{d.get('status')},{d.get('created_by')}\n"
        
        bio = io.BytesIO(file_content.encode('utf-8'))
        bio.name = "instagram_reports.csv"
        bot.send_document(chat_id, bio)

def admin_search_user(message):
    uid = message.text
    user_doc = db.collection('users').document(uid).get()
    if user_doc.exists:
        d = user_doc.to_dict()
        msg = f"👤 <b>User Info ({uid})</b>\n\nব্যালেন্স: {d.get('balance')}\nকাজ জমা: {d.get('submitted')}\nব্যান: {d.get('banned')}"
        markup = InlineKeyboardMarkup()
        action = "unban" if d.get('banned') else "ban"
        markup.add(InlineKeyboardButton(f"🚫 {action.title()} User", callback_data=f"usr_{action}_{uid}"))
        bot.send_message(message.chat.id, msg, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ ইউজার পাওয়া যায়নি।")

@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_"))
def user_actions(call):
    action, uid = call.data.split('_')[1], call.data.split('_')[2]
    is_banned = True if action == "ban" else False
    db.collection('users').document(uid).update({'banned': is_banned})
    bot.answer_callback_query(call.id, f"User {uid} is now {action}ned!")
    bot.send_message(call.message.chat.id, f"✅ User {uid} has been {action}ned.")

def admin_update_rates(message):
    try:
        task_rate, ref_rate = map(float, message.text.split())
        db.collection('settings').document('app_settings').update({
            'task_rate': task_rate, 'ref_commission': ref_rate
        })
        bot.send_message(message.chat.id, f"✅ রেট আপডেট হয়েছে!\nTask: {task_rate}\nRef: {ref_rate}")
    except:
        bot.send_message(message.chat.id, "❌ ফরমেট ভুল হয়েছে।")

def admin_send_notice(message):
    notice = message.text
    users = db.collection('users').stream()
    count = 0
    bot.send_message(message.chat.id, "⏳ নোটিশ পাঠানো শুরু হয়েছে...")
    for u in users:
        try:
            bot.send_message(u.id, f"📢 <b>অ্যাডমিন নোটিশ:</b>\n\n{notice}")
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ {count} জন ইউজারকে নোটিশ পাঠানো সম্পন্ন হয়েছে।")

if __name__ == "__main__":
    print("Bot is polling with new features...")
    bot.infinity_polling()
