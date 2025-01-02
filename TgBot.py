import nest_asyncio
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters, \
    ContextTypes

nest_asyncio.apply()

group_users = {}
user_groups = {}
current_group_settings = {}
current_number = 1  # Стартовый номер
banning_speech = ['1', '2', '3']
BOT_TOKEN = "7628643183:AAFkpHzp0o7WTFOKa6pjApDl4FDpr6aAOzs"
ERROR_GROUP_ID = -1002295285798  # ID группы для ошибок


async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Проверяем, является ли чат группой
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эта команда доступна только в группах.")
        return

    # Добавление пользователя в список участников группы
    if user_id not in group_users:
        # Форматируем номер с ведущими нулями
        global current_number
        formatted_number = str(current_number).zfill(10)

        group_users[user_id] = {
            'name': update.effective_user.first_name or "Без имени",
            'nickname': update.effective_user.username or "Нет никнейма",
            'number': formatted_number,
            'telegram_id': user_id,
            'warnings': 0,
            'banned': False
        }
        current_number += 1  # Увеличиваем номер для следующего пользователя

    # Добавляем группу в список групп пользователя, если еще нет
    if user_id not in user_groups:
        user_groups[user_id] = {}

    user_groups[user_id][str(chat_id)] = update.effective_chat.title

    # Ответ пользователю
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! Ты был добавлен в группу {update.effective_chat.title}. Используй /mygroups для просмотра своих групп."
    )


