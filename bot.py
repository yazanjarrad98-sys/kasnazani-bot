import telebot
import os
import re
import json
import time
from pypdf import PdfReader
from google import genai
from google.genai.errors import APIError

# ==================== الإعدادات والمفاتيح ====================
TOKEN = "8934001695:AAEdzd-JNyasVh7RTpk4eniJ2HFwNx0K-wg"
GEMINI_API_KEY = "AQ.Ab8RN6JWEMuS1iUQeN3yRYCz-vBcj2P8EIzL6gEqsVvIZxQXrg"
ADMIN_ID = 8032030029
DATA_FILE = "library.json"
# ============================================================

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

library_chunks = []

# تحميل المكتبة من الملف المحلي عند تشغيل البوت
if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            library_chunks = data.get('chunks', [])
            print(f"تم تحميل المكتبة بنجاح! عدد الفقرات المحفوظة: {len(library_chunks)}")
    except Exception as e:
        print(f"خطأ في تحميل ملف المكتبة: {e}")

def normalize(text):
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'[ؤئ]', 'ء', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ال', '', text)
    return text.lower()

def read_pdf_with_pages(file_path):
    pages_data = []
    try:
        reader = PdfReader(file_path)
        for idx, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages_data.append({"page_num": idx + 1, "text": text})
    except Exception as e:
        print(f"خطأ قراءة الـ PDF: {e}")
    return pages_data

def chunk_pages_data(pages_data, book_name, chunk_size=800, overlap=150):
    chunks = []
    for page in pages_data:
        p_num = page["page_num"]
        text = page["text"]
        start = 0
        while start < len(text):
            end = start + chunk_size
            c_text = text[start:end].strip()
            if len(c_text) > 30:
                chunks.append({
                    "book": book_name,
                    "page": p_num,
                    "text": c_text
                })
            start += (chunk_size - overlap)
    return chunks

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({'chunks': library_chunks}, f, ensure_ascii=False, indent=2)

def search_in_books(question, top_k=10):
    q_words = [w for w in re.findall(r'\w+', normalize(question)) if len(w) > 1]
    scores = []
    
    for item in library_chunks:
        chunk_normalized = normalize(item['text'])
        score = sum(1 for word in q_words if word in chunk_normalized)
        if score > 0:
            scores.append((score, item))
            
    scores.sort(key=lambda x: x[0], reverse=True)
    best_chunks = [item for score, item in scores[:top_k]]
    
    return best_chunks

@bot.message_handler(commands=['start'])
def start(msg):
    total_books = len(set(c['book'] for c in library_chunks))
    bot.send_message(
        msg.chat.id, 
        f"🤍 أهلاً بك في بوت المكتبة الشاملة\n\n📚 الكتب المرفوعة حالياً: {total_books}\n📄 إجمالي الفقرات: {len(library_chunks)}\n\nأرسل سؤالك وسيتم البحث في جميع الكتب واستخراج النص المباشر ورقم الصفحة."
    )

@bot.message_handler(content_types=['document'])
def handle_file(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    temp_path = f"temp_{msg.file_unique_id}.pdf"
    book_name = msg.document.file_name.replace(".pdf", "").replace(".PDF", "")
    
    try:
        bot.send_message(msg.chat.id, f"⏳ جاري معالجة كتاب: [{book_name}] وتفكيك صفحاته...")
        
        file_info = bot.get_file(msg.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(temp_path, 'wb') as f:
            f.write(downloaded_file)
            
        pages_data = read_pdf_with_pages(temp_path)
        
        if pages_data:
            new_chunks = chunk_pages_data(pages_data, book_name)
            library_chunks.extend(new_chunks)
            save_data()
            
            total_books = len(set(c['book'] for c in library_chunks))
            bot.send_message(
                msg.chat.id, 
                f"✅ تم إضافة الكتاب بنجاح إلى المكتبة الدائمة!\n\n📖 الكتاب: {book_name}\n📄 الفقرات المضافة: {len(new_chunks)}\n📚 إجمالي الكتب بالمكتبة: {total_books}"
            )
        else:
            bot.send_message(msg.chat.id, "❌ الملف لا يحتوي على نص قابل للقراءة (قد يكون مصوراً Scan).")
            
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء معالجة الملف: {e}")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

@bot.message_handler(func=lambda m: True)
def reply(msg):
    if len(library_chunks) == 0:
        bot.reply_to(msg, "⚠️ المكتبة فارغة حالياً. يرجى رفع ملفات PDF أولاً.")
        return
    
    bot.send_message(msg.chat.id, "⏳ جاري البحث في كافة الكتب والمستندات...")
    
    relevant_chunks = search_in_books(msg.text, top_k=10)
    
    if not relevant_chunks:
        bot.send_message(msg.chat.id, "لم أجد معلومات مرتبطة بسؤالك في الكتب المرفوعة.")
        return

    formatted_context = []
    for c in relevant_chunks:
        formatted_context.append(f"المصدر: كتاب [{c['book']}] (صفحة: {c['page']})\nالنص:\n{c['text']}")
        
    context_text = "\n\n---\n\n".join(formatted_context)
    
    prompt = f"""
أنت مساعد بحثي دقيق جداً. وظيفتك هي استخراج النص من الفقرات المرفقة أدناه فقط.

التعليمات الصارمة:
1. أجب عن السؤال بالاعتماد الحصري على "المحتوى المرفق من الكتب".
2. انقُل النص المطلوب (الأوراد، الأذكار، الفقرات) بشكل *حرفي تماماً* دون أي شرح أو تلخيص أو تحوير.
3. اذكر اسم الكتاب ورقم الصفحة بوضوح بجانب كل نص تنقله.
4. أجب بنفس لغة السؤال.

المحتوى المرفق من الكتب:
{context_text}

سؤال المستخدم:
{msg.text}
"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = ai_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )
            bot.send_message(msg.chat.id, response.text)
            break
        except APIError as e:
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                bot.send_message(msg.chat.id, "❌ السيرفر مشغول حالياً، يرجى إعادة إرسال السؤال بعد قليل.")
                break
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء إعداد الإجابة: {e}")
            break

print("البوت تعمل قاعدته الدائمة بنجاح...")
while True:
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        time.sleep(5)