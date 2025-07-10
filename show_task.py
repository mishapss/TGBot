import psycopg2
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from states import user_states
from keyboard import get_main_keyboard

#конфигурация подключения к бд
DB_CONFIG = {
    "dbname": "",
    "user": "",
    "password": "",
    "host": "",
    "port": 
}

async def show_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление пользователя в комнату показа задания. Должен только устанавливать состояние пользователя и показывать клавиатура."""
    user_id = update.effective_user.id
    user_states[user_id] = "SHOW_TASK_ASSIGNEE"

    await update.message.reply_text(
        "Выбери исполнителя:",
        reply_markup=ReplyKeyboardMarkup(
            [["Миша", "Папа", "Мама", "Настя"]],
            one_time_keyboard=True
        )
    )
    
async def handle_show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора исполнителя (без изменений)"""
    user_id = update.effective_user.id
    
    if user_states.get(user_id) != "SHOW_TASK_ASSIGNEE":
        return
    
    assignee = update.message.text.strip()
    context.user_data['current_assignee'] = assignee

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    '''SELECT task_id, title, description, due_date FROM tasks WHERE assignee = %s ORDER BY due_DATE NULLS LAST, created_at''',
                    (assignee,)
                )
                tasks = cursor.fetchall()
        
        if not tasks:
            await update.message.reply_text(f"У {assignee} нет заданий", reply_markup=get_main_keyboard())
            del user_states[user_id] # Очищаем состояние при отсутствии заданий
            return
        
        #формируем компактный список
        tasks_list = []
        for task in tasks:
            task_id, title, description, due_date = task

            #обработка даты
            due_str = "⏳ без срока" if due_date is None else f"до {due_date.strftime('%d.%m.%Y')}"

            #форматируем запись
            tasks_list.append(
                f"🔹 {title}\n"
                f"   {description}\n"
                f"   {due_str}\n"
            )

        await update.message.reply_text(
            f"📋 Задания для {assignee}:\n\n" + 
            "\n".join(tasks_list),
            reply_markup=get_main_keyboard()
        )

        #переводим в состояние выбора задания
        user_states[user_id] = "WAITING_TASK_SELECTION"
        context.user_data["tasks"] = {task[0]: task for task in tasks}# Сохраняем задачи

        return "COMPLETE"

    except Exception as e:
        print(f"Database error: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при загрузке заданий",
        reply_markup=get_main_keyboard()
        )
        if user_id in user_states:
            del user_states[user_id]