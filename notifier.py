from telegram import Bot
import psycopg2, asyncio
from datetime import datetime, timedelta
from typing import Union
from datetime import datetime, date

DB_CONFIG = {
    "dbname": "",
    "user": "",
    "password": "",
    "host": "",
    "port": 
}


async def notify_assignee(bot_token: str, assignee_name: str, 
                        task_title: str, task_description: str,
                        due_date: Union[datetime, date, None] = None, has_time: bool = False):
    bot = Bot(token=bot_token)

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'SELECT username FROM assignee_mapping WHERE name = %s',
                    (assignee_name,)
                )
                result = cursor.fetchone()
                
                if not result:
                    print(f"⚠️ Для '{assignee_name}' нет юзернейма!")
                    return
                          
                username = result[0]  # "mishapss"
                
                # 2. Ищем chat_id по юзернейму (из users)
                cursor.execute(
                    'SELECT chat_id FROM users WHERE username = %s',
                    (username,)
                )
                result = cursor.fetchone()
                
                if not result:
                    print(f"⚠️ Нет chat_id для @{username}!")
                    return
                
                chat_id = result[0]

                # Форматируем дату (если due_date не None)
                deadline_text = "не указан"
                if due_date:
                    if has_time and isinstance(due_date, datetime):
                        deadline_text = due_date.strftime("%d.%m.%Y %H:%M")
                    else:
                        deadline_text = due_date.strftime("%d.%m.%Y")
    
                message = (
                    "📌 Вам добавлено новое задание!\n\n"
                    f"🔹 Название: {task_title}\n"
                    f"📝 Описание: {task_description}\n"
                    f"⏳ Дедлайн: {deadline_text}\n"
                )

                await bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"Ошибка уведомления: {e}")


async def start_notifier(bot_token: str):
    """фон для проверки дедлайнов"""
    bot = Bot(token = bot_token)
    while True:
        try:
            await check_deadlines(bot)
        except Exception as e:
            print(f"Ошибка в notifier: {e}")
        await asyncio.sleep(3600)

async def check_deadlines(bot: Bot):
    """проверка дедлайнов"""
    now = datetime.now()
    deadline_threshold = now + timedelta(hours=24)

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT task_id, task.title, task.assignee, users.chat_id
                FROM tasks task
                JOIN users ON task.assignee = user_name
                WHERE task.due_date BETWEEN %s AND %s
                AND task.notified = FALSE    
                ''', (now, deadline_threshold))
            
            for task_id, title, assignee, chat_id in cursor.fetchall():
                try:
                    message = (
                        "⏰ Напоминание!\n"
                        f"Задание: {title}\n"
                        f"Дедлайн: {deadline_threshold.strftime('%d.%m.%Y %H:%M')}\n"
                        "Осталось менее 24 часов!"
                    )
                    await bot.send_message(chat_id=chat_id, text=message)

                    cursor.execute(
                        "UPDATE tasks task SET notified = TRUE WHERE task.id = %s",
                        (task_id,)
                    )
                    conn.commit()
                except Exception as e:
                    print(f"Ошибка отправки уведомления: {e}")