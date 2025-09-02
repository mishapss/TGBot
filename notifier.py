from telegram import Bot
import psycopg2, asyncio
from datetime import datetime, timedelta
from typing import Union
from datetime import datetime, date

DB_CONFIG = {
    "dbname": "db1",
    "user": "postgres",
    "password": "PGS8!32_admin",
    "host": "localhost",
    "port": 5432
}

async def notify_assignee(bot_token: str, 
                          assignee_name: str,
                          task_title: str,
                          task_description: str,
                          reminder: str,
                          due_date: Union[datetime, date, None] = None,
                          ):
    bot = Bot(token=bot_token)

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'SELECT username FROM assignee_mapping WHERE name = %s',
                    (assignee_name,)
                )
                if not (username := cursor.fetchone()):
                    print(f"⚠️ Для '{assignee_name}' нет юзернейма!")
                    return
                
                cursor.execute('SELECT chat_id FROM users WHERE username = %s', (username[0],))
                if not (chat_id := cursor.fetchone()):
                    print(f"⚠️ Нет chat_id для @{username[0]}!")
                    return

                deadline_text = due_date.strftime("%d.%m.%Y") if due_date else "не указан"
    
                message = (
                    "📌 Вам добавлено новое задание!\n\n"
                    f"🔹 Название: {task_title}\n"
                    f"📝 Описание: {task_description}\n"
                    f"⏳ Дедлайн: {deadline_text}\n"
                    f"🔔 Напоминание: {reminder}\n"
                )

                await bot.send_message(chat_id=chat_id[0], text=message)
    except Exception as e:
        print(f"Ошибка уведомления: {e}")

async def send_notification(bot, chat_id, task_title, when):
    """Отправка уведомления"""
    try:
        message = (
            f"⏰ Напоминание!\n"
            f"Задание: {task_title}\n"
            f"Срок: {when}"
        )
        await bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"Ошибка отправки: {e}")


async def check_deadlines(bot: Bot):
    now = datetime.now()
    current_time = f"{now.hour}:{now.minute}"
    today = now.date()

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT 
                    t.task_id, 
                    t.title, 
                    t.assignee, 
                    u.chat_id, 
                    t.reminder_type,
                    t.due_date
                FROM tasks t
                JOIN assignee_mapping am ON t.assignee = am.name
                JOIN users u ON am.username = u.username
                WHERE t.due_date = %s
                AND t.notified_today = FALSE
            ''', (today,))
            
            tasks = cursor.fetchall()
            
            for task in tasks:
                task_id, title, assignee, chat_id, reminder_type, due_date = task
                               
                if not chat_id:
                    print(f"⚠️ Нет chat_id для {assignee}")
                    continue
                
                if reminder_type.startswith("В этот день в"):
                    try:
                        db_time = reminder_type.split("в ")[1].split()[0]
                        if db_time == current_time:
                            await send_notification(bot, chat_id, title, "сегодня")
                            cursor.execute(
                                "UPDATE tasks SET notified_today = TRUE WHERE task_id = %s",
                                (task_id,)
                            )
                            conn.commit()
                    except Exception as e:
                        print("ошибка обработки reminder_type")
                        
            if current_time == "09:00":
                one_day_start = today + timedelta(days=1)

                cursor.execute('''
                    SELECT
                        t.task_id,
                        t.title,
                        t.assignee, 
                        u.chat_id
                    FROM tasks t
                    JOIN assignee_mapping am ON t.assignee = am.name
                    JOIN users u ON am.username = u.username
                    WHERE t.due_date = %s
                    AND t.notified_1_day = FALSE
                    AND t.reminder_type = 'За 1 день до'
                ''', (one_day_start,)
                )
                        
                tasks_1_day = cursor.fetchall()

                for task in tasks_1_day:
                    task_id, title, assignee, chat_id = task
                    await send_notification(bot, chat_id, title, "завтра")
                    cursor.execute(
                        "UPDATE tasks SET notified_1_day = TRUE WHERE task_id = %s",
                        (task_id,)
                    )
                    conn.commit()
                    
            if current_time == "09:00":
                two_days_start = today + timedelta(days=2)

                cursor.execute('''
                    SELECT
                        t.task_id,
                        t.title,
                        t.assignee, 
                        u.chat_id
                    FROM tasks t
                    JOIN assignee_mapping am ON t.assignee = am.name
                    JOIN users u ON am.username = u.username
                    WHERE t.due_date = %s
                    AND t.notified_2_day = FALSE
                    AND t.reminder_type = 'За 2 дня до'
                    ''', (two_days_start,)
                )
                        
                tasks_2_days = cursor.fetchall()

                for task in tasks_2_days:
                    task_id, title, assignee, chat_id = task
                    await send_notification(bot, chat_id, title, "через 2 дня")
                    cursor.execute(
                        "UPDATE tasks SET notified_2_day = TRUE WHERE task_id = %s",
                        (task_id,)
                    )
                    conn.commit()

async def start_notifier(bot_token: str):
    
    bot = Bot(token = bot_token)
    while True:
        try:
           await check_deadlines(bot)
           await asyncio.sleep(3600)  
        except Exception as e:
            print(f"Ошибка в notifier: {e}")
            await asyncio.sleep(3600)