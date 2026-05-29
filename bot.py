import telebot
import os
import re
import threading
import time
from datetime import datetime, timedelta
from supabase import create_client, Client
from flask import Flask

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Данные для подключения к Supabase (берутся из переменных окружения на Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Создаём клиент Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

bot = telebot.TeleBot(TOKEN)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_user_tasks(user_id):
    """Получить все задачи пользователя, отсортированные по дате"""
    response = supabase.table('tasks')\
        .select('id, task_text, deadline_date')\
        .eq('user_id', user_id)\
        .order('deadline_date')\
        .execute()
    return response.data

def add_task_to_db(user_id, task_text, deadline_date):
    """Добавить задачу в базу"""
    response = supabase.table('tasks').insert({
        'user_id': user_id,
        'task_text': task_text,
        'deadline_date': deadline_date
    }).execute()
    return response.data

def delete_task_from_db(task_id, user_id):
    """Удалить задачу из базы (проверяя, что задача принадлежит пользователю)"""
    response = supabase.table('tasks')\
        .delete()\
        .eq('id', task_id)\
        .eq('user_id', user_id)\
        .execute()
    return len(response.data) > 0

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message,
        "✅ Бот-дедлайн трекер работает! Данные хранятся в облаке ☁️\n\n"
        "📌 КОМАНДЫ:\n"
        "/add задача ГГГГ-ММ-ДД — добавить дедлайн\n"
        "/list — показать все задачи\n"
        "/today — задачи на сегодня\n"
        "/tomorrow — задачи на завтра\n"
        "/delete номер — удалить задачу\n\n"
        "✨ Данные не теряются даже после перезапуска сервера!\n\n"
        "Пример: /add Сдать лабу 2026-06-01")

@bot.message_handler(commands=['add'])
def add_task(message):
    try:
        # Берём текст после /add
        text = message.text[4:].strip()
        
        # Ищем дату в формате ГГГГ-ММ-ДД в любом месте
        match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if not match:
            bot.reply_to(message, "❌ Не найден дедлайн! Формат: /add Название 2026-05-25")
            return
        
        deadline_str = match.group(1)
        
        # Всё, что до даты — название задачи
        parts = text.split(deadline_str)
        task_text = parts[0].strip()
        
        if not task_text:
            bot.reply_to(message, "❌ Укажите название задачи")
            return
        
        # Проверяем корректность даты
        datetime.strptime(deadline_str, "%Y-%m-%d")
        
        # Сохраняем в Supabase
        add_task_to_db(message.chat.id, task_text, deadline_str)
        
        bot.reply_to(message, f"✅ Задача «{task_text}» сохранена в облаке! Дедлайн: {deadline_str}")
    
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка! Используйте: /add Название задачи 2026-05-22")

@bot.message_handler(commands=['list'])
def list_tasks(message):
    tasks = get_user_tasks(message.chat.id)
    
    if not tasks:
        bot.reply_to(message, "📭 У вас пока нет задач")
        return
    
    answer = "📋 ВСЕ ДЕДЛАЙНЫ:\n\n"
    for idx, task in enumerate(tasks, start=1):
        answer += f"{idx}. {task['task_text']} — {task['deadline_date']}\n"
    
    bot.reply_to(message, answer)

@bot.message_handler(commands=['today'])
def today_tasks(message):
    today_str = datetime.now().strftime("%Y-%m-%d")
    tasks = get_user_tasks(message.chat.id)
    
    today_tasks_list = [t for t in tasks if t['deadline_date'] == today_str]
    
    if not today_tasks_list:
        bot.reply_to(message, f"📭 На сегодня ({today_str}) задач нет. Отдыхайте! 🎉")
        return
    
    answer = f"⏰ ЗАДАЧИ НА СЕГОДНЯ ({today_str}):\n\n"
    for idx, task in enumerate(today_tasks_list, start=1):
        answer += f"{idx}. {task['task_text']} — СЕГОДНЯ❗\n"
    
    bot.reply_to(message, answer)

