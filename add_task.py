import psycopg2
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from states import user_states
from datetime import datetime, timedelta
from notifier import notify_assignee


# Конфигурация подключения к базе данных
DB_CONFIG = {
    "dbname": "",
    "user": "",
    "password": "",
    "host": "",
    "port": 
}

def create_datemultirange(date):
    upper_bound = date + timedelta(days=1)
    return f"{{[{date.isoformat()}, {upper_bound.isoformat()})}}"

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Процесс добавления задания."""
    user_id = update.effective_user.id
    user_states[user_id] = "ADD_TASK_TITLE" # Устанавливаем первое состояние
    context.user_data.clear() #очищаем предыдущие данные

    await update.message.reply_text("Введите название задания:")

# Обработка текстовых сообщений
async def handle_task_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка последовательного ввода данных."""
    user_id = update.effective_user.id
    user_input = update.message.text.strip()

    # Проверяем состояние пользователя
    if user_id not in user_states or not user_states[user_id].startswith("ADD_TASK_"):
        return
    
    current_state = user_states[user_id]
        
    if current_state == "ADD_TASK_TITLE":
        context.user_data["title"] = user_input
        user_states[user_id] = "ADD_TASK_DESCRIPTION"
        await update.message.reply_text("Теперь введите описание задания:")
    
    elif current_state == "ADD_TASK_DESCRIPTION":
        context.user_data['description'] = user_input
        user_states[user_id] = "ADD_TASK_ASSIGNEE"

        reply_keyboard = [["Миша", "Папа", "Мама", "Настя"]]
        await update.message.reply_text(
            "выберите исполнителя:",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True
            )
        )

    elif current_state == "ADD_TASK_ASSIGNEE":
        if user_input not in ["Миша", "Папа", "Мама", "Настя"]:
            await update.message.reply_text("❌ Выберите исполнителя из списка")
            return
        
        context.user_data["assignee"] = user_input
        user_states[user_id] = "ADD_TASK_DUE_DATE"
        await update.message.reply_text(
            "⏳ Введите дедлайн в формате ДД.ММ.ГГГГ\n"
            "Или отправьте 'нет', если дедлайн не нужен"
        )
    
    elif current_state == "ADD_TASK_DUE_DATE":
        due_date = None
        has_time = False

        
        if user_input.lower() != 'нет':
            try:
                # Парсим дату (с временем или без)
                if ' ' in user_input:
                    due_date = datetime.strptime(user_input, "%d.%m.%Y %H:%M")
                    context.user_data["has_time"] = True
                else:
                    due_date = datetime.strptime(user_input, "%d.%m.%Y").date()
                    context.user_data["has_time"] = False
            
            except ValueError:
                await update.message.reply_text(
                    "⛔ Неверный формат. Введите:\n"
                    "• 25.12.2023 (дата)\n"
                    "• 25.12.2023 14:00 (дата и время)\n"
                    "• 'нет' (без дедлайна)"
                )
                return
        
        context.user_data["due_date"] = due_date
        context.user_data["has_time"] = has_time
             
            #сохраняем в бд
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        '''INSERT INTO tasks 
                        (title, description, assignee, status, due_date, created_at, category, notified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE)
                        RETURNING task_id''',
                        (
                        context.user_data["title"],
                        context.user_data["description"],
                        context.user_data["assignee"],
                        "Новая",
                        context.user_data["due_date"],
                        create_datemultirange(datetime.now().date()),
                        "Общее"
                        )
                    )
                    task_id = cursor.fetchone()[0]
                    conn.commit()


            due_date_value = context.user_data["due_date"]
            if due_date_value:
                if context.user_data["has_time"]:
                    due_date_str = due_date_value.strftime("%d.%m.%Y %H:%M")
                else:
                    due_date_str = due_date_value.strftime("%d.%m.%Y")
            else:
                due_date_str = "нет"
                
            message = (
                    f"✅ <b>Задание добавлено!</b>\n\n"
                    f"📌 {context.user_data['title']}\n"
                    f"📝 {context.user_data['description']}\n"
                    f"👤 {context.user_data['assignee']}\n"
                    f"⏳ {due_date_str}"
                )
            
            await update.message.reply_text(message, parse_mode='HTML')

        
            # Отправляем уведомление
            await notify_assignee(
                bot_token=context.bot.token,
                assignee_name=context.user_data["assignee"],
                task_title=context.user_data["title"],
                task_description=context.user_data["description"],
                due_date=context.user_data["due_date"],
                has_time=context.user_data["has_time"]
            )

            return "COMPLETE"

        except Exception as e:
            await update.message.reply_text("Ошибка при сохранении задания")
            print(f"ошибка {e}")
        finally:
            #очищаем состояние
            if user_id in user_states:
                del user_states[user_id]
            context.user_data.clear()
        
        
