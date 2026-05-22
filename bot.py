import sqlite3
from datetime import datetime
import telebot
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

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

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 
        "✅ Бот работает!\n\n"
        "📌 Команды:\n"
        "/add задача ГГГГ-ММ-ДД\n"
        "/list\n\n"
        "Пример: /add Сдать лабу 2026-05-25")

@bot.message_handler(commands=['add'])
def add_task(message):
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(message, "❌ Формат: /add Название задачи 2026-05-25")
            return
        task_text = parts[1]
        deadline_str = parts[2]
        datetime.strptime(deadline_str, "%Y-%m-%d")
        cursor.execute(
            "INSERT INTO tasks (user_id, task_text, deadline_date) VALUES (?, ?, ?)",
            (message.chat.id, task_text, deadline_str)
        )
        conn.commit()
        bot.reply_to(message, f"✅ Задача «{task_text}» сохранена! Дедлайн: {deadline_str}")
    except Exception:
        bot.reply_to(message, "❌ Ошибка! Используйте формат: /add задача 2026-05-22")

@bot.message_handler(commands=['list'])
def list_tasks(message):
    cursor.execute(
        "SELECT task_text, deadline_date FROM tasks WHERE user_id = ? ORDER BY deadline_date",
        (message.chat.id,)
    )
    tasks = cursor.fetchall()
    if not tasks:
        bot.reply_to(message, "📭 У вас пока нет задач")
        return
    answer = "📋 ВАШИ ДЕДЛАЙНЫ:\n\n"
    for task, date in tasks:
        answer += f"• {task} — {date}\n"
    bot.reply_to(message, answer)

# ========== ЭТО ДЛЯ RENDER (имитация веб-сервера) ==========
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_webserver():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# Запускаем веб-сервер в отдельном потоке
threading.Thread(target=run_webserver, daemon=True).start()

# ========== ЗАПУСК БОТА ==========
print("🚀 Бот запущен!")
bot.infinity_polling()
