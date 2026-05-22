import sqlite3
from datetime import datetime, timedelta
import telebot
import os
import re
import threading
import time

TOKEN = os.environ.get("TELEGRAM_TOKEN")

bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("deadlines.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        task_text TEXT,
        deadline_date TEXT
    )
""")
conn.commit()

# ========== КОМАНДА /START ==========
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 
        "✅ Бот-дедлайн трекер работает!\n\n"
        "📌 КОМАНДЫ:\n"
        "/add задача ГГГГ-ММ-ДД — добавить дедлайн\n"
        "/list — показать все задачи\n"
        "/today — задачи на сегодня\n"
        "/tomorrow — задачи на завтра\n"
        "/delete номер — удалить задачу (номер из /list)\n\n"
        "Примеры:\n"
        "/add Сдать лабу 2026-05-25\n"
        "/delete 3")

# ========== КОМАНДА /ADD ==========
@bot.message_handler(commands=['add'])
def add_task(message):
    try:
        text = message.text[4:].strip()
        
        match = re.search(r'(\d{4}-\d{2}-\d{2})$', text)
        if not match:
            bot.reply_to(message, "❌ Не найден дедлайн! Формат: /add Название 2026-05-25")
            return
        
        deadline_str = match.group(1)
        task_text = text[:match.start()].strip()
        
        if not task_text:
            bot.reply_to(message, "❌ Укажите название задачи")
            return
        
        datetime.strptime(deadline_str, "%Y-%m-%d")
        
        cursor.execute(
            "INSERT INTO tasks (user_id, task_text, deadline_date) VALUES (?, ?, ?)",
            (message.chat.id, task_text, deadline_str)
        )
        conn.commit()
        
        bot.reply_to(message, f"✅ Задача «{task_text}» сохранена! Дедлайн: {deadline_str}")
    
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка! Используйте: /add Название задачи 2026-05-22")

# ========== КОМАНДА /LIST (с нумерацией для каждого пользователя) ==========
@bot.message_handler(commands=['list'])
def list_tasks(message):
    cursor.execute(
        "SELECT id, task_text, deadline_date FROM tasks WHERE user_id = ? ORDER BY deadline_date",
        (message.chat.id,)
    )
    tasks = cursor.fetchall()
    
    if not tasks:
        bot.reply_to(message, "📭 У вас пока нет задач")
        return
    
    answer = "📋 ВСЕ ДЕДЛАЙНЫ:\n\n"
    # Нумерация для пользователя (1, 2, 3...), а не глобальный id
    for idx, (db_id, task, date) in enumerate(tasks, start=1):
        answer += f"{idx}. {task} — {date}\n"
    
    # Сохраняем соответствие "номер_для_пользователя" -> "реальный_id_в_бд"
    # Временно сохраняем в памяти, но лучше при удалении искать по дате и тексту
    # В этом коде при удалении будем искать по позиции
    
    bot.reply_to(message, answer)

# ========== КОМАНДА /TODAY ==========
@bot.message_handler(commands=['today'])
def today_tasks(message):
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute(
        "SELECT id, task_text FROM tasks WHERE user_id = ? AND deadline_date = ?",
        (message.chat.id, today_str)
    )
    tasks = cursor.fetchall()
    
    if not tasks:
        bot.reply_to(message, f"📭 На сегодня ({today_str}) задач нет. Отдыхайте! 🎉")
        return
    
    answer = f"⏰ ЗАДАЧИ НА СЕГОДНЯ ({today_str}):\n\n"
    for idx, (db_id, task) in enumerate(tasks, start=1):
        answer += f"{idx}. {task} — СЕГОДНЯ❗\n"
    
    bot.reply_to(message, answer)

# ========== КОМАНДА /TOMORROW ==========
@bot.message_handler(commands=['tomorrow'])
def tomorrow_tasks(message):
    tomorrow_str = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    cursor.execute(
        "SELECT id, task_text FROM tasks WHERE user_id = ? AND deadline_date = ?",
        (message.chat.id, tomorrow_str)
    )
    tasks = cursor.fetchall()
    
    if not tasks:
        bot.reply_to(message, f"📭 На завтра ({tomorrow_str}) задач нет")
        return
    
    answer = f"⏰ ЗАДАЧИ НА ЗАВТРА ({tomorrow_str}):\n\n"
    for idx, (db_id, task) in enumerate(tasks, start=1):
        answer += f"{idx}. {task}\n"
    answer += f"\n⚠️ Не забудьте сделать до завтра!"
    
    bot.reply_to(message, answer)

# ========== КОМАНДА /DELETE (по номеру из /list, с правильным удалением) ==========
@bot.message_handler(commands=['delete'])
def delete_task(message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ Формат: /delete номер_задачи\n\nНомер можно посмотреть командой /list")
            return
        
        user_number = int(parts[1])  # номер, который видит пользователь (1, 2, 3...)
        
        # Получаем все задачи пользователя
        cursor.execute(
            "SELECT id, task_text, deadline_date FROM tasks WHERE user_id = ? ORDER BY deadline_date",
            (message.chat.id,)
        )
        tasks = cursor.fetchall()
        
        if not tasks:
            bot.reply_to(message, "📭 У вас нет задач для удаления")
            return
        
        # Проверяем, что номер существует
        if user_number < 1 or user_number > len(tasks):
            bot.reply_to(message, f"❌ Задачи с номером {user_number} не существует. Всего задач: {len(tasks)}")
            return
        
        # Получаем реальный id задачи из базы данных
        db_id = tasks[user_number - 1][0]  # user_number начинается с 1, а список с 0
        task_text = tasks[user_number - 1][1]
        
        # Удаляем по реальному id
        cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (db_id, message.chat.id))
        conn.commit()
        
        bot.reply_to(message, f"✅ Задача «{task_text}» удалена!")
    
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
            
            # Проверяем задачи на завтра
            cursor.execute(
                "SELECT user_id, task_text FROM tasks WHERE deadline_date = ?",
                (tomorrow.strftime("%Y-%m-%d"),)
            )
            tasks_tomorrow = cursor.fetchall()
            
            for user_id, task_text in tasks_tomorrow:
                try:
                    bot.send_message(user_id, f"🔔 НАПОМИНАНИЕ!\nЗавтра дедлайн: «{task_text}»\n\nУспейте сделать!")
                except:
                    pass
            
            # Проверяем задачи на сегодня
            cursor.execute(
                "SELECT user_id, task_text FROM tasks WHERE deadline_date = ?",
                (today.strftime("%Y-%m-%d"),)
            )
            tasks_today = cursor.fetchall()
            
            for user_id, task_text in tasks_today:
                try:
                    bot.send_message(user_id, f"⚠️ СРОЧНОЕ НАПОМИНАНИЕ!\nСегодня последний день: «{task_text}»\n\nНе откладывайте!")
                except:
                    pass
            
            time.sleep(21600)  # 6 часов
            
        except Exception as e:
            print(f"Ошибка в фоновой проверке: {e}")
            time.sleep(60)

# ========== ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД ==========
@bot.message_handler(func=lambda message: True)
def unknown(message):
    bot.reply_to(message, "❓ Неизвестная команда. Напишите /start")

# ========== ЗАПУСК ==========
print("🚀 Бот запущен!")
print("Доступные команды: /start, /add, /list, /today, /tomorrow, /delete")
print("🔔 Фоновая проверка дедлайнов запущена (каждые 6 часов)")

background_thread = threading.Thread(target=check_deadlines_background, daemon=True)
background_thread.start()


