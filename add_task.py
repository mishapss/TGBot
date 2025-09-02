import psycopg2
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from states import user_states
from notifier import notify_assignee 
import dateparser
from datetime import datetime, timedelta
import re
from dateutil.relativedelta import relativedelta

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


async def parse_date(date_str):
    if not date_str or date_str.lower().strip() == 'нет':
        return None
    
    lower_input = date_str.lower().strip()

    if lower_input == "сегодня":
        return datetime.now().date()
    if lower_input == "завтра":
        return (datetime.now() + timedelta(days=1)).date()
    if lower_input == "послезавтра":
        return (datetime.now() + timedelta(days=2)).date()

    m = re.match(r'^через\s+(?:(\d+)\s+)?([а-яё]+)', lower_input)
    if m:
        n = int(m.group(1)) if m.group(1) else 1
        unit = m.group(2)

        day_forms   = {"день", "дня", "дней", "сутки", "суток"}
        week_forms  = {"неделя", "неделю", "недели", "недель"}
        month_forms = {"месяц", "месяца", "месяцев"}
        year_forms  = {"год", "года", "лет"}

        base = datetime.now()
        if unit in day_forms:
            return (base + timedelta(days=n)).date()
        if unit in week_forms:
            return (base + timedelta(weeks=n)).date()
        if unit in month_forms:
            return (base + relativedelta(months=n)).date()
        if unit in year_forms:
            return (base + relativedelta(years=n)).date()

    weekdays_numbers = {
        'понедельник': 0,
        'вторник': 1,
        'среда': 2,  'среду': 2,
        'четверг': 3,
        'пятница': 4, 'пятницу': 4,
        'суббота': 5, 'субботу': 5,
        'воскресенье': 6
    }
    for name, num in weekdays_numbers.items():
        if name in lower_input:
            return get_next_weekday(num).date()

    try:
        parsed = dateparser.parse(
            date_str,
            languages=['ru'],
            settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now(),
                'DATE_ORDER': 'DMY'
            }
        )
        return parsed.date() if parsed else None
    except Exception as e:
        print(f"Ошибка парсинга даты '{date_str}': {e}")
        return None

def get_next_weekday(weekday: int):
    today = datetime.now().weekday()
    days_ahead = weekday - today
    if days_ahead <= 0:
        days_ahead += 7
    return datetime.now() + timedelta(days=days_ahead)   

async def handle_task_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text.strip()
    
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
            "⏳ Введите дедлайн в формате ДД.ММ.ГГГГ, через 2 дня, через неделю и тд.\n"
            "Или отправьте 'нет', если дедлайн не нужен."
        )
    
    elif current_state == "ADD_TASK_DUE_DATE":
        if user_input.lower() != 'нет':
            due_date = await parse_date(user_input) 

            if due_date is None:
                await update.message.reply_text("Не удалось распознать дату")
                return

            context.user_data["due_date"] = due_date 
            user_states[user_id] = "ADD_TASK_REMINDER_TYPE"

            reply_keyboard = [["За 2 дня до", "За 1 день до", "Без напоминаний", "В этот день в 9:00 утра"]]

            await update.message.reply_text(
                "Выберите напоминание",
                reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True
                )
            )

        if user_input.lower() == 'нет':
            context.user_data["due_date"] = None
            context.user_data["reminder"] = "нет"
            return await handle_task_creation(update, context) 

    elif current_state == "ADD_TASK_REMINDER_TYPE":
        context.user_data["reminder"] = user_input

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
        if context.user_data.get("due_date"):
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

        await notify_assignee(
            bot_token=context.bot.token,
            assignee_name=context.user_data["assignee"],
            task_title=context.user_data["title"],
            task_description=context.user_data["description"],
            due_date=context.user_data["due_date"],
            reminder=context.user_data.get("reminder")
        )

        user_id = update.effective_user.id
        if user_id in user_states:
            del user_states[user_id]
        context.user_data.clear()

    except Exception as e:
        await update.message.reply_text("Ошибка при сохранении задания",
        reply_markup=get_main_keyboard())
        print(f"ошибка {e}")
