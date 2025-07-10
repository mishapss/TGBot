from telegram import ReplyKeyboardMarkup

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["Посмотреть задания"], ["Добавить задание"], ["Удалить задание"]],
        resize_keyboard=True
    )