@bot.message_handler(commands=['tomorrow'])
def tomorrow_tasks(message):
    tomorrow_str = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    tasks = get_user_tasks(message.chat.id)
    
    tomorrow_tasks_list = [t for t in tasks if t['deadline_date'] == tomorrow_str]
    
    if not tomorrow_tasks_list:
        bot.reply_to(message, f"📭 На завтра ({tomorrow_str}) задач нет")
        return
    
    answer = f"⏰ ЗАДАЧИ НА ЗАВТРА ({tomorrow_str}):\n\n"
    for idx, task in enumerate(tomorrow_tasks_list, start=1):
        answer += f"{idx}. {task['task_text']}\n"
    answer += f"\n⚠️ Не забудьте сделать до завтра!"
    
    bot.reply_to(message, answer)

@bot.message_handler(commands=['delete'])
def delete_task(message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ Формат: /delete номер_задачи\n\nНомер можно посмотреть командой /list")
            return
        
        user_number = int(parts[1])
        tasks = get_user_tasks(message.chat.id)
        
        if not tasks:
            bot.reply_to(message, "📭 У вас нет задач для удаления")
            return
        
        if user_number < 1 or user_number > len(tasks):
            bot.reply_to(message, f"❌ Задачи с номером {user_number} не существует. Всего задач: {len(tasks)}")
            return
        
        # Получаем реальный ID задачи из базы
        task_id = tasks[user_number - 1]['id']
        task_text = tasks[user_number - 1]['task_text']
        
        if delete_task_from_db(task_id, message.chat.id):
            bot.reply_to(message, f"✅ Задача «{task_text}» удалена из облака!")
        else:
            bot.reply_to(message, f"❌ Не удалось удалить задачу")
    
    except ValueError:
        bot.reply_to(message, "❌ Номер должен быть числом. Пример: /delete 3")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при удалении: {str(e)}")

# ========== ФОНОВАЯ ПРОВЕРКА ДЕДЛАЙНОВ ==========
def check_deadlines_background():
    while True:
        try:
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            tomorrow_str = tomorrow.strftime("%Y-%m-%d")
            today_str = today.strftime("%Y-%m-%d")
            
            # Получаем задачи на завтра
            response = supabase.table('tasks')\
                .select('user_id, task_text')\
                .eq('deadline_date', tomorrow_str)\
                .execute()
            
            notified_users = set()
            for task in response.data:
                user_id = task['user_id']
                if user_id not in notified_users:
                    try:
                        bot.send_message(user_id, f"🔔 НАПОМИНАНИЕ!\nЗавтра дедлайн: «{task['task_text']}»")
                        notified_users.add(user_id)
                    except:
                        pass
            
            # Получаем задачи на сегодня
            response = supabase.table('tasks')\
                .select('user_id, task_text')\
                .eq('deadline_date', today_str)\
                .execute()
            
            notified_users = set()
            for task in response.data:
                user_id = task['user_id']
                if user_id not in notified_users:
                    try:
                        bot.send_message(user_id, f"⚠️ СРОЧНО!\nСегодня последний день: «{task['task_text']}»")
                        notified_users.add(user_id)
                    except:
                        pass
            
            time.sleep(21600)  # 6 часов
            
        except Exception as e:
            print(f"Ошибка в фоновой проверке: {e}")
            time.sleep(60)

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
web_app = Flask(__name__)

@web_app.route('/')
@web_app.route('/health')
def health_check():
    return "Bot is running!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# ========== ЗАПУСК С АВТОВОССТАНОВЛЕНИЕМ ==========
print("🚀 Бот запущен с Supabase!")
print("Доступные команды: /start, /add, /list, /today, /tomorrow, /delete")
print("☁️ Данные хранятся в Supabase, ничего не потеряется!")

# Запускаем веб-сервер в отдельном потоке (для Render)
web_thread = threading.Thread(target=run_web_server, daemon=True)
web_thread.start()
print(f"🌐 Веб-сервер для Render запущен на порту {os.environ.get('PORT', 10000)}")

# Запускаем фоновую проверку дедлайнов
background_thread = threading.Thread(target=check_deadlines_background, daemon=True)
background_thread.start()

# Запускаем бота с автовосстановлением при ошибке 409
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        if "409" in str(e):
            print("⚠️ Ошибка 409 (конфликт), перезапускаем через 10 секунд...")
            time.sleep(10)
        else:
            print(f"❌ Другая ошибка: {e}")
            time.sleep(5)
