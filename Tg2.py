import logging
import re
import nest_asyncio
import asyncio
import time
import random
import io
import string

from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot, ChatPermissions, CallbackQuery
from telegram.constants import ChatMemberStatus

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, CallbackContext, Updater

from PIL import Image, ImageDraw, ImageFont

from collections import defaultdict
from flask import Flask






nest_asyncio.apply()

group_data = {}
captcha_data = {}
current_number = 1
BOT_TOKEN = "7628643183:AAFkpHzp0o7WTFOKa6pjApDl4FDpr6aAOzs"
ERROR_GROUP_ID = -1002295285798  # ID группы для ошибок

"""
group_data = {
    -1001234567890: {  # ID группы
        "group_name": "Название группы",
        "banned_words": ["запрещенное1", "запрещенное2"],  # Список запрещенных слов
        "users": {  # Участники группы
            123456789: {  # ID пользователя
                "name": "Имя пользователя",
                "nickname": "Никнейм пользователя",
                "telegram_id": 123456789,  # Telegram ID
                "warnings": 2,  # Количество предупреждений
                "banned": False  # Забанен или нет
            },
            987654321: {
                "name": "Другой пользователь",
                "nickname": "Другой никнейм",
                "telegram_id": 987654321,
                "warnings": 0,
                "banned": False
            }
        },
        "MAX_MESSAGES_PER_SECOND": 10,  # Максимум сообщений в секунду для этой группы
        "MUT_SECONDS": 120, # Время временного мута
        "SPECIAL_GROUP_ID": -1002483663129,    # ID групы с банами и предупреждениями
        "CAPTCHA_TIMEOUT": 3600,  # Максимальное время бездействия капчи
        "CAPTCHA_ATTEMPTS": 5,    # Максимальное количество попыток капчи
        "user_message_timestamps": {},  # Временные метки сообщений для пользователей
        "rules": "Нет",  # Правила группы
        "feedback": "Нет",  # Обратная связь для группы
    },
    -1009876543210: {  # Другая группа
        "group_name": "Другая группа",
        "banned_words": ["запрещенное3", "запрещенное4"],
        "users": {
            1122334455: {
                "name": "Пользователь 1",
                "nickname": "Ник 1",
                "telegram_id": 1122334455,
                "warnings": 0,
                "banned": False
            },
            9988776655: {
                "name": "Пользователь 2",
                "nickname": "Ник 2",
                "telegram_id": 9988776655,
                "warnings": 1,
                "banned": False
            }
        },
        "MAX_MESSAGES_PER_SECOND": 10,  # Максимум сообщений в секунду для этой группы
        "MUT_SECONDS"'": 300, # Время временного мута
        "SPECIAL_GROUP_ID": -1002295285798,    # ID групы с банами и предупреждениями
        "CAPTCHA_TIMEOUT": 60,  # Максимальное время бездействия капчи
        "CAPTCHA_ATTEMPTS": 2,    # Максимальное количество попыток капчи
        "user_message_timestamps": {},  # Временные метки сообщений для пользователей
        "rules": "Не спамить",  # Правила группы
        "feedback": "Пока что ее нет",  # Обратная связь для группы
    }
}
"""


async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эта команда доступна только в группах.")
        return

    if chat_id not in group_data:
        group_data[chat_id] = {
            'group_name': update.effective_chat.title,
            'users': {},
            'banned_words': [],
            'MAX_MESSAGES_PER_SECOND': 10,
            'MUT_SECONDS': 60,
            'SPECIAL_GROUP_ID': -1002483663129,
            'CAPTCHA_TIMEOUT': 3600,
            'CAPTCHA_ATTEMPTS': 5,
            'user_message_timestamps': {},
            'rules': "Правила не заданы.",
            'feedback': "Обратная связь не задана.",
        }

    chat_member = await update.effective_chat.get_member(user_id)

    # Обновляем информацию о пользователе в group_data
    if user_id not in group_data[chat_id]['users']:
        group_data[chat_id]['users'][user_id] = {
            'name': update.effective_user.first_name or "Без имени",
            'nickname': update.effective_user.username or "Нет никнейма",
            'telegram_id': user_id,
            'warnings': 0,
            'banned': False,
            'captcha_attempts': 0,
            'captcha_expiry': datetime.now(timezone.utc) + timedelta(hours=1),
            'status': chat_member.status  # Сохраняем статус пользователя
        }
    else:
        # Обновляем статус пользователя, если он уже есть в группе
        group_data[chat_id]['users'][user_id]['status'] = chat_member.status

    if chat_member.status == 'creator':
        await update.message.reply_text("Вы не можете быть ограничены, так как являетесь владельцем чата.")
        return

    until_date = datetime.now(timezone.utc) + timedelta(hours=1)
    await update.message.chat.restrict_member(
        user_id,
        ChatPermissions(can_send_messages=False),
        until_date=until_date
    )
    await send_captcha(update, context, chat_id, user_id)

