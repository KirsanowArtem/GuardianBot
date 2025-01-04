import logging
import re
import nest_asyncio
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters, CallbackContext
)


nest_asyncio.apply()

group_users = {}
user_groups = {}
group_data = {}
current_group_settings = {}
user_warnings = {}
banned_words = {}
current_number = 1
banning_speech = ['1', '2', '3']
BOT_TOKEN = "7628643183:AAFkpHzp0o7WTFOKa6pjApDl4FDpr6aAOzs"
ERROR_GROUP_ID = -1002295285798  # ID группы для ошибок
SPECIAL_GROUP_ID = -100123456789  # ID групы с банами и предупреждениями

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эта команда доступна только в группах.")
        return

    if chat_id not in group_data:
        global current_number
        formatted_number = str(current_number).zfill(10)
        group_data[chat_id] = {
            'group_name': update.effective_chat.title,
            'users': {},
            'banned_words': []
        }
        current_number += 1

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
        current_number += 1

    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! Ты был добавлен в группу {update.effective_chat.title}. Используй /mygroups для просмотра своих групп."
    )

async def my_groups(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        await update.message.reply_text("Эта команда доступна только в личных сообщениях с ботом.")
        return

    user_id = update.effective_user.id

    user_groups = [
        chat_id for chat_id, data in group_data.items()
        if user_id in data['users']
    ]

    if not user_groups:
        await update.message.reply_text("Вы не добавлены ни в одну группу.")
        return

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
    keyboard = [
        [InlineKeyboardButton("Просмотреть всех пользователей", callback_data=f"view_users_{group_id}")],
        [InlineKeyboardButton("Настроить запрещенные слова", callback_data=f"banned_words_{group_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(f"Перешли в настройки группы: {group_name}.", reply_markup=reply_markup)

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
    if context.user_data.get('awaiting_banned_words', False):
        await save_banned_words(update, context)
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text

    if chat_id not in group_data:
        return

    banned_words = group_data[chat_id].get('banned_words', [])

    if any(word in message_text for word in banned_words):

        await check_message(update, context)

        if user_id not in group_data[chat_id]['users']:
            return

        group_data[chat_id]['users'][user_id]['warnings'] += 1
        warnings_count = group_data[chat_id]['users'][user_id]['warnings']

        if warnings_count >= 5:
            group_data[chat_id]['users'][user_id]['banned'] = True
            await update.message.reply_text(
                f"{update.effective_user.first_name} был заблокирован за 5 предупреждений."
            )



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

async def warn_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.message.chat.id

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /warn @username")
        return

    target_user_username = context.args[0].lstrip('@')
    target_user_data = None

    if chat_id not in group_data:
        await update.message.reply_text(f"В этой группе нет зарегистрированных пользователей.")
        return

    for u_id, u_data in group_data[chat_id]['users'].items():
        if u_data.get('nickname') == target_user_username:
            target_user_data = u_data
            break

    if not target_user_data:
        await update.message.reply_text(f"Пользователь с username @{target_user_username} не найден.")
        return

    target_user_data['warnings'] += 1
    warnings_count = target_user_data['warnings']

    await update.message.reply_text(f"Пользователь @{target_user_username} получил замечание. Всего замечаний: {warnings_count}.")

    if warnings_count >= 5:
        target_user_data['banned'] = True
        await update.message.reply_text(f"Пользователь @{target_user_username} был забанен за 5 предупреждений.")

        violation_message = (
            f"Пользователь @{target_user_username} "
            f"был забанен за 5 предупреждений в группе {group_data[chat_id]['group_name']}."
        )

        await context.bot.send_message(chat_id=-4613640811, text=violation_message)

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

    if user_id not in current_group_settings:
        await update.message.reply_text("Вы не выбрали группу. Используйте /mygroups, чтобы выбрать группу.")
        return

    group_id = current_group_settings[user_id]
    if group_id not in group_users:
        await update.message.reply_text("Информация о пользователях в этой группе отсутствует.")
        return

    response = "Информация о пользователях:\n"
    for user_id, info in group_users.items():
        response += (f"ID: {user_id}\nИмя: {info['name']}\n"
                    f"Никнейм: {info['nickname']}\n"
                    f"Номер: {info['number']}\n"
                    f"Телеграм ID: {info['telegram_id']}\n"
                    f"Замечания: {info['warnings']}\nЗабанен: {info['banned']}\n\n")

    await update.message.reply_text(response)

async def ban_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id not in current_group_settings:
        await update.message.reply_text("Вы не выбрали группу. Используйте /mygroups, чтобы выбрать группу.")
        return

    group_id = current_group_settings[user_id]

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /ban <user_id>")
        return

    target_user_id = int(context.args[0])
    if target_user_id in group_users:
        group_users[target_user_id]['banned'] = True
        await update.message.reply_text(f"Пользователь {group_users[target_user_id]['name']} забанен.")
    else:
        await update.message.reply_text("Пользователь не найден.")

async def unban_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id not in current_group_settings:
        await update.message.reply_text("Вы не выбрали группу. Используйте /mygroups, чтобы выбрать группу.")
        return

    group_id = current_group_settings[user_id]

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /unban <user_id>")
        return

    target_user_id = int(context.args[0])
    if target_user_id in group_users:
        group_users[target_user_id]['banned'] = False
        await update.message.reply_text(f"Пользователь {group_users[target_user_id]['name']} разбанен.")
    else:
        await update.message.reply_text("Пользователь не найден.")


async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.lower()

    if any(banned_word in message_text for banned_word in banning_speech):
        if user_id not in group_users:
            group_users[user_id] = {'warnings': 0, 'banned': False}

        group_users[user_id]['warnings'] += 1
        warnings_count = group_users[user_id]['warnings']

        await update.message.chat.send_message(
            f"{update.effective_user.first_name} вы использовали запрещенное слово!\nВсего предупреждений: {warnings_count}."
        )
        await update.message.delete()

        if warnings_count >= 5:
            group_users[user_id]['banned'] = True
            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) был забанен за 5 предупреждений.\n"
                f"Сообщение:\n{message_text}\n"
                f"#Ban\n"
                f"Номер пользователя: {group_users[user_id].get('number', 'Не задан')}"
            )
            print(f"Номер пользователя: {group_users[user_id].get('number')}")

            await context.bot.send_message(-4613640811, violation_message)
            try:
                await context.bot.ban_chat_member(update.message.chat.id, user_id)
                await update.message.reply_text(f"Вы были забанены за 5 предупреждений.")
            except Exception as e:
                await update.message.reply_text(f"Не удалось забанить пользователя: {e}")
        else:
            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) использовал запрещенное слово: {update.message.text}.\n"
                f"Всего предупреждений: {warnings_count}.\n"
                f"Сообщение:\n{message_text}\n"
                f"#Warn\n"
                f"Номер пользователя: {group_users[user_id].get('number', 'Не задан')}"
            )
            await context.bot.send_message(-4613640811, violation_message)

async def send_error_message(application: Application, error: str, group_name: str):
    error_message = f"Ошибка в группе {group_name} (ссылка: https://t.me/c/{str(ERROR_GROUP_ID)[4:]})\n\nОшибка: {error}"
    await application.bot.send_message(ERROR_GROUP_ID, error_message)

async def debug(update: Update, context: CallbackContext):
    await update.message.reply_text(str(group_data))

async def process_message(update: Update, context: CallbackContext):
    if context.user_data.get('awaiting_banned_words', False):
        await save_banned_words(update, context)
    else:
        await handle_message(update, context)

def add_warning(user_id):
    if user_id not in user_warnings:
        user_warnings[user_id] = 0
    user_warnings[user_id] += 1
    return user_warnings[user_id]


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
    application.add_handler(MessageHandler(filters.TEXT, process_message))

    try:
        await application.run_polling()
    except Exception as e:
        logging.error(f"Ошибка в main: {e}")



if __name__ == "__main__":
    asyncio.run(main())