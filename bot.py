import os
import json
import time
import re
import telebot
from telebot import apihelper
from pypdf import PdfReader
from groq import Groq

# تفعيل البروكسي الخاص بـ PythonAnywhere
apihelper.proxy = {'https': 'http://proxy.server:3128'}

# --- استدعاء المفاتيح بأمان عبر متغيرات البيئة ---
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ضع_توكن_التليجرام_هنا")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

ADMIN_ID = 8032030029
DATA_FILE = "library.json"

bot = telebot.TeleBot(TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# قائمة كلمات شائعة يجب تجاهلها في البحث
STOP_WORDS = {
    "ما", "من", "في", "على", "الى", "الي", "عن", "هل", "هو", "هي",
    "ذلك", "هذا", "هذه", "التي", "الذي", "ان", "أن", "كان", "كانت",
    "كل", "بعض", "غير", "او", "أو", "لا", "نعم", "ثم", "حتى", "اذا",
    "إذا", "قد", "لقد", "ماذا", "لماذا", "كيف", "اين", "أين", "متي",
    "متى", "كم", "لم", "لن", "ليس", "ما", "من", "مع", "بعد", "قبل",
    "قال", "قالت", "يقول", "رسول", "الله", "صلى", "عليه", "وسلم",
    "السلام", "عبدالله", "أبي", "ابن", "بنت", "يا", "أيها", "الناس"
}

def clean_for_search(text):
    """تجريد سريع للهمزات والتاء المربوطة وتوحيد الأحرف"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ؤ", "و", text)
    text = re.sub(r"ئ", "ي", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return text

def extract_keywords(query):
    """استخراج كلمات البحث مع تجاهل الكلمات الشائعة والقصيرة"""
    clean = clean_for_search(query)
    words = re.findall(r"\w+", clean)
    keywords = []
    for w in words:
        if len(w) > 2 and w not in STOP_WORDS:
            keywords.append(w)
    return keywords[:10]

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

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "📚 أهلاً بك في بوت المكتبة الشاملة!\n\n"
        "✍️ أرسل سؤالك مباشرة وسأبحث في الكتب المرفوعة.\n"
        "📖 سأنقل لك النصوص الحرفية مع ذكر المصدر ورقم الصفحة.\n\n"
        "⚡ البوت سريع جداً الآن!"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['books'])
def list_books(message):
    """عرض قائمة الكتب المرفوعة"""
    if not library:
        bot.reply_to(message, "المكتبة فارغة حالياً.")
        return
    
    books_list = "\n".join([f"📖 {name} ({len(chunks)} صفحة)" for name, chunks in library.items()])
    bot.reply_to(message, f"الكتب المتاحة:\n\n{books_list}")

@bot.message_handler(commands=['delete'])
def delete_book(message):
    """حذف كتاب (للمشرف فقط)"""
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "عذراً، هذا الأمر للمشرف فقط.")
        return
    
    try:
        book_name = message.text.replace('/delete', '').strip()
        if book_name in library:
            del library[book_name]
            save_data(library)
            bot.reply_to(message, f"✅ تم حذف كتاب: {book_name}")
        else:
            bot.reply_to(message, "❌ الكتاب غير موجود.\nاستخدم الأمر: /delete اسم_الكتاب")
    except Exception as e:
        bot.reply_to(message, f"خطأ: {e}")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "عذراً، رفع الملفات متاح للمشرفين فقط.")
        return

    file_name = message.document.file_name
    if not file_name.lower().endswith('.pdf'):
        bot.reply_to(message, "الرجاء إرسال ملف بصيغة PDF فقط.")
        return

    msg = bot.reply_to(message, "⏳ جاري قراءة الملف وتخزينه...")
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
            if text and text.strip():
                raw_text = text.strip()
                raw_text = re.sub(r'\n{3,}', '\n\n', raw_text)
                chunks.append({
                    "page": i + 1,
                    "text": raw_text,
                    "clean_text": clean_for_search(raw_text)
                })

        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        if not chunks:
            bot.edit_message_text("❌ لم يتم العثور على نصوص قابلة للقراءة في الملف.",
                                  chat_id=message.chat.id, message_id=msg.message_id)
            return

        book_key = file_name.replace(".pdf", "")
        
        if book_key in library:
            bot.edit_message_text(f"⏳ الكتاب {book_key} موجود مسبقاً، جاري التحديث...",
                                  chat_id=message.chat.id, message_id=msg.message_id)
        
        library[book_key] = chunks
        save_data(library)

        bot.edit_message_text(
            f"✅ تمت إضافة الكتاب '{book_key}' بنجاح!\n📄 إجمالي الصفحات: {len(chunks)}",
            chat_id=message.chat.id, message_id=msg.message_id
        )
    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء معالجة الملف: {e}",
                              chat_id=message.chat.id, message_id=msg.message_id)

def search_relevant_chunks(query, max_chunks=4, max_text_length=2500):
    """البحث عن أفضل الصفحات المطابقة للاستعلام"""
    keywords = extract_keywords(query)
    if not keywords:
        return "", []
    
    results = []
    
    for book_name, chunks in library.items():
        for chunk in chunks:
            clean = chunk.get('clean_text', '')
            if not clean:
                clean = clean_for_search(chunk['text'])
                chunk['clean_text'] = clean
            
            score = 0
            for kw in keywords:
                if kw in clean:
                    score += 1
                    score += min(clean.count(kw) - 1, 3) * 0.5
            
            if score > 0:
                first_200 = clean[:200]
                for kw in keywords:
                    if kw in first_200:
                        score += 0.5
                
                results.append((score, book_name, chunk))
    
    results.sort(key=lambda x: x[0], reverse=True)
    
    seen_books = set()
    unique_results = []
    for score, book_name, chunk in results:
        if book_name not in seen_books:
            unique_results.append((score, book_name, chunk))
            seen_books.add(book_name)
        if len(unique_results) >= max_chunks:
            break
    
    if not unique_results:
        for book_name, chunks in list(library.items())[:2]:
            for chunk in chunks[:2]:
                unique_results.append((0, book_name, chunk))
    
    context_parts = []
    sources = []
    
    for score, book_name, chunk in unique_results[:max_chunks]:
        text_to_send = chunk['text'][:max_text_length]
        context_parts.append(f"=== {book_name} - صفحة {chunk['page']} ===\n{text_to_send}")
        sources.append(f"{book_name} - ص{chunk['page']}")
    
    context = "\n\n".join(context_parts)
    return context, sources

def generate_answer_with_groq(query, context):
    """توليد الإجابة باستخدام Groq المجاني والسريع"""
    
    prompt = f"""أنت باحث إسلامي متخصص في استخراج النصوص من الكتب.
مهمتك: أجب على سؤال المستخدم بناءً على النصوص المرفقة فقط.

قواعد مهمة:
1. انقل النصوص الحرفية كما هي تماماً بدون تصرف أو اختصار.
2. إذا كان هناك تفاصيل أو قوائم أو أذكار، انقلها كاملة.
3. اذكر اسم الكتاب ورقم الصفحة بعد كل اقتباس.
4. إذا لم تجد الإجابة في النصوص، قل: "لم أجد هذه المعلومة في الكتب المتاحة".
5. لا تضف معلومات من عندك خارج النصوص.

النصوص المتاحة:
{context}

سؤال المستخدم: {query}

الإجابة:"""

    # ✅ قائمة موديلات متاحة للتجربة بالترتيب
    models_to_try = [
        "llama-3.3-70b-versatile",   # الأفضل والأدق
        "llama-3.2-3b-preview",     # احتياطي سريع
        "gemma2-9b-it",             # احتياطي إضافي
        "mixtral-8x7b-32768",       # احتياطي أخير
    ]
    
    last_error = None
    
    for model_name in models_to_try:
        try:
            response = groq_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "أنت باحث إسلامي دقيق في نقل النصوص من الكتب."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=2000,
                top_p=0.9,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = str(e)
            # إذا كان الخطأ "موديل غير موجود" جرب التالي
            if "model_not_found" in last_error or "does not exist" in last_error:
                continue
            # أي خطأ آخر
            raise Exception(f"فشل توليد الإجابة: {e}")
    
    raise Exception(f"جميع الموديلات غير متاحة. آخر خطأ: {last_error}")

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_query(message):
    try:
        query = message.text.strip()
        if not query:
            return

        if not library:
            bot.reply_to(message, "📚 المكتبة فارغة حالياً.\nأرسل PDF للمشرف لرفعه.")
            return

        bot.send_chat_action(message.chat.id, 'typing')
        
        context, sources = search_relevant_chunks(query)
        
        if not context:
            bot.reply_to(message, "لم أجد محتوى مناسباً في المكتبة.")
            return
        
        full_text = generate_answer_with_groq(query, context)
        
        if sources:
            sources_text = "\n\n📚 المصادر:\n" + "\n".join([f"• {s}" for s in sources])
            full_text += sources_text
        
        if len(full_text) > 4000:
            for i in range(0, len(full_text), 4000):
                bot.send_message(message.chat.id, full_text[i:i+4000])
                time.sleep(0.1)
        else:
            bot.reply_to(message, full_text)

    except Exception as e:
        error_msg = f"❌ حدث خطأ: {str(e)[:200]}"
        bot.reply_to(message, error_msg)
        print(f"Error: {e}")

@bot.message_handler(commands=['status'])
def bot_status(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    status_text = f"""
📊 حالة البوت:
✅ البوت يعمل
📚 عدد الكتب: {len(library)}
📄 إجمالي الصفحات: {sum(len(chunks) for chunks in library.values())}
💾 حجم البيانات: {os.path.getsize(DATA_FILE) / 1024:.1f} KB
⚡ الموديل: Groq Llama 3.3 (مجاني وسريع)
"""
    bot.reply_to(message, status_text)

if __name__ == "__main__":
    print("🚀 البوت يعمل الآن مع Groq المجاني...")
    print(f"📚 عدد الكتب المحملة: {len(library)}")
    
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"خطأ في الاستطلاع: {e}")
            time.sleep(3)