async def send_captcha(update: Update, context: CallbackContext, chat_id, user_id):
    characters = string.ascii_lowercase + string.digits
    correct_text = ''.join(random.choices(characters, k=8))

    wrong_answers = set()
    while len(wrong_answers) < 3:
        wrong_text = ''.join(
            random.choice(characters) if random.random() > 0.7 else c
            for c in correct_text
        )
        if wrong_text != correct_text:
            wrong_answers.add(wrong_text)

    options = list(wrong_answers) + [correct_text]
    random.shuffle(options)

    if user_id not in captcha_data:
        captcha_data[user_id] = {
            'correct_text': correct_text,
            'attempts': 0,
            'expiry': datetime.now(timezone.utc) + timedelta(seconds=group_data[chat_id].get("CAPTCHA_TIMEOUT", 3600)),
            'captcha_message_id': None,
        }
    else:
        captcha_data[user_id]['correct_text'] = correct_text

    image = Image.new('RGB', (200, 75), color='white')
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 160)
    except IOError:
        font = ImageFont.load_default()

    draw.text((50, 50), f"{correct_text}", font=font, fill='black')

    image_stream = io.BytesIO()
    image.save(image_stream, format='PNG')
    image_stream.seek(0)

    buttons = [[InlineKeyboardButton(text=option, callback_data=f"captcha_{user_id}_{option}")] for option in options]
    keyboard = InlineKeyboardMarkup(buttons)

    user_name = f"@{group_data[chat_id]['users'][user_id]['nickname']}" if group_data[chat_id]['users'][user_id][
        'nickname'] else group_data[chat_id]['users'][user_id]['name']

    message = await context.bot.send_photo(
        chat_id=chat_id,
        photo=image_stream,
        caption=f"{user_name}, выберите правильный вариант:",
        reply_markup=keyboard
    )

    captcha_data[user_id]['captcha_message_id'] = message.message_id

async def captcha_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = int(query.data.split("_")[1])
    selected_option = query.data.split("_")[2]
    chat_id = query.message.chat.id
    current_user_id = query.from_user.id

    if current_user_id != user_id:
        if current_user_id in captcha_data:
            await query.answer("Это не ваша капча. Пройдите свою.")
            await query.message.reply_text(
                f"@{query.from_user.username}, пожалуйста, пройдите свою капчу."
            )
        else:
            chat_member = await context.bot.get_chat_member(chat_id, current_user_id)
            if chat_member.status not in ["administrator", "creator"]:
                await captcha_ban_user(update, context, chat_id, current_user_id, timeout_expired=False)
        return

    if current_user_id not in captcha_data:
        await query.answer("Вы уже прошли капчу.")
        return

    captcha_info = captcha_data[current_user_id]
    if datetime.now(timezone.utc) > captcha_info['expiry']:
        await query.message.delete()
        await captcha_ban_user(update, context, chat_id, current_user_id, timeout_expired=True)
        del captcha_data[current_user_id]
        return

    if selected_option == captcha_info['correct_text']:
        await query.message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text="Капча пройдена! Мут снят."
        )
        await query.message.chat.restrict_member(
            current_user_id,
            ChatPermissions(can_send_messages=True)
        )
        del captcha_data[current_user_id]
    else:
        captcha_info['attempts'] += 1
        if captcha_info['attempts'] >= group_data[chat_id].get("CAPTCHA_ATTEMPTS", 5):
            await query.message.delete()
            await captcha_ban_user(update, context, chat_id, current_user_id, timeout_expired=False)
            del captcha_data[current_user_id]
        else:
            await query.message.delete()
            await send_captcha(update, context, chat_id, current_user_id)

async def captcha_ban_user(update: Update, context: CallbackContext, chat_id, user_id, timeout_expired=False):
    await context.bot.ban_chat_member(chat_id, user_id)
    group_data[chat_id]['users'][user_id]['banned'] = True
    name = group_data[chat_id]['users'][user_id]['name']
    reason = "превышено время ожидания" if timeout_expired else "превышено количество попыток"
    ban_message = (
        f"Пользователь {name} удален из чата за {reason}.\n"
        f"#CAPTCHA_BAN\n"
        f"#BAN"
    )

    special_group_id = group_data[chat_id].get("SPECIAL_GROUP_ID", -1002483663129)
    await context.bot.send_message(special_group_id, ban_message)
    await context.bot.send_message(chat_id, f"Пользователь {name} удален из чата за {reason}.")

