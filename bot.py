import os
import re
import json
import time
from threading import Thread
from flask import Flask
import telebot
from pypdf import PdfReader
from google import genai
from google.genai.errors import APIError

# ==========================================
# 1. خادم ويب وهمي لإبقاء البوت شغالاً على Render
# ==========================================
app = Flask(_name_)

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

# ==========================================
# 2. الإعدادات والمفاتيح
# ==========================================
# ضع التوكن ومفتاح API الخاص بك هنا بين التنصيص
TOKEN = os.environ.get("BOT_TOKEN","8934001695:AAEdzd-JNyasVh7RTpk4eniJ2HFwNx0K-wg")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6JWEMuS1iUQeN3yRYCz-vBcj2P8EIzL6gEqsVvIZxQXrg")

ADMIN_ID = 8032030029
DATA_FILE = "library.json"

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 3. إدارة بيانات المكتبة
# ==========================================
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

# ==========================================
# 4. دالة الاستجابة مع الذكاء الاصطناعي
# ==========================================
def ask_gemini_with_retry(prompt, retries=3, delay=5):
    for attempt in range(retries):
        try:
            response = ai_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            return response.text
        except APIError as e:
            if e.code == 503 and attempt < retries - 1:
                time.sleep(delay)
                continue
            raise e

# ==========================================
# 5. معالجة الأوامر والرسائل
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في بوت المكتبة والمستندات!\n\n"
        "يمكنك إرسال أي سؤال وسأجيبك بناءً على الكتب والمستندات المتاحة.\n"
        "كما يمكنك إرسال ملفات PDF لإضافتها إلى المكتبة."
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "عذراً، رفع الملفات متاح للمشرفين فقط.")
        return

    file_name = message.document.file_name
    if not file_name.lower().endswith('.pdf'):
        bot.reply_to(message, "الرجاء إرسال ملف بصيغة PDF فقط.")
        return

    msg = bot.reply_to(message, "جاري تحميل وقراءة الملف...")
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
            bot.edit_message_text("لم يتم العثور على نصوص قابلة للقراءة في الملف.", chat_id=message.chat.id, message_id=msg.message_id)
            return

        book_key = file_name.replace(".pdf", "")
        library[book_key] = chunks
        save_data(library)

        bot.edit_message_text(f"تمت إضافة الكتاب '{book_key}' بنجاح! إجمالي الصفحات: {len(chunks)}", chat_id=message.chat.id, message_id=msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"حدث خطأ أثناء معالجة الملف: {e}", chat_id=message.chat.id, message_id=msg.message_id)

@bot.message_handler(func=lambda message: True)
def handle_query(message):
    query = message.text
    if not library:
        bot.reply_to(message, "المكتبة فارغة حالياً. يرجى رفع بعض الكتب أولاً.")
        return

    bot.send_chat_action(message.chat.id, 'typing')

    context_str = ""
    for book_name, chunks in library.items():
        context_str += f"\n--- الكتاب: {book_name} ---\n"
        for chunk in chunks[:15]:  # دمج أجزاء من المحتوى للبحث
            context_str += f"[صفحة {chunk['page']}]: {chunk['text'][:300]}...\n"

    prompt = f"""
أنت مساعد ذكي يجيب على أسئلة المستخدمين بدقة بناءً على كتب ومستندات المكتبة.
استخرج الإجابة المباشرة مع ذكر اسم الكتاب ورقم الصفحة إن أمكن.

المستندات المتاحة:
{context_str}

سؤال المستخدم:
{query}
"""
    try:
        reply = ask_gemini_with_retry(prompt)
        bot.reply_to(message, reply)
    except Exception as e:
        bot.reply_to(message, f"حدث خطأ في توليد الإجابة: {e}")

if _name_ == "_main_":
    print("جاري تشغيل البوت...")
    bot.infinity_polling(skip_pending_updates=True)