async def my_groups(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id not in user_groups or not user_groups[user_id]:
        await update.message.reply_text("Вы не добавлены ни в одну группу.")
        return

    keyboard = [
        [InlineKeyboardButton(group_name, callback_data=f"group_{group_id}")]
        for group_id, group_name in user_groups[user_id].items()
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Ваши группы:", reply_markup=reply_markup)

async def group_settings(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    group_id = query.data.split("_")[1]
    group_name = user_groups[query.from_user.id].get(group_id, "Неизвестная группа")

    current_group_settings[query.from_user.id] = group_id

    keyboard = [[InlineKeyboardButton("Просмотреть всех пользователей", callback_data=f"view_users_{group_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(f"Перешли в настройки группы: {group_name}.", reply_markup=reply_markup)

async def view_users(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    group_id = query.data.split("_")[2]
    response = "Информация о пользователях:\n"

    for user_id, info in group_users.items():
        response += (f"ID: {user_id}\nИмя: {info['name']}\n"
                    f"Никнейм: {info['nickname']}\n"
                    f"Номер: {info['number']}\n"
                    f"Телеграм ID: {info['telegram_id']}\n"  # Добавили ID пользователя
                    f"Замечания: {info['warnings']}\nЗабанен: {info['banned']}\n\n")

    await query.edit_message_text(response)

async def locate(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id

    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эта команда работает только в группах.")
        return

    try:
        # Получаем количество участников в чате
        total_members = await context.bot.get_chat_members_count(chat_id)
        print(f"Количество участников в группе: {total_members}")

        # Получаем список администраторов (например, для подтверждения доступности бота)
        admins = await context.bot.get_chat_administrators(chat_id)
        all_members = {admin.user.id: admin.user for admin in admins}

        # Получаем всех участников чата
        async for member in context.bot.get_chat_members(chat_id):
            user_id = member.user.id
            user = member.user
            if user_id not in all_members:
                # Для каждого участника добавляем пользователя в базу данных или список
                if user_id not in group_users:
                    global current_number  # Используем глобальную переменную для инкремента
                    formatted_number = str(current_number).zfill(10)  # Форматируем номер с ведущими нулями
                    group_users[user_id] = {
                        'name': user.first_name or "Без имени",
                        'nickname': user.username or "Нет никнейма",
                        'number': formatted_number,  # Сохраняем как строку с 10 символами
                        'telegram_id': user_id,  # Добавляем Telegram ID
                        'warnings': 0,
                        'banned': False
                    }
                    current_number += 1  # Увеличиваем номер для следующего пользователя

                if user_id not in user_groups:
                    user_groups[user_id] = {}

                user_groups[user_id][str(chat_id)] = update.effective_chat.title

        await update.message.reply_text(f"Список пользователей успешно обновлён. Количество участников: {total_members}.")

    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении участников: {e}")

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

async def warn_user(update: Update, context: CallbackContext):
    print("1 - warn_user вызвана")
    user_id = update.effective_user.id
    chat_id = update.message.chat.id  # Получаем ID чата (группы)

    # Проверка аргументов
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /warn @username")
        return

    target_user_username = context.args[0].lstrip('@')  # Убираем @ в случае, если он есть
    target_user_id = None

    print(f"2 - Поиск пользователя с username: {target_user_username}")

    # Проверяем, если в group_users есть этот чат
    if chat_id not in group_users:
        await update.message.reply_text(f"В этой группе нет зарегистрированных пользователей.")
        return

    # Ищем пользователя в группе
    for user_id, user_data in group_users[chat_id].items():
        if user_data.get('username') == target_user_username:
            target_user_id = user_id
            print(f"3 - Найден пользователь: {target_user_username}, id: {target_user_id}")
            break

    if target_user_id is None:
        await update.message.reply_text(f"Пользователь с username @{target_user_username} не найден.")
        return

    # Если в группе еще нет информации о пользователе, создаем ее
    if target_user_id not in group_users[chat_id]:
        group_users[chat_id][target_user_id] = {'warnings': 0, 'banned': False}

    # Добавляем предупреждение
    group_users[chat_id][target_user_id]['warnings'] += 1
    warnings_count = group_users[chat_id][target_user_id]['warnings']
    print(f"4 - Всего замечаний для {target_user_id}: {warnings_count}")

    await update.message.reply_text(f"Пользователь @{target_user_username} получил замечание. Всего замечаний: {warnings_count}.")

    # Если пользователь набрал 5 предупреждений, то он будет забанен
    if warnings_count >= 5:
        group_users[chat_id][target_user_id]['banned'] = True
        await update.message.reply_text(f"Пользователь @{target_user_username} был забанен за 5 предупреждений.")

        # Отправка сообщения в группу с ID -4613640811
        violation_message = (
            f"Пользователь @{target_user_username} "
            f"был забанен за 5 предупреждений."
        )
        await context.bot.send_message(-4613640811, violation_message)

        # Баним пользователя в чате
        try:
            await context.bot.ban_chat_member(chat_id, target_user_id)
            await update.message.reply_text(f"Пользователь @{target_user_username} был забанен в группе.")
        except Exception as e:
            await update.message.reply_text(f"Не удалось забанить пользователя: {e}")


async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.lower()

    # Проверка на наличие запрещенных слов
    if any(banned_word in message_text for banned_word in banning_speech):
        # Увеличиваем количество предупреждений для пользователя
        if user_id not in group_users:
            group_users[user_id] = {'warnings': 0, 'banned': False}  # Добавлен флаг 'banned'

        group_users[user_id]['warnings'] += 1
        warnings_count = group_users[user_id]['warnings']

        # Отправляем предупреждение пользователю
        await update.message.chat.send_message(
            f"Вы использовали запрещенное слово! Всего предупреждений: {warnings_count}."
        )

        # Удаляем сообщение
        await update.message.delete()

        # Если пользователь набрал 5 предупреждений, баним его
        if warnings_count >= 5:
            # Обновляем статус пользователя как забаненного
            group_users[user_id]['banned'] = True
            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) был забанен за 5 предупреждений."
            )
            await context.bot.send_message(-4613640811, violation_message)

            # Баним пользователя в чате
            try:
                await context.bot.ban_chat_member(update.message.chat.id, user_id)
                await update.message.reply_text(f"Вы были забанены за 5 предупреждений.")
            except Exception as e:
                await update.message.reply_text(f"Не удалось забанить пользователя: {e}")
        else:
            # Если предупреждения меньше 5
            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) использовал запрещенное слово: {update.message.text}. "
                f"Всего предупреждений: {warnings_count}."
                f"#Warm"
            )
            await context.bot.send_message(-4613640811, violation_message)


async def send_error_message(application: Application, error: str, group_name: str):
    # Отправка сообщения об ошибке в группу
    error_message = f"Ошибка в группе {group_name} (ссылка: https://t.me/c/{str(ERROR_GROUP_ID)[4:]})\n\nОшибка: {error}"
    await application.bot.send_message(ERROR_GROUP_ID, error_message)


async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mygroups", my_groups))
    application.add_handler(CallbackQueryHandler(group_settings, pattern="^group_"))
    application.add_handler(CallbackQueryHandler(view_users, pattern="^view_users_"))
    application.add_handler(CommandHandler("locate", locate))
    application.add_handler(CommandHandler("userinfo", user_info))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("warn", warn_user))

    # Добавляем обработчик сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))

    # Запуск приложения
    try:
        await application.run_polling()
    except Exception as e:
        await send_error_message(application, str(e), "Основная группа")  # Пример вызова ошибки

if __name__ == "__main__":
    asyncio.run(main())