async def new_member(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    for member in update.message.new_chat_members:
        user_id = member.id

        chat_member = await update.effective_chat.get_member(user_id)
        if chat_member.status == 'creator':
            continue

        if chat_id not in group_data:
            group_data[chat_id] = {
                'group_name': update.effective_chat.title,
                'users': {},
                'banned_words': [],
                'MAX_MESSAGES_PER_SECOND': 10,
                'MUT_SECONDS': 60,
                'SPECIAL_GROUP_ID': -1002483663129,
                'user_message_timestamps': {}
            }

        if user_id not in group_data[chat_id]['users']:
            group_data[chat_id]['users'][user_id] = {
                'name': member.first_name or "Без имени",
                'nickname': member.username or "Нет никнейма",
                'telegram_id': user_id,
                'warnings': 0,
                'banned': False,
                'captcha_attempts': 0,
                'captcha_expiry': datetime.now(timezone.utc) + timedelta(hours=1)
            }

        until_date = datetime.now(timezone.utc) + timedelta(seconds=60)
        await update.message.chat.restrict_member(
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        await send_captcha(update, context, chat_id, user_id)







async def my_groups(update: Update, context: CallbackContext):
    """Отображает группы с разделением на роли."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    admin_groups = [
        g_id for g_id, data in group_data.items()
        if user_id in data['users']
        and (await context.bot.get_chat_member(g_id, user_id)).status in ['administrator', 'creator']
    ]

    user_groups = [
        g_id for g_id, data in group_data.items()
        if user_id in data['users']
        and (await context.bot.get_chat_member(g_id, user_id)).status not in ['administrator', 'creator']
    ]

    keyboard = [
        [InlineKeyboardButton("Администратор", callback_data="role_admin")],
        [InlineKeyboardButton("Пользователь", callback_data="role_user")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_message = await update.message.reply_text("Выберите свою роль:", reply_markup=reply_markup)

    # Инициализация данных группы и сообщений бота
    if chat_id not in group_data:
        group_data[chat_id] = {
            "group_name": update.effective_chat.title,
            "banned_words": [],
            "users": {},
            "bot_messages": []
        }

    group_data[chat_id]["bot_messages"].append({"id": sent_message.message_id, "path": "start/"})
    print(f"Добавлено сообщение {sent_message.message_id} с путем start/")

async def role_handler(update: Update, context: CallbackContext):
    query = update.callback_query

    user_id = query.from_user.id
    role = query.data.split("_")[1]
    chat_id = query.message.chat.id
    message_id = query.message.message_id

    # Проверка наличия данных
    if chat_id not in group_data:
        return await query.edit_message_text("Ошибка: Данные группы не найдены.")

    # Обновляем путь в сообщении
    for msg in group_data[chat_id]["bot_messages"]:
        if msg["id"] == message_id:
            msg["path"] += f"{role}/"
            print(f"Обновлен путь для сообщения {message_id}: {msg['path']}")
            break

    if role == "admin":
        groups = [
            g_id for g_id, data in group_data.items()
            if user_id in data["users"]
            and (await context.bot.get_chat_member(g_id, user_id)).status in ['administrator', 'creator']
        ]
    else:
        groups = [
            g_id for g_id, data in group_data.items()
            if user_id in data["users"]
            and (await context.bot.get_chat_member(g_id, user_id)).status not in ['administrator', 'creator']
        ]

    if not groups:
        keyboard = []
        keyboard.append([InlineKeyboardButton("Назад", callback_data=f"go_back_{chat_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("У вас нет доступных групп.", reply_markup=reply_markup)
        return

    keyboard = [
        [InlineKeyboardButton(group_data[g_id]["group_name"], callback_data=f"{role}_group_{g_id}")]
        for g_id in groups
    ]

    keyboard.append([InlineKeyboardButton("Назад", callback_data=f"go_back_{chat_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите группу:", reply_markup=reply_markup)

async def group_settings(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    # Разделение данных callback_data
    data_parts = query.data.split("_")
    if len(data_parts) != 3 or data_parts[0] != "group" or data_parts[1] != "settings":
        await query.message.reply_text("Некорректный формат данных. Попробуйте снова.")
        return

    group_id = int(data_parts[-1])  # Получаем ID группы
    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    chat_id = query.message.chat.id
    message_id = query.message.message_id

    for msg in group_data.get(chat_id, {}).get("bot_messages", []):
        if msg["id"] == message_id:
            msg["path"] += "group_settings/"
            print(f"Обновлен путь для сообщения {message_id}: {msg['path']}")
            break

    group_name = group_data[group_id]['group_name']
    # Формируем кнопки настроек группы
    keyboard = [


        [InlineKeyboardButton("Настроить группу с предупреждениями и банами", callback_data=f"set_warn_grup_{group_id}")],
        [InlineKeyboardButton("Просмотреть настройки группы", callback_data=f"view_settings_{group_id}")],
        [InlineKeyboardButton("Изменить описание правил группы", callback_data=f"set_rules_grup_{group_id}")],
        [InlineKeyboardButton("Изменить обратную связь для группы", callback_data=f"set_feedback_grup_{group_id}")],
        [InlineKeyboardButton("Назад", callback_data=f"go_back_{group_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Используем функцию для проверки и редактирования
    await edit_message_if_needed(query, f"Настройки группы: {group_name}", reply_markup)

async def rules(update: Update, context: CallbackContext):
    """Отображает правила группы."""
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[1])
    rules = group_data[group_id].get("rules", "Правила не заданы.")

    settings = group_data[group_id]
    response = (
        f"Правила группы: {settings['group_name']}:\n"
        f"- Лимит сообщений в секунду: {settings['MAX_MESSAGES_PER_SECOND']}\n"
        f"- Время временного мута: {settings['MUT_SECONDS']} секунд\n"
        f"- Запрещенные слова: {', '.join(settings['banned_words']) if settings['banned_words'] else 'Нет'}"
    )

    await query.message.reply_text(f"Правила группы:\n{rules}")

async def feedback(update: Update, context: CallbackContext):
    """Отображает обратную связь группы."""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[1])

    for msg in group_data.get(chat_id, {}).get("bot_messages", []):
        if msg["id"] == message_id:
            msg["path"] += "feedback/"
            print(f"Обновлен путь для сообщения {message_id}: {msg['path']}")
            break

    feedback_text = group_data[group_id].get("feedback", "Обратная связь не задана.")
    await query.message.reply_text(f"Обратная связь:\n{feedback_text}")

async def go_back(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id

    for msg in group_data.get(chat_id, {}).get("bot_messages", []):
        if msg["id"] == message_id and msg["path"] != "start/":
            path_parts = msg["path"].strip("/").split("/")
            print(f"Текущий путь: {msg['path']}")  # Отладка пути

            if len(path_parts) < 3:
                msg["path"] = "start/"
                print("Возврат к выбору роли")
                await query.edit_message_text(
                    "Выберите свою роль:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Администратор", callback_data="role_admin")],
                        [InlineKeyboardButton("Пользователь", callback_data="role_user")],
                    ])
                )
                return

            # Удаляем последний элемент пути
            msg["path"] = "/".join(path_parts[:-2]) + "/"
            print(f"Возврат назад, обновленный путь: {msg['path']}")

            # Получаем последний и предпоследний элементы пути
            last_step = path_parts[-2]
            prev_step = path_parts[-3] if len(path_parts) > 2 else ""

            if prev_step == "admin" or prev_step == "user":
                for group_id, data in group_data.items():
                    if data.get("group_name") == last_step:
                        break
                await group_details(update, context)
                return

            if last_step == "admin" or last_step == "user":
                for group_id, data in group_data.items():
                    if data.get("group_name") == path_parts[-1]:
                        break

                new_query = CallbackQuery(
                    id=query.id,
                    from_user=query.from_user,
                    message=query.message,
                    chat_instance=query.chat_instance,
                    data=f"role_{last_step}"
                )

                # Создание нового объекта Update, содержащего новый CallbackQuery
                fake_update = Update(update.update_id, callback_query=new_query)

                await role_handler(fake_update, context)

                return


            if last_step.isdigit() and int(last_step) in group_data:
                print("11111111111111111111111111111111111111111111111111111111111111111111111111111111")
                group_id = int(last_step)
                group_name = group_data[group_id]['group_name']

                keyboard = [
                    [InlineKeyboardButton("Просмотреть всех пользователей", callback_data=f"view_users_{group_id}")],
                    [InlineKeyboardButton("Настроить запрещенные слова", callback_data=f"set_banned_words_{group_id}")],
                    [InlineKeyboardButton("Настроить лимит сообщений", callback_data=f"set_max_messages_{group_id}")],
                    [InlineKeyboardButton("Назад", callback_data=f"go_back_{group_id}")],
                ]

                await query.message.reply_text(
                    f"Настройки группы {group_name}:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

            await query.edit_message_text("Ошибка: Некорректный идентификатор группы.")
            return

async def edit_message_if_needed(query, new_text, new_reply_markup):
    """Редактирует сообщение только если его содержимое или клавиатура изменились."""
    current_text = query.message.text
    current_reply_markup = query.message.reply_markup

    # Проверяем, изменились ли текст или разметка
    if current_text == new_text and current_reply_markup == new_reply_markup:
        return  # Ничего не делаем, если текст и клавиатура не изменились
    # Выполняем редактирование
    await query.edit_message_text(new_text, reply_markup=new_reply_markup)

async def group_details(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[2])

    for msg in group_data.get(chat_id, {}).get("bot_messages", []):
        if msg["id"] == message_id:
            msg["path"] += f"{group_data[group_id]['group_name']}/"
            print(f"Обновлен путь для сообщения {message_id}: {msg['path']}")
            break

    user_id = query.from_user.id
    user_data = group_data[group_id]['users'].get(user_id)

    if not user_data:
        await query.edit_message_text("Ошибка: Пользователь не найден в данных группы.")
        return

    role = 'admin' if user_data.get('status') in ['administrator', 'creator'] else 'user'

    if role == "admin":
        keyboard = [
            [InlineKeyboardButton("Управление пользователями", callback_data=f"user_management_{group_id}")],
            [InlineKeyboardButton("Фильтры и ограничения", callback_data=f"filters_limits_{group_id}")],
            [InlineKeyboardButton("Настройки капчи", callback_data=f"captcha_settings_{group_id}")],
            [InlineKeyboardButton("Настройки группы", callback_data=f"group_settings_{group_id}")],
            [InlineKeyboardButton("Назад", callback_data=f"go_back_{group_id}")],
        ]
    elif role == "user":
        keyboard = [
            [InlineKeyboardButton("Правила", callback_data=f"rules_{group_id}")],
            [InlineKeyboardButton("Обратная связь", callback_data=f"feedback_{group_id}")],
            [InlineKeyboardButton("Назад", callback_data="role_user")]
        ]
    else:
        await query.edit_message_text("Ошибка выбора группы.")
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Группа: {group_data[group_id]['group_name']}", reply_markup=reply_markup)

async def view_settings(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[-1])


    settings = group_data[group_id]
    response = (
        f"Настройки группы {settings['group_name']}:\n"
        f"🔸 Количество пользователей: {len(settings['users'])}:\n"
        f"🔸 Лимит сообщений в секунду: {settings['MAX_MESSAGES_PER_SECOND']}\n"
        f"🔸 Время временного мута: {settings['MUT_SECONDS']} секунд\n"
        f"🔸 Время жизни капчи: {settings.get('CAPTCHA_TIMEOUT', 3600)} секунд\n"
        f"🔸 Количество попыток капчи: {settings.get('CAPTCHA_ATTEMPTS', 5)}\n"
        f"🔸 ID группы с предупреждениями: {settings['SPECIAL_GROUP_ID']}\n"
        f"🔸 Запрещенные слова: {', '.join(settings['banned_words']) if settings['banned_words'] else 'Нет'}"
        f"🔸 Обратная связь: {settings['feedback']}\n"
        f"🔸 Правила:\n{settings['rules']}\n"
    )


    await query.message.reply_text(response)

async def user_management(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[-1])

    for msg in group_data.get(chat_id, {}).get("bot_messages", []):
        if msg["id"] == message_id:
            msg["path"] += "user_management/"
            print(f"Обновлен путь для сообщения {message_id}: {msg['path']}")
            break

    keyboard = [
        [InlineKeyboardButton("Просмотреть всех пользователей", callback_data=f"view_users_{group_id}")],
        [InlineKeyboardButton("Назад", callback_data=f"go_back_{group_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Управление пользователями:", reply_markup=reply_markup)

async def filters_limits(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[-1])

    for msg in group_data.get(chat_id, {}).get("bot_messages", []):
        if msg["id"] == message_id:
            msg["path"] += "filters_limits/"
            print(f"Обновлен путь для сообщения {message_id}: {msg['path']}")
            break

    keyboard = [
        [InlineKeyboardButton("Настроить запрещенные слова", callback_data=f"banned_words_{group_id}")],
        [InlineKeyboardButton("Настроить лимит сообщений в секунду", callback_data=f"set_max_messages_{group_id}")],
        [InlineKeyboardButton("Настроить временный мут", callback_data=f"set_mut_{group_id}")],
        [InlineKeyboardButton("Назад", callback_data=f"go_back_{group_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Фильтры и ограничения:", reply_markup=reply_markup)

async def captcha_settings(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[-1])

    for msg in group_data.get(chat_id, {}).get("bot_messages", []):
        if msg["id"] == message_id:
            msg["path"] += "captcha_settings/"
            print(f"Обновлен путь для сообщения {message_id}: {msg['path']}")
            break

    keyboard = [
        [InlineKeyboardButton("Изменить время жизни капчи", callback_data=f"set_captcha_timeout_{group_id}")],
        [InlineKeyboardButton("Изменить количество попыток капчи", callback_data=f"set_captcha_attempts_{group_id}")],
        [InlineKeyboardButton("Назад", callback_data=f"go_back_{group_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Настройки капчи:", reply_markup=reply_markup)




async def set_banned_words(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[2])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return


    context.user_data['current_group'] = group_id
    context.user_data['awaiting_banned_words'] = True
    await query.message.reply_text("Введите запрещенные слова через запятую с пробелом (, ):")

async def set_max_messages(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[3])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return


    context.user_data['current_group'] = group_id
    context.user_data['awaiting_max_messages'] = True
    await query.message.reply_text("Введите новый лимит сообщений в секунду:")

async def set_mut(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[2])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return


    context.user_data['current_group'] = group_id
    context.user_data['awaiting_mut'] = True
    await query.message.reply_text("Введите новое количество минут мута:")

async def set_warn_grup(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[3])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return


    context.user_data['current_group'] = group_id
    context.user_data['awaiting_warn_grup'] = True
    await query.message.reply_text("Введите новый id группы, его можно узнать например из бота @getmyid_bot")

async def set_captcha_timeout(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[3])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return


    context.user_data['current_group'] = group_id
    context.user_data['awaiting_captcha_timeout'] = True
    await query.message.reply_text("Введите новое время жизни капчи (в секундах):")

async def set_captcha_attempts(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[3])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    context.user_data['current_group'] = group_id
    context.user_data['awaiting_captcha_attempts'] = True
    await query.message.reply_text("Введите новое количество попыток для капчи:")

async def set_rules_attempts(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[3])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    context.user_data['current_group'] = group_id
    context.user_data['awaiting_rules_attempts'] = True
    await query.message.reply_text("Введите правила групы:")

async def set_feedback_attempts(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    group_id = int(query.data.split("_")[3])

    if group_id not in group_data:
        await query.message.reply_text("Группа не найдена.")
        return

    context.user_data['current_group'] = group_id
    context.user_data['awaiting_feedback_attempts'] = True
    await query.message.reply_text("Введите обратную связь для групы:")



async def save_banned_words(update: Update, context: CallbackContext):
    if not context.user_data.get('awaiting_banned_words'):
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id
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

async def save_max_messages(update: Update, context: CallbackContext):
    if not context.user_data.get('awaiting_max_messages'):
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    group_id = context.user_data.get('current_group')

    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    try:
        new_limit = int(update.message.text)
        if new_limit < 1:
            await update.message.reply_text("Лимит должен быть положительным числом.")
            return

        group_data[group_id]['MAX_MESSAGES_PER_SECOND'] = new_limit
        context.user_data['awaiting_max_messages'] = False


        await update.message.reply_text(
            f"Новый лимит сообщений в секунду для группы {group_data[group_id]['group_name']}: {new_limit}"
        )
    except ValueError:
        await update.message.reply_text("Пожалуйста, укажите корректное число.")

async def save_mut(update: Update, context: CallbackContext):
    if context.user_data.get('awaiting_mut', False):
        try:
            chat_id = update.effective_chat.id
            message_id = update.message.message_id
            input_text = update.message.text.strip()

            days, hours, minutes, seconds = 0, 0, 0, 0
            if input_text.isdigit():
                total_seconds = int(input_text)
            else:
                pattern = r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?'
                match = re.fullmatch(pattern, input_text)
                if match:
                    days = int(match.group(1) or 0)
                    hours = int(match.group(2) or 0)
                    minutes = int(match.group(3) or 0)
                    seconds = int(match.group(4) or 0)
                else:
                    raise ValueError("Неверный формат времени. Используйте формат '1d5h8m10s' или число секунд.")
                total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds

            group_id = context.user_data['current_group']
            group_data[group_id]['MUT_SECONDS'] = total_seconds
            context.user_data['awaiting_mut'] = False


            await update.message.reply_text(f"Время мута установлено на {total_seconds} секунд.")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {str(e)}. Попробуйте снова.")
    else:
        await update.message.reply_text("Неверный ввод. Попробуйте снова.")

async def save_warn_grup(update: Update, context: CallbackContext):
    if not context.user_data.get('awaiting_warn_grup'):
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    group_id = context.user_data.get('current_group')

    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    try:
        input_text = int(update.message.text)
        group_data[group_id]['SPECIAL_GROUP_ID'] = input_text
        context.user_data['awaiting_warn_grup'] = False


        await update.message.reply_text(f"Группа с банами и предупреждениями изменена на {input_text}.")
    except ValueError as e:
        await update.message.reply_text(f"Ошибка: {str(e)}. Попробуйте снова.")

async def save_captcha_timeout(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    group_id = context.user_data.get('current_group')

    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    try:
        timeout = int(update.message.text.strip())
        if timeout < 1:
            raise ValueError("Время должно быть положительным числом.")
        group_data[group_id]['CAPTCHA_TIMEOUT'] = timeout
        context.user_data['awaiting_captcha_timeout'] = False


        await update.message.reply_text(f"Время жизни капчи обновлено: {timeout} секунд.")
    except ValueError as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def save_captcha_attempts(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    group_id = context.user_data.get('current_group')

    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    try:
        attempts = int(update.message.text.strip())
        if attempts < 1:
            raise ValueError("Количество попыток должно быть больше нуля.")
        group_data[group_id]['CAPTCHA_ATTEMPTS'] = attempts
        context.user_data['awaiting_captcha_attempts'] = False


        await update.message.reply_text(f"Количество попыток капчи обновлено: {attempts}")
    except ValueError as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def save_rules_attempts(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    group_id = context.user_data.get('current_group')

    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    try:
        rules = update.message.text.strip()
        group_data[group_id]['rules'] = rules
        context.user_data['awaiting_rules_attempts'] = False


        await update.message.reply_text(f"Правила группы обновлено:\n {rules}")
    except ValueError as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def save_feedback_attempts(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    group_id = context.user_data.get('current_group')

    if not group_id or group_id not in group_data:
        await update.message.reply_text("Группа не найдена или не выбрана.")
        return

    try:
        feedback = update.message.text.strip()
        group_data[group_id]['feedback'] = feedback
        context.user_data['awaiting_feedback_attempts'] = False


        await update.message.reply_text(f"Обратная связь для группы обновлена:\n {feedback}")
    except ValueError as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def process_message(update: Update, context: CallbackContext):
    if context.user_data.get('awaiting_banned_words', False):
        print("0")
        await save_banned_words(update, context)
    elif context.user_data.get('awaiting_max_messages', False):
        print("00")
        await save_max_messages(update, context)
    elif context.user_data.get('awaiting_mut', False):
        print("000")
        await save_mut(update, context)
    elif context.user_data.get('awaiting_warn_grup', False):
        print("0000")
        await save_warn_grup(update, context)
    elif context.user_data.get('awaiting_captcha_timeout', False):
        print("00000")
        await save_captcha_timeout(update, context)
    elif context.user_data.get('awaiting_captcha_attempts', False):
        print("000000")
        await save_captcha_attempts(update, context)
    elif context.user_data.get('group_', False):
        print("0000000")
        await group_settings(update, context)
    elif context.user_data.get('banned_words_', False):
        print("00000000")
        await set_banned_words(update, context)
    elif context.user_data.get('view_users_', False):
        print("000000000")
        await view_users(update, context)
    elif context.user_data.get('awaiting_mut_', False):
        print("00000000000")
        await save_mut(update, context)
    elif context.user_data.get('awaiting_warn_grup', False):
        print("000000000000")
        await save_warn_grup(update, context)
    elif context.user_data.get('awaiting_rules_attempts', False):
        await save_rules_attempts(update, context)
        print("0000000000000")
    elif context.user_data.get('awaiting_feedback_attempts', False):
        await save_feedback_attempts(update, context)
        print("00000000000000")
    else:
        print("111-222")
        await handle_message(update, context)



async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_text = update.message.text

    if chat_id not in group_data:
        return

    MAX_MESSAGES_PER_SECOND = group_data[chat_id].get('MAX_MESSAGES_PER_SECOND', 10)
    user_message_timestamps = group_data[chat_id].get('user_message_timestamps', {})

    current_time = time.time()

    if user_id not in user_message_timestamps:
        user_message_timestamps[user_id] = []

    user_message_timestamps[user_id] = [timestamp for timestamp in user_message_timestamps[user_id] if current_time - timestamp < 1]

    user_message_timestamps[user_id].append(current_time)

    if len(user_message_timestamps[user_id]) > MAX_MESSAGES_PER_SECOND:
        await handle_spam(update, context, user_id)
        return

    banned_words = group_data[chat_id].get('banned_words', [])
    if any(word in message_text for word in banned_words):
        await check_message(update, context)

async def handle_spam(update: Update, context: CallbackContext, user_id: int):
    chat_id = update.effective_chat.id
    user_data = group_data[chat_id]['users'].get(user_id)
    MAX_MESSAGES_PER_SECOND = group_data[chat_id].get('MAX_MESSAGES_PER_SECOND', 10)
    MUT_SECONDS = group_data[chat_id]['MUT_SECONDS']
    SPECIAL_GROUP_ID = group_data[chat_id]['SPECIAL_GROUP_ID']

    if user_data:
        if user_data.get('muted', False):
            return

        until_date = datetime.now(timezone.utc) + timedelta(seconds=MUT_SECONDS)

        await update.message.chat.restrict_member(
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        await update.message.delete()

        await context.bot.send_message(
            user_id, text=f"{update.effective_user.first_name} Вы превысили лимит сообщений. Вам выдано предупреждение, и вы временно замучены на 1 минуту."
        )

        await context.bot.send_message(chat_id, text=f"Пользователь {update.effective_user.first_name} превысил лимит сообщений в секунду.")

        user_data['warnings'] += 1
        warnings_count = user_data['warnings']

        if warnings_count >= 5:
            user_data['banned'] = True

            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) был забанен за 5 предупреждений и спам.\n"
                f"(больше {MAX_MESSAGES_PER_SECOND} сообщений за секунду).\n"
                f"ID пользователя: {user_data.get('telegram_id', 'Не известен')}"
                f"#Ban\n"
                f"#Spam\n"
            )
            await context.bot.send_message(chat_id,f"Пользователь {user_data['name']} был забанен за 5 предупреждений.")
        else:
            violation_message = (
                f"Пользователь {update.effective_user.first_name} "
                f"(@{update.effective_user.username}) получил мут на 1 минуту за спам "
                f"(больше {MAX_MESSAGES_PER_SECOND} сообщений за секунду).\n"
                f"ID пользователя: {user_data.get('telegram_id', 'Не известен')}"
                f"#Spam"
            )

        await context.bot.send_message(SPECIAL_GROUP_ID, violation_message)

async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text

    user_data = group_data[chat_id]['users'][user_id]
    user_data['warnings'] += 1
    warnings_count = user_data['warnings']
    SPECIAL_GROUP_ID = group_data[chat_id]['SPECIAL_GROUP_ID']

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
            f"ID пользователя: {user_data.get('telegram_id', 'Не известен')}"
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
            f"ID пользователя: {user_data.get('telegram_id', 'Не известен')}"
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
        response += (f"Имя: {info['name']}\n"
                     f"Никнейм: {info['nickname']}\n"
                     f"ID: {user_id}\n"
                     f"ID: {info['telegram_id']}\n"
                     f"Замечания: {info['warnings']}\n"
                     f"Забанен: {info['banned']}\n\n")

    await query.edit_message_text(response)



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
                f"Забанен: {user_data['banned']}\n\n")
    await update.message.reply_text(response)


async def send_error_message(application: Application, error: str, group_name: str, update: Update = None):
    error_message = f"Ошибка в группе {group_name} (ссылка: https://t.me/c/{str(ERROR_GROUP_ID)[4:]})\n\nОшибка: {error}"

    if update and update.message:
        chat = update.effective_chat
        if chat.username:
            message_link = f"https://t.me/{chat.username}/{update.message.message_id}"
        else:
            message_link = f"https://t.me/c/{str(chat.id)[4:]}/{update.message.message_id}"
        error_message += f"\nСообщение, в котором произошла ошибка: {message_link}"

    await application.bot.send_message(ERROR_GROUP_ID, error_message)

async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mygroups", my_groups))
    application.add_handler(CommandHandler("userinfo", user_info))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("warn", warn_user))





    application.add_handler(CallbackQueryHandler(user_management, pattern="^user_management_"))
    application.add_handler(CallbackQueryHandler(filters_limits, pattern="^filters_limits_"))
    application.add_handler(CallbackQueryHandler(captcha_settings, pattern="^captcha_settings_"))
    application.add_handler(CallbackQueryHandler(view_settings, pattern="^view_settings_"))

    application.add_handler(CallbackQueryHandler(group_settings, pattern="^group_"))
    application.add_handler(CallbackQueryHandler(set_banned_words, pattern="^banned_words_"))
    application.add_handler(CallbackQueryHandler(view_users, pattern="^view_users_"))
    application.add_handler(CallbackQueryHandler(save_max_messages, pattern="^awaiting_max_messages"))
    application.add_handler(CallbackQueryHandler(save_mut, pattern="^awaiting_mut_"))
    application.add_handler(CallbackQueryHandler(save_warn_grup, pattern="^awaiting_warn_grup"))
    application.add_handler(CallbackQueryHandler(save_warn_grup, pattern="^awaiting_captcha_attempts"))
    application.add_handler(CallbackQueryHandler(save_rules_attempts , pattern="^awaiting_rules_attempts"))
    application.add_handler(CallbackQueryHandler(save_feedback_attempts , pattern="^awaiting_feedback_attempts"))



    application.add_handler(CallbackQueryHandler(group_settings, pattern="^group_settings_"))
    application.add_handler(CallbackQueryHandler(go_back, pattern="^go_back_"))
    application.add_handler(CallbackQueryHandler(role_handler, pattern="^role_"))
    application.add_handler(CallbackQueryHandler(group_details, pattern="^(admin|user)_group_"))
    application.add_handler(CallbackQueryHandler(rules, pattern="^rules_"))
    application.add_handler(CallbackQueryHandler(feedback, pattern="^feedback_"))

    application.add_handler(CallbackQueryHandler(set_banned_words, pattern="^set_banned_words_"))
    application.add_handler(CallbackQueryHandler(set_max_messages, pattern="^set_max_messages_"))
    application.add_handler(CallbackQueryHandler(set_mut, pattern="^set_mut_"))
    application.add_handler(CallbackQueryHandler(set_warn_grup, pattern="^set_warn_grup_"))
    application.add_handler(CallbackQueryHandler(set_captcha_timeout, pattern="^set_captcha_timeout_"))
    application.add_handler(CallbackQueryHandler(set_captcha_attempts, pattern="^set_captcha_attempts_"))
    application.add_handler(CallbackQueryHandler(set_rules_attempts, pattern="^set_rules_grup_"))
    application.add_handler(CallbackQueryHandler(set_feedback_attempts, pattern="^set_feedback_grup_"))

    application.add_handler(CallbackQueryHandler(captcha_callback, pattern="^captcha_"))

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

    application.add_handler(MessageHandler(filters.TEXT, process_message))

    try:
        await application.run_polling()
    except Exception as e:
        print("-------------------------------------------------------------------------------------------------")
        await send_error_message(application, str(e), "Guardian_Помилки", None)
        logging.error(f"Ошибка в main: {e}")



if __name__ == "__main__":
    asyncio.run(main())