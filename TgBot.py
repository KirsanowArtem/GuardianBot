import logging
import re
import nest_asyncio
import asyncio
import time

from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot, ChatPermissions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, CallbackContext, Updater
from collections import defaultdict
from flask import Flask


nest_asyncio.apply()

group_data = {}
current_number = 1
BOT_TOKEN = "7628643183:AAFkpHzp0o7WTFOKa6pjApDl4FDpr6aAOzs"
ERROR_GROUP_ID = -1002295285798  # ID группы для ошибок
SPECIAL_GROUP_ID = -1002483663129  # ID групы с банами и предупреждениями

"""
group_data = {
    -1001234567890: {  # ID группы
        "group_name": "Название группы",
        "banned_words": ["запрещенное1", "запрещенное2"],  # Список запрещенных слов
        "users": {  # Участники группы
            123456789: {  # ID пользователя
                "name": "Имя пользователя",
                "nickname": "Никнейм пользователя",
                "number": 1,  # Номер пользователя
                "telegram_id": 123456789,  # Telegram ID
                "warnings": 2,  # Количество предупреждений
                "banned": False  # Забанен или нет
            },
            987654321: {
                "name": "Другой пользователь",
                "nickname": "Другой никнейм",
                "number": 2,
                "telegram_id": 987654321,
                "warnings": 0,
                "banned": False
            }
        },
        "MAX_MESSAGES_PER_SECOND": 10,  # Максимум сообщений в секунду для этой группы
        "user_message_timestamps": {},  # Временные метки сообщений для пользователей
    },
    -1009876543210: {  # Другая группа
        "group_name": "Другая группа",
        "banned_words": ["запрещенное3", "запрещенное4"],
        "users": {
            1122334455: {
                "name": "Пользователь 1",
                "nickname": "Ник 1",
                "number": 1,
                "telegram_id": 1122334455,
                "warnings": 0,
                "banned": False
            },
            9988776655: {
                "name": "Пользователь 2",
                "nickname": "Ник 2",
                "number": 2,
                "telegram_id": 9988776655,
                "warnings": 1,
                "banned": False
            }
        },
        "MAX_MESSAGES_PER_SECOND": 10,  # Максимум сообщений в секунду для этой группы
        "user_message_timestamps": {},  # Временные метки сообщений для пользователей
    }
}
"""

async def start(update: Update, context: CallbackContext):
    global current_number  # Указываем, что используем глобальную переменную current_number

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эта команда доступна только в группах.")
        return

    if chat_id not in group_data:
        # Инициализация данных для новой группы
        group_data[chat_id] = {
            'group_name': update.effective_chat.title,
            'users': {},
            'banned_words': [],
            'MAX_MESSAGES_PER_SECOND': 10,  # Максимум сообщений в секунду для этой группы
            'user_message_timestamps': {}  # Временные метки сообщений для пользователей
        }

    if user_id not in group_data[chat_id]['users']:
        formatted_number = str(current_number).zfill(10)
        group_data[chat_id]['users'][user_id] = {
            'name': update.effective_user.first_name or "Без имени",
            'nickname': update.effective_user.username or "Нет никнейма",
            'number': formatted_number,
            'telegram_id': user_id,
            'warnings': 0,
            'banned': False
        }
        current_number += 1  # Увеличиваем current_number

    # Инициализация временных меток сообщений для нового пользователя в группе
    if user_id not in group_data[chat_id]['user_message_timestamps']:
        group_data[chat_id]['user_message_timestamps'][user_id] = []

    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! Ты был добавлен в группу {update.effective_chat.title}. Используй /mygroups для просмотра своих групп."
    )


async def my_groups(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        await update.message.reply_text("Эта команда доступна только в личных сообщениях с ботом.")
        return

    user_id = update.effective_user.id

    # Получение списка групп, в которых есть пользователь
    user_groups = [
        chat_id for chat_id, data in group_data.items()
        if user_id in data['users']
    ]

    if not user_groups:
        await update.message.reply_text("Вы не добавлены ни в одну группу.")
        return

    # Создание кнопок для каждой группы
    keyboard = [
        [InlineKeyboardButton(group_data[chat_id]['group_name'], callback_data=f"group_{chat_id}")]
        for chat_id in user_groups
    ]
    keyboard.append([InlineKeyboardButton("Настройки", callback_data="settings")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Ваши группы:", reply_markup=reply_markup)


async def group_settings(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[1])
    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    group_name = group_data[group_id]['group_name']

    # Кнопки для настроек
    keyboard = [
        [InlineKeyboardButton("Просмотреть всех пользователей", callback_data=f"view_users_{group_id}")],
        [InlineKeyboardButton("Настроить запрещенные слова", callback_data=f"banned_words_{group_id}")],
        [InlineKeyboardButton("Настроить лимит сообщений в секунду", callback_data=f"set_max_messages_{group_id}")],
        [InlineKeyboardButton("Сбросить временные метки сообщений", callback_data=f"reset_timestamps_{group_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(f"Перешли в настройки группы: {group_name}.", reply_markup=reply_markup)


# Команда для настройки лимита сообщений в секунду
async def set_max_messages(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[3])
    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    context.user_data['current_group'] = group_id
    context.user_data['awaiting_max_messages'] = True
    await query.message.reply_text("Введите новый лимит сообщений в секунду:")


# Сохранение нового лимита сообщений
async def save_max_messages(update: Update, context: CallbackContext):
    if not context.user_data.get('awaiting_max_messages'):
        return

    group_id = context.user_data.get('current_group')
    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    try:
        new_limit = int(update.message.text)
        if new_limit < 1:
            await update.message.reply_text("Лимит должен быть положительным числом.")
            return
        # Обновляем значение лимита для группы
        group_data[group_id]['MAX_MESSAGES_PER_SECOND'] = new_limit
        context.user_data['awaiting_max_messages'] = False
        await update.message.reply_text(
            f"Новый лимит сообщений в секунду для группы {group_data[group_id]['group_name']}: {new_limit}"
        )
    except ValueError:
        await update.message.reply_text("Пожалуйста, укажите корректное число.")


# Команда для сброса временных меток сообщений
async def reset_timestamps(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[3])
    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    # Сброс временных меток для этой группы
    group_data[group_id]['user_message_timestamps'] = {}
    await query.message.reply_text(
        f"Временные метки сообщений для группы {group_data[group_id]['group_name']} были сброшены.")


# Команда для настройки запрещённых слов
async def set_banned_words(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    context.user_data['current_group'] = group_id
    context.user_data['awaiting_banned_words'] = True
    await query.message.reply_text(
        "Введите запрещенные слова через запятую с пробелом (, ):"
    )


# Сохранение запрещённых слов
async def save_banned_words(update: Update, context: CallbackContext):
    if not context.user_data.get('awaiting_banned_words'):
        return

    group_id = context.user_data.get('current_group')
    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    banned_words = update.message.text.split(", ")
    group_data[group_id]['banned_words'] = banned_words
    context.user_data['awaiting_banned_words'] = False
    await update.message.reply_text(
        f"Запрещенные слова обновлены для группы {group_data[group_id]['group_name']}: {', '.join(banned_words)}"
    )


async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_text = update.message.text

    # Проверка наличия данных для группы
    if chat_id not in group_data:
        return

    # Получаем MAX_MESSAGES_PER_SECOND и user_message_timestamps для текущей группы
    MAX_MESSAGES_PER_SECOND = group_data[chat_id].get('MAX_MESSAGES_PER_SECOND', 10)
    user_message_timestamps = group_data[chat_id].get('user_message_timestamps', {})

    current_time = time.time()

    # Инициализация временных меток для нового пользователя, если их еще нет
    if user_id not in user_message_timestamps:
        user_message_timestamps[user_id] = []

    # Очистка старых меток сообщений
    user_message_timestamps[user_id] = [timestamp for timestamp in user_message_timestamps[user_id] if current_time - timestamp < 1]

    # Добавление новой метки времени
    user_message_timestamps[user_id].append(current_time)

    # Если количество сообщений больше лимита, обрабатываем как спам
    if len(user_message_timestamps[user_id]) > MAX_MESSAGES_PER_SECOND:
        await handle_spam(update, context, user_id)
        return

    # Проверка на запрещенные слова
    banned_words = group_data[chat_id].get('banned_words', [])
    if any(word in message_text for word in banned_words):
        await check_message(update, context)

async def handle_spam(update: Update, context: CallbackContext, user_id: int):
    chat_id = update.effective_chat.id
    user_data = group_data[chat_id]['users'].get(user_id)
    MAX_MESSAGES_PER_SECOND = group_data[chat_id].get('MAX_MESSAGES_PER_SECOND', 10)

    if user_data:
        if user_data.get('muted', False):
            return

        until_date = datetime.now(timezone.utc) + timedelta(minutes=1)

        # Мутим пользователя на 1 минуту за спам
        await update.message.chat.restrict_member(
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        await update.message.delete()

        # Уведомление пользователя о муте
        await context.bot.send_message(
            user_id, text=f"{update.effective_user.first_name} Вы превысили лимит сообщений. Вам выдано предупреждение, и вы временно замучены на 1 минуту."
        )

        # Уведомление группы о нарушении
        await context.bot.send_message(chat_id, text=f"Пользователь {update.effective_user.first_name} превысил лимит сообщений в секунду.")

        # Увеличиваем количество предупреждений
        user_data['warnings'] += 1
        warnings_count = user_data['warnings']

        # Если 5 предупреждений - баним
        if warnings_count >= 5:
            user_data['banned'] = True

            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) был забанен за 5 предупреждений и спам.\n"
                f"(больше {MAX_MESSAGES_PER_SECOND} сообщений за секунду).\n"
                f"Номер пользователя: {user_data.get('number', 'Не задан')}"
                f"#Ban\n"
                f"#Spam\n"
            )
            await context.bot.send_message(chat_id,f"Пользователь {user_data['name']} был забанен за 5 предупреждений.")
        else:
            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) получил мут на 1 минуту за спам "
                f"(больше {MAX_MESSAGES_PER_SECOND} сообщений за секунду).\n"
                f"Номер пользователя: {user_data.get('number', 'Не задан')}"
                f"#Spam"
            )

        # Отправка сообщения в специальную группу для уведомлений
        await context.bot.send_message(SPECIAL_GROUP_ID, violation_message)

async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text

    user_data = group_data[chat_id]['users'][user_id]
    user_data['warnings'] += 1
    warnings_count = user_data['warnings']

    await update.message.chat.send_message(
        f"{user_data['name']} вы использовали запрещенное слово! Всего предупреждений: {warnings_count}."
    )
    await update.message.delete()

    if warnings_count >= 5:
        user_data['banned'] = True

        violation_message = (
            f"Пользователь {update.effective_user.first_name} "
            f"(@{update.effective_user.username}) был забанен за 5 предупреждений.\n"
            f"Сообщение:\n{message_text}\n"
            f"Номер пользователя: {user_data.get('number', 'Не задан')}"
            f"#Ban\n"
        )

        await context.bot.send_message(chat_id, f"Пользователь {user_data['name']} был забанен за 5 предупреждений.")
        await context.bot.send_message(SPECIAL_GROUP_ID, violation_message)
        await context.bot.ban_chat_member(chat_id, user_id)
    else:
        violation_message = (
            f"Пользователь {update.effective_user.first_name} "
            f"(@{update.effective_user.username}) использовал запрещенное слово: {update.message.text}.\n"
            f"Всего предупреждений: {warnings_count}.\n"
            f"Сообщение:\n{message_text}\n"
            f"Номер пользователя: {user_data.get('number', 'Не задан')}"
            f"#Warn\n"
        )
        await context.bot.send_message(SPECIAL_GROUP_ID, violation_message)

async def warn_user(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /warn @username")
        return

    target_username = context.args[0].lstrip("@")
    target_user = None

    for uid, user_data in group_data[chat_id]['users'].items():
        if user_data['nickname'] == target_username:
            target_user = user_data
            break

    if not target_user:
        await update.message.reply_text(f"Пользователь с username @{target_username} не найден.")
        return

    target_user['warnings'] += 1
    warnings_count = target_user['warnings']

    await update.message.reply_text(f"Пользователь @{target_username} получил предупреждение. Всего: {warnings_count}.")

    if warnings_count >= 5:
        target_user['banned'] = True
        await update.message.reply_text(f"Пользователь @{target_username} был забанен за 5 предупреждений.")

async def view_users(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    users = group_data[group_id].get('users', {})
    if not users:
        await query.edit_message_text("В группе пока нет пользователей.")
        return

    response = f"Информация о пользователях в группе {group_data[group_id]['group_name']}:\n\n"
    for user_id, info in users.items():
        response += (f"ID: {user_id}\nИмя: {info['name']}\n"
                     f"Никнейм: {info['nickname']}\n"
                     f"Номер: {info['number']}\n"
                     f"Телеграм ID: {info['telegram_id']}\n"
                     f"Замечания: {info['warnings']}\nЗабанен: {info['banned']}\n\n")

    await query.edit_message_text(response)

async def handle_callback_query(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data.startswith("group_"):
        await group_settings(update, context)
    elif query.data.startswith("banned_words_"):
        await set_banned_words(update, context)
    elif query.data.startswith("view_users_"):
        await view_users(update, context)

async def user_info(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if chat_id not in group_data or user_id not in group_data[chat_id]['users']:
        await update.message.reply_text("Информация о вас в этой группе отсутствует.")
        return

    user_data = group_data[chat_id]['users'][user_id]
    response = (f"Информация о пользователе:\n"
                f"Имя: {user_data['name']}\n"
                f"Никнейм: {user_data['nickname']}\n"
                f"Номер: {user_data['number']}\n"
                f"Telegram ID: {user_data['telegram_id']}\n"
                f"Замечания: {user_data['warnings']}\n"
                f"Забанен: {user_data['banned']}")
    await update.message.reply_text(response)

async def ban_user(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /ban <user_id>")
        return

    target_user_id = int(context.args[0])
    if chat_id in group_data and target_user_id in group_data[chat_id]['users']:
        group_data[chat_id]['users'][target_user_id]['banned'] = True
        await update.message.reply_text(f"Пользователь {group_data[chat_id]['users'][target_user_id]['name']} забанен.")
    else:
        await update.message.reply_text("Пользователь не найден.")

async def unban_user(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /unban <user_id>")
        return

    target_user_id = int(context.args[0])
    if chat_id in group_data and target_user_id in group_data[chat_id]['users']:
        group_data[chat_id]['users'][target_user_id]['banned'] = False
        await update.message.reply_text(f"Пользователь {group_data[chat_id]['users'][target_user_id]['name']} разбанен.")
    else:
        await update.message.reply_text("Пользователь не найден.")


async def send_error_message(application: Application, error: str, group_name: str, update: Update = None):
    error_message = f"Ошибка в группе {group_name} (ссылка: https://t.me/c/{str(ERROR_GROUP_ID)[4:]})\n\nОшибка: {error}"

    if update and update.message:
        message_link = f"https://t.me/{update.effective_chat.username}/{update.message.message_id}"
        error_message += f"\nСообщение, в котором произошла ошибка: {message_link}"

    await application.bot.send_message(ERROR_GROUP_ID, error_message)


async def debug(update: Update, context: CallbackContext):
    await update.message.reply_text(str(group_data))

async def process_message(update: Update, context: CallbackContext):
    if context.user_data.get('awaiting_banned_words', False):
        await save_banned_words(update, context)
    else:
        await handle_message(update, context)

async def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mygroups", my_groups))
    application.add_handler(CommandHandler("userinfo", user_info))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CallbackQueryHandler(group_settings, pattern="^group_"))
    application.add_handler(CallbackQueryHandler(view_users, pattern="^view_users_"))
    application.add_handler(CallbackQueryHandler(set_banned_words, pattern="^banned_words_"))
    application.add_handler(CallbackQueryHandler(set_max_messages, pattern="^set_max_messages_"))
    application.add_handler(CallbackQueryHandler(reset_timestamps, pattern="^reset_timestamps_"))


    application.add_handler(MessageHandler(filters.TEXT, process_message))

    try:
        await application.run_polling()
    except Exception as e:
        print("-------------------------------------------------------------------------------------------------")
        await send_error_message(application, str(e), "Guardian_Помилки", None)
        logging.error(f"Ошибка в main: {e}")



if __name__ == "__main__":
    asyncio.run(main())