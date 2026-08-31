import os
import re
import json
import time
from threading import Thread
from flask import Flask
import telebot
from pypdf import PdfReader
import google.generativeai as genai

# 1. خادم Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Kasnazani Bot is running 24/7!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

keep_alive()

# 2. البيانات والمفاتيح (ضع مفتاحك هنا مباشرة)
TOKEN = os.environ.get("BOT_TOKEN","8934001695:AAEdzd-JNyasVh7RTpk4eniJ2HFwNx0K-wg")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY","AQ.Ab8RN6JWEMuS1iUQeN3yRYCz-vBcj2P8EIzL6gEqsVvIZxQXrg")

# تهيئة المفتاح
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

ADMIN_ID = 8032030029
DATA_FILE = "library.json"

bot = telebot.TeleBot(TOKEN)

# 3. حفظ وقراءة البيانات
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

library = load_data()

# 4. الأوامر ورفع الملفات
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "أهلاً بك في بوت المكتبة والمستندات!\nأرسل ملفات PDF للرفع، أو اطرح أي سؤال للإجابة عنه.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "عذراً، رفع الملفات متاح للمشرفين فقط.")
        return

    file_name = message.document.file_name
    if not file_name.lower().endswith('.pdf'):
        bot.reply_to(message, "الرجاء إرسال ملف بصيغة PDF فقط.")
        return

    msg = bot.reply_to(message, "جاري قراءة وتخزين الكتاب...")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        temp_filename = f"temp_{int(time.time())}.pdf"
        with open(temp_filename, 'wb') as f:
            f.write(downloaded_file)

        reader = PdfReader(temp_filename)
        chunks = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                chunks.append({"page": i + 1, "text": text})
        
        os.remove(temp_filename)

        if not chunks:
            bot.edit_message_text("لم يتم العثور على نصوص قابلة للقراءة.", chat_id=message.chat.id, message_id=msg.message_id)
            return

        book_key = file_name.replace(".pdf", "")
        library[book_key] = chunks
        save_data(library)

        bot.edit_message_text(f"تمت إضافة الكتاب '{book_key}' بنجاح! الإجمالي: {len(chunks)} صفحة.", chat_id=message.chat.id, message_id=msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"خطأ في المعالجة: {e}", chat_id=message.chat.id, message_id=msg.message_id)

@bot.message_handler(func=lambda message: True)
def handle_query(message):
    query = message.text
    if not library:
        bot.reply_to(message, "المكتبة فارغة حالياً.")
        return

    bot.send_chat_action(message.chat.id, 'typing')

    context_str = ""
    for book_name, chunks in library.items():
        context_str += f"\n--- الكتاب: {book_name} ---\n"
        for chunk in chunks[:15]:
            context_str += f"[صفحة {chunk['page']}]: {chunk['text'][:300]}...\n"

    prompt = f"بناءً على المستندات التالية:\n{context_str}\n\nأجب عن السؤال التالي بدقة: {query}"

    try:
        response = model.generate_content(prompt)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"خطأ في توليد الإجابة: {e}")

if __name__ == "__main__":
    bot.remove_webhook()
    bot.infinity_polling()
