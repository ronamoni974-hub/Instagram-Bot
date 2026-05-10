import os
import json
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from faker import Faker
import random
import string
import pyotp
import firebase_admin
from firebase_admin import credentials, firestore

# --- এনভায়রনমেন্ট কনফিগারেশন ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8782856209:AAFyDqj1owGHut0ivuobBJxyg9j2PXpNrW4")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6670461311") )

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
fake = Faker()
user_sessions = {}

# --- Firebase সেটআপ (Render এর জন্য নিরাপদ পদ্ধতি) ---
firebase_cred_json = os.environ.get("FIREBASE_CRED")

try:
    if firebase_cred_json:
        cred_dict = json.loads(firebase_cred_json)
        cred = credentials.Certificate(cred_dict)
    else:
        # লোকাল টেস্টিং এর জন্য
        cred = credentials.Certificate("firebase_credentials.json")
        
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase connected successfully!")
except Exception as e:
    print(f"Firebase Error: {e}")

# --- ডাটাবেস ফাংশন ---
def init_user(chat_id):
    """ইউজারের ব্যালেন্স প্রোফাইল তৈরি করবে যদি না থাকে"""
    user_ref = db.collection('users').document(str(chat_id))
    if not user_ref.get().exists:
        user_ref.set({'balance': 0.0})

def save_ig_account(chat_id, data):
    try:
        doc_ref = db.collection('instagram_accounts').document(data['username'])
        doc_ref.set({
            'created_by': str(chat_id),
            'name': data.get('name'),
            'username': data.get('username'),
            'password': data.get('password'),
            '2fa_secret': data.get('2fa_secret'),
            'status': 'unchecked', # চেকার বট পরে এটি আপডেট করবে
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False

# --- কীবোর্ড মেনু ---
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🚀 Start Task"), KeyboardButton("💰 My Balance"))
    return markup

def task_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔐 Instagram 2FA"), KeyboardButton("❌ Cancel"))
    return markup

def start_action_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("▶️ Start"), KeyboardButton("❌ Cancel"))
    return markup

def step_2fa_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔑 2FA Input"), KeyboardButton("❌ Cancel"))
    return markup

def final_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("✅ Account Registered"), KeyboardButton("❌ Cancel"))
    return markup

# --- ডাটা জেনারেটর ---
def generate_ig_details():
    first = fake.first_name()
    last = fake.last_name()
    random_num = random.randint(1000, 99999)
    username = f"{first.lower()}_{last.lower()}{random_num}"[:18]
    password = ''.join(random.choices(string.ascii_letters + string.digits + "@#$", k=12))
    return f"{first} {last}", username, password

# --- ইউজার কমান্ড ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_user(message.chat.id)
    bot.send_message(message.chat.id, "স্বাগতম! কাজ শুরু করতে নিচের বাটন ব্যবহার করুন।", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "💰 My Balance")
def check_balance(message):
    chat_id = str(message.chat.id)
    user_doc = db.collection('users').document(chat_id).get()
    balance = user_doc.to_dict().get('balance', 0) if user_doc.exists else 0
    bot.send_message(message.chat.id, f"আপনার বর্তমান ব্যালেন্স: <b>{balance} Taka/Points</b>", reply_markup=main_menu())

# --- অ্যাডমিন প্যানেল ---
@bot.message_handler(commands=['addbalance'])
def add_balance(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "⛔ আপনি এই কমান্ড ব্যবহারের জন্য অনুমোদিত নন।")
        return
    
    try:
        # Command format: /addbalance <user_id> <amount>
        parts = message.text.split()
        target_user = parts[1]
        amount = float(parts[2])
        
        user_ref = db.collection('users').document(target_user)
        if user_ref.get().exists:
            current_balance = user_ref.get().to_dict().get('balance', 0)
            user_ref.update({'balance': current_balance + amount})
            bot.reply_to(message, f"✅ ইউজার {target_user} এর একাউন্টে {amount} ব্যালেন্স যোগ করা হয়েছে।")
            bot.send_message(target_user, f"🎉 অ্যাডমিন আপনার একাউন্টে {amount} ব্যালেন্স যোগ করেছেন!")
        else:
            bot.reply_to(message, "❌ ইউজার ডাটাবেসে পাওয়া যায়নি।")
    except Exception as e:
        bot.reply_to(message, "⚠️ সঠিক ফরম্যাট: `/addbalance user_id amount`\nউদাহরণ: `/addbalance 123456789 50`", parse_mode='Markdown')

# --- ওয়ার্কফ্লো হ্যান্ডলার ---
@bot.message_handler(func=lambda m: m.text in ["🚀 Start Task", "🔐 Instagram 2FA", "▶️ Start", "🔑 2FA Input", "✅ Account Registered", "❌ Cancel"])
def workflow_handler(message):
    chat_id = message.chat.id
    text = message.text

    if text == "🚀 Start Task":
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
            if save_ig_account(chat_id, user_sessions[chat_id]):
                bot.send_message(chat_id, "🎉 একাউন্ট সেভ হয়েছে! চেকার বট চেক করার পর ব্যালেন্স যোগ হবে।", reply_markup=main_menu())
                del user_sessions[chat_id]
            else:
                bot.send_message(chat_id, "❌ ডাটাবেস এরর।", reply_markup=final_menu())
        else:
            bot.send_message(chat_id, "⚠️ সেশন পাওয়া যায়নি।", reply_markup=main_menu())

    elif text == "❌ Cancel":
        if chat_id in user_sessions: del user_sessions[chat_id]
        bot.send_message(chat_id, "ক্যানসেল করা হয়েছে।", reply_markup=main_menu())

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

if __name__ == "__main__":
    print("Bot is polling...")
    bot.infinity_polling()
