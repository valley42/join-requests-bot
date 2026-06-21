import telebot
import sqlite3
import logging
from datetime import datetime
import sys

# ===== НАСТРОЙКИ =====
BOT_TOKEN = sys.argv[1]
# ===== ЛОГИРОВАНИЕ =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect("applications.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            group_chat_id INTEGER,
            age INTEGER,
            reason TEXT,
            date TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_survey(user_id, username, first_name, last_name, group_chat_id, age, reason):
    conn = sqlite3.connect("applications.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO surveys (user_id, username, first_name, last_name, group_chat_id, age, reason, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, first_name, last_name, group_chat_id, age, reason, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"Анкета сохранена для {user_id}")

# ===== ХРАНЕНИЕ СОСТОЯНИЙ =====
user_states = {}

# ===== ОБРАБОТЧИК ЗАЯВОК =====
@bot.chat_join_request_handler()
def handle_join_request(chat_join_request):
    user = chat_join_request.from_user
    chat = chat_join_request.chat
    user_id = user.id
    chat_id = chat.id

    if user_id in user_states:
        bot.send_message(user_id, "Вы уже отвечаете на вопросы анкеты. Пожалуйста, завершите её.")
        return

    user_states[user_id] = {
        'state': 'waiting_age',
        'chat_id': chat_id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name
    }

    try:
        bot.send_message(user_id, "📝 Для вступления в группу ответьте на пару вопросов:\n\n1. Сколько тебе лет? (пожалуйста, скажи честно)")
        logger.info(f"Запрошен возраст у {user_id}")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение {user_id}: {e}")
        bot.decline_chat_join_request(chat_id, user_id)
        del user_states[user_id]

# ===== ОБРАБОТКА ЛИЧНЫХ СООБЩЕНИЙ =====
@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_survey(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in user_states:
        bot.reply_to(message, "👋 Привет! Если хотите вступить в группу, подайте заявку через неё.")
        return

    state_data = user_states[user_id]
    state = state_data['state']

    if state == 'waiting_age':
        try:
            age = int(text)
            if age < 1 or age > 120:
                bot.reply_to(message, "Пожалуйста, введите реальный возраст (от 1 до 120).")
                return
        except ValueError:
            bot.reply_to(message, "Пожалуйста, введите возраст числом.")
            return

        # ===== ПРОВЕРКА 12+ =====
        if age < 12:
            chat_id = state_data['chat_id']
            try:
                bot.decline_chat_join_request(chat_id, user_id)
                bot.reply_to(message, "❌ Извините, для вступления в группу нужно быть старше 12 лет.")
                logger.info(f"Заявка отклонена: возраст {age} < 12 у {user_id}")
            except Exception as e:
                logger.error(f"Ошибка при отклонении заявки {user_id}: {e}")
                bot.reply_to(message, "Произошла ошибка. Попробуйте позже.")
            # Удаляем состояние
            del user_states[user_id]
            return

        # Возраст подходит
        state_data['age'] = age
        state_data['state'] = 'waiting_reason'
        bot.reply_to(message, "✅ Спасибо!\n\n2. Зачем ты хочешь попасть в группу? (необязательно, но поможет нам понять тебя)")

    elif state == 'waiting_reason':
        reason = text if text else "Не указано"
        state_data['reason'] = reason

        chat_id = state_data['chat_id']
        try:
            bot.approve_chat_join_request(chat_id, user_id)
            logger.info(f"✅ Заявка одобрена для {user_id}")

            save_survey(
                user_id,
                state_data.get('username'),
                state_data.get('first_name'),
                state_data.get('last_name'),
                chat_id,
                state_data['age'],
                reason
            )

            bot.send_message(user_id, "🎉 Поздравляю! Вы приняты в группу. Добро пожаловать!")

        except Exception as e:
            logger.error(f"Ошибка при одобрении заявки {user_id}: {e}")
            bot.send_message(user_id, "❌ Произошла ошибка. Попробуйте позже.")

        del user_states[user_id]

# ===== ОТМЕНА =====
@bot.message_handler(commands=['cancel'], func=lambda m: m.chat.type == 'private')
def cancel_survey(message):
    user_id = message.from_user.id
    if user_id in user_states:
        chat_id = user_states[user_id]['chat_id']
        try:
            bot.decline_chat_join_request(chat_id, user_id)
            logger.info(f"Заявка отклонена (отмена) для {user_id}")
        except:
            pass
        del user_states[user_id]
        bot.reply_to(message, "❌ Анкета отменена.")
    else:
        bot.reply_to(message, "У вас нет активной анкеты.")

# ===== /START =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Подайте заявку в группу, и я задам пару вопросов.")

# ===== ЗАПУСК =====
if __name__ == "__main__":
    logger.info("Бот запущен, ожидаем заявки...")
    bot.infinity_polling()
