from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from states import user_states
from delete_task import delete_task_command, delete_task
from add_task import handle_task_room  # Импортируем напрямую обработчик
from show_task import show_task_command, handle_show_tasks#, handle_task_selection
import asyncio, psycopg2
from notifier import start_notifier

DB_CONFIG = {
    "dbname": "",
    "user": "",
    "password": "",
    "host": "",
    "port": 
}
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """получаем chat_id"""
    user = update.effective_user
    chat_id = user.id
    user_name = user.first_name

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO users (user_name, chat_id) VALUES (%s, %s)',
                    (user_name, chat_id)
                )
                conn.commit()

        await update.message.reply_text(
            f"Ваш chat_id: {chat_id}\n"
            f"Имя: {user_name}\n"
            "Данные сохранены для уведомлений!"
        )
    except Exception as e:
        print(f"Ошибка сохранения chat_id: {e}")
        await update.message.reply_text(f"Ваш chat_id: {chat_id} (не сохранен в базу данных)")



def get_main_keyboard():
    """возвращает клаву"""
    return ReplyKeyboardMarkup(
        [["Посмотреть задания"], ["Добавить задание"], ["Удалить задание"]],
    resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Посмотреть задания"],
        ["Добавить задание"], 
        ["Удалить задание"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я бот для управления задачами. Пропиши сначала команду /register. В следующем сообщении напиши /set_username Имя (вместо 'Имя' напиши 'Миша', 'Папа', 'Мама', 'Настя'). После с помощью клавиатуры выбери действие и следуй инструкциям.",
        reply_markup=get_main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_id = update.effective_user.id

    if user_input == "Добавить задание":
        # Очищаем предыдущее состояние
        if user_id in user_states:
            del user_states[user_id]
        context.user_data.clear()
        
        # Устанавливаем начальное состояние добавления задачи
        user_states[user_id] = "ADD_TASK_TITLE"
        await update.message.reply_text("Введите название задания:")
        
    elif user_input == "Посмотреть задания":
        await show_task_command(update, context)
        
    elif user_input == "Удалить задание":
        await delete_task_command(update, context)
        
    else:
        await handle_unknwon_command(update, context)

async def handle_unknwon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных команд"""
    user_id = update.effective_user.id

    #активное состояние проверка
    if user_id in user_states:
        await route_message(update, context)
    else:
        await update.message.reply_text(
            "Неизвестная команда. Пожалуйста, используйте кнопки:",
            reply_markup=get_main_keyboard()
        )
        
async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in user_states:
        current_state = user_states[user_id]
        
        if current_state.startswith("ADD_TASK_"):
            result = await handle_task_room(update, context)
            if result == "COMPLETE":
                await show_main_menu(update)
            
        elif current_state.startswith("SHOW_TASK_"):
            result = await handle_show_tasks(update, context)
            if result == "COMPLETE":
                await show_main_menu(update)
            
        elif current_state.startswith("DELETE_TASK_"): 
            result = await delete_task(update, context)
            if result == "COMPLETE":
                await show_main_menu(update)
            
async def show_main_menu(update: Update):
    """выдает глав меню с клавой"""
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """регает пользователя и его id"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    user_name = user.first_name or "User"
    if user.last_name:
        user_name += " " + user.last_name

    print(f"🔄 Регистрируем: {user_name} (chat_id: {chat_id})")

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO users (user_name, chat_id) VALUES (%s, %s)',
                    (user_name, chat_id)
                )
                conn.commit()
        
        await update.message.reply_text(
            f"✅ Вы зарегистрированы как {user_name}!",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        print(f"Ошибка регистрации: {e}")  # Теперь выведет реальную ошибку
        await update.message.reply_text("❌ Ошибка регистрации. Попробуйте позже.")

async def set_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args # /set_username Миша

    if not args:
        await update.message.reply_text("❌ Укажите имя, например: /set_username Миша")
        return
    
    assignee_name = args[0] #Миша
    username = user.username #mishapss или none

    if not username:
        await update.message.reply_text("❌ У вас не установлен юзернейм в Telegram. Добавьте его в настройках!")
        return
    
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                # обновляем assignee_mapping
                cursor.execute(
                    'INSERT INTO assignee_mapping (name, username) '
                    'VALUES (%s, %s) '
                    'ON CONFLICT (name) DO UPDATE SET username = EXCLUDED.username',
                    (assignee_name, user.username)
                )
                # 2. Обновляем users (чтобы username был там же)
                cursor.execute(
                    'UPDATE users SET username = %s WHERE chat_id = %s',
                    (username, chat_id)
                )
                conn.commit

        await update.message.reply_text(
            f"✅ Вы привязаны к имени '{assignee_name}'!\n"
            f"Ваш юзернейм: @{username}"
        )
    except Exception as e:
        print(f"ошибка: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

def main():
    TOKEN = ""
    application = ApplicationBuilder().token(TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("myid", get_id))
    application.add_handler(CommandHandler("set_username", set_username))
    
    # Фоновые задачи
    loop = asyncio.get_event_loop()
    loop.create_task(start_notifier(TOKEN))

    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()