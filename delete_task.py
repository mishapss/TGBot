import psycopg2
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from states import user_states, STATE_DELETE_TASK, STATE_WAITING_TASK_NUMBER

DB_CONFIG = {
    "dbname": "",
    "user": "",
    "password": "",
    "host": "",
    "port": 
}

def get_main_keyboard():
    """возвращает клаву"""
    return ReplyKeyboardMarkup(
        [["Посмотреть задания"], ["Добавить задание"], ["Удалить задание"]],
    resize_keyboard=True
    )

async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инициализация процесса удаления задания"""
    user_id = update.effective_user.id
    user_states[user_id] = STATE_DELETE_TASK
    context.user_data.clear()
    
    await update.message.reply_text(
        "Выберите исполнителя:",
        reply_markup=ReplyKeyboardMarkup(
            [["Миша", "Папа", "Мама", "Настя"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик удаления задания"""
    user_id = update.effective_user.id
    user_input = update.message.text.strip()
    current_state = user_states.get(user_id)

    if current_state == STATE_DELETE_TASK:
        if user_input not in ["Миша", "Папа", "Мама", "Настя"]:
            await update.message.reply_text("Пожалуйста, выберите исполнителя из списка")
            return
            
        context.user_data["assignee"] = user_input
        
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        '''SELECT task_id, title FROM tasks 
                        WHERE assignee = %s 
                        ORDER BY due_date NULLS LAST, created_at''',
                        (user_input,)
                    )
                    tasks = cursor.fetchall()

            if not tasks:
                await update.message.reply_text(f"У {user_input} нет заданий", reply_markup=get_main_keyboard())
                del user_states[user_id]
                return
            
            context.user_data["tasks"] = tasks
            tasks_text = "\n".join([f"{idx+1}. {title}" for idx, (_, title) in enumerate(tasks)])
            
            await update.message.reply_text(
                f"Задания {user_input}:\n{tasks_text}\n\n"
                "Введите номер задания для удаления:"
            )
            
            user_states[user_id] = STATE_WAITING_TASK_NUMBER

        except Exception as e:
            await update.message.reply_text("Ошибка при получении заданий")
            print(f"Ошибка: {e}")
            if user_id in user_states:
                del user_states[user_id]
    
    elif current_state == STATE_WAITING_TASK_NUMBER:
        try:
            task_num = int(user_input)
            tasks = context.user_data.get("tasks", [])
            
            if not 1 <= task_num <= len(tasks):
                await update.message.reply_text("Неверный номер задания")
                return
                
            task_id, task_title = tasks[task_num - 1]
            
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        'DELETE FROM tasks WHERE task_id = %s RETURNING title',
                        (task_id,)
                    )
                    deleted_title = cursor.fetchone()[0]
                conn.commit()
                
            await update.message.reply_text(f"✅ Задание '{deleted_title}' удалено!", reply_markup=get_main_keyboard())
            
            return "COMPLETE"

        except ValueError:
            await update.message.reply_text("Введите номер цифрами")
        except Exception as e:
            await update.message.reply_text("Ошибка при удалении")
            print(f"Ошибка: {e}")
        finally:
            # Всегда очищаем состояние
            if user_id in user_states:
                del user_states[user_id]

            context.user_data.clear()
