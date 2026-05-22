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
        "/delete номер — удалить задачу\n\n"
        "🔔 Автоматические напоминания приходят:\n"
        "• в 09:00 — за день до дедлайна\n"
        "• в 09:00 — в день дедлайна\n\n"
        "Пример: /add Сдать лабу 2026-05-25")

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

# ========== КОМАНДА /LIST ==========
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
    for task_id, task, date in tasks:
        answer += f"{task_id}. {task} — {date}\n"
    
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
    for task_id, task in tasks:
        answer += f"{task_id}. {task} — СЕГОДНЯ❗\n"
    
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
    for task_id, task in tasks:
        answer += f"{task_id}. {task}\n"
    answer += f"\n⚠️ Не забудьте сделать до завтра!"
    
    bot.reply_to(message, answer)

# ========== КОМАНДА /DELETE ==========
@bot.message_handler(commands=['delete'])
def delete_task(message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ Формат: /delete номер_задачи\n\nНомер можно посмотреть командой /list")
            return
        
        task_id = int(parts[1])
        
        cursor.execute(
            "SELECT task_text FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, message.chat.id)
        )
        task = cursor.fetchone()
        
        if not task:
            bot.reply_to(message, f"❌ Задача с номером {task_id} не найдена")
            return
        
        cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, message.chat.id))
        conn.commit()
        
        bot.reply_to(message, f"✅ Задача «{task[0]}» удалена!")
    
    except ValueError:
        bot.reply_to(message, "❌ Номер должен быть числом. Пример: /delete 3")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при удалении")

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
            
            # Проверяем каждые 6 часов (21600 секунд)
            # Для демонстрации можно поставить 60 секунд, но для бота лучше 21600
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

# Запускаем фоновую проверку в отдельном потоке
background_thread = threading.Thread(target=check_deadlines_background, daemon=True)
background_thread.start()

bot.infinity_polling()
