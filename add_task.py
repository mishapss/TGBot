import psycopg2
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from states import user_states, STATE_WAITING_TITLE, STATE_WAITING_DESCRIPTION, STATES, STATE_WAITING_ASSIGNEE, STATE_WAITING_DUE_DATE
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

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["Посмотреть задания"], ["Добавить задание"], ["Удалить задание"]],
        resize_keyboard=True
    )

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Процесс добавления задания."""
    user_id = update.effective_user.id
    user_states[user_id] = "ADD_TASK_TITLE"
    context.user_data.clear()
    await update.message.reply_text("Введите название задания:")
    print(datetime.now())

# Обработка текстовых сообщений
async def handle_task_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text.strip()

    #print(f"\n=== DEBUG: Получено сообщение '{user_input}' от {user_id} ===")
    #print(f"Текущее состояние: {user_states.get(user_id)}")
    #print(f"User_data: {context.user_data}")
    """Обработка последовательного ввода данных."""
    
    if user_id not in user_states:
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

        if user_input.lower() == 'нет':
            context.user_data["due_date"] = None
            context.user_data["reminder"] = "нет"
        
        # Пропускаем состояние ADD_TASK_REMINDER_TYPE и сразу переходим к сохранению
            user_states[user_id] = "ADD_TASK_NEXT_STATE_AFTER_TASK_CREATION"
        
            return await handle_task_creation(update, context)
    
        try:
            due_date = datetime.strptime(user_input, "%d.%m.%Y").date()
            context.user_data["due_date"] = due_date

        # Запрашиваем напоминание только если дедлайн установлен
            user_states[user_id] = "ADD_TASK_REMINDER_TYPE"
            #print(f"DEBUG: Установлено состояние ADD_TASK_REMINDER_TYPE для {user_id}")
    
            reply_keyboard = [["За 2 дня до", "За 1 день до", "Без напоминаний", "В этот день в 9:00 утра"]]
    
            await update.message.reply_text(
            "Выберите напоминание:",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True
            )
            )
            return
        except ValueError:
            await update.message.reply_text(
            "⛔ Неверный формат. Введите:\n"
            "• 25.12.2023 (дата)\n"
            "• 'нет' (без дедлайна)"
            )
        return

    elif current_state == "ADD_TASK_REMINDER_TYPE":
        #print(f"DEBUG: Получено напоминание: {user_input}")
        context.user_data["reminder"] = user_input

        # Переходим к сохранению задачи
        user_states[user_id] = "ADD_TASK_NEXT_STATE_AFTER_TASK_CREATION"
    
    # Вызываем обработчик сохранения задачи
        return await handle_task_creation(update, context)

async def handle_task_creation(update, context):
    """Функция для сохранения задачи в БД"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    '''INSERT INTO tasks 
                    (title, description, assignee, status, due_date, created_at, category, notified, reminder_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s)
                    RETURNING task_id''',
                    (
                    context.user_data["title"],
                    context.user_data["description"],
                    context.user_data["assignee"],
                    "Новая",
                    context.user_data["due_date"],
                    create_datemultirange(datetime.now().date()),
                    "Общее",
                    context.user_data.get("reminder")
                    )
                )
                task_id = cursor.fetchone()[0]
                conn.commit()

        due_date_str = "нет"
        if context.user_data["due_date"]:
            due_date_str = context.user_data["due_date"].strftime("%d.%m.%Y")
            
        message = (
                f"✅ <b>Задание добавлено!</b>\n\n"
                f"📌 {context.user_data['title']}\n"
                f"📝 {context.user_data['description']}\n"
                f"👤 {context.user_data['assignee']}\n"
                f"⏳ {due_date_str}\n"
                f"🔔 {context.user_data.get('reminder', 'нет')}"
            )
        
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=get_main_keyboard())

        # Отправляем уведомление
        await notify_assignee(
            bot_token=context.bot.token,
            assignee_name=context.user_data["assignee"],
            task_title=context.user_data["title"],
            task_description=context.user_data["description"],
            due_date=context.user_data["due_date"],
            reminder=context.user_data.get("reminder")
        )

        # Очищаем состояние
        user_id = update.effective_user.id
        if user_id in user_states:
            del user_states[user_id]
        context.user_data.clear()

    except Exception as e:
        await update.message.reply_text("Ошибка при сохранении задания",
        reply_markup=get_main_keyboard())
        print(f"ошибка {e}")
        
