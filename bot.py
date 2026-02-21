"""
Telegram бот для отправки тестовых постбеков X-Partners.
Команды:
1. Тестовая регистрация
2. Тестовый депозит
"""
import asyncio
import logging

# Исправление для Python 3.10+: создаём event loop до запуска бота
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
from telegram import BotCommand, BotCommandScopeChat, Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

import httpx

from config import TELEGRAM_BOT_TOKEN, AFFISE_API_URL, AFFISE_API_KEY, PROXY_URL, TRACKER_DOMAINS
from admin_service import is_admin, is_owner, get_owner, add_admin, remove_admin, list_admins
from postback_service import (
    extract_clickid_from_redirect,
    extract_offer_id_from_url,
    extract_pid_from_url,
    get_offer_secure,
    send_postback,
)

# Состояния для ConversationHandler
AWAITING_LINK = 1

# Текст кнопок (Reply Keyboard)
BTN_REG = "📝 Тестовая регистрация"
BTN_DEPOSIT = "💰 Тестовый депозит"
BTN_MENU = "📋 Меню"
CB_REG = "test_reg"
CB_DEPOSIT = "test_deposit"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def _set_commands_for_user(bot, user_id: int) -> None:
    """Устанавливает список команд в кнопке Меню для конкретного пользователя."""
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("help", "Справка"),
        BotCommand("cancel", "Отмена операции"),
    ]
    if is_admin(user_id):
        commands.append(BotCommand("status", "Статус сервисов"))
        commands.append(BotCommand("admins", "Список админов"))
    if is_owner(user_id):
        commands.append(BotCommand("addadmin", "Добавить админа"))
        commands.append(BotCommand("removeadmin", "Удалить админа"))
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception:
        pass


async def _set_default_commands(app: Application) -> None:
    """Устанавливает команды по умолчанию (для всех) при запуске бота."""
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("help", "Справка"),
        BotCommand("request_access", "Запросить доступ админа"),
        BotCommand("cancel", "Отмена операции"),
    ]
    await app.bot.set_my_commands(commands)


def _help_text(user_id: int) -> str:
    """Текст справки в зависимости от роли."""
    lines = [
        "📖 *Справка*\n",
        "*Команды:*",
        "/start — главное меню",
        "/help — эта справка",
        "/request\\_access — запросить доступ админа",
        "/cancel — отмена текущей операции",
    ]
    if is_admin(user_id):
        lines.append("/status — проверка работы бота и сервисов")
        lines.append("/admins — список админов")
    if is_owner(user_id):
        lines.append("/addadmin — добавить админа")
        lines.append("/removeadmin — удалить админа")
    lines.append("")
    lines.append("*Как пользоваться:*")
    lines.append("1. Нажмите кнопку «📝 Тестовая регистрация» или «💰 Тестовый депозит»")
    lines.append("2. Отправьте ссылку")
    lines.append("3. Бот пройдёт по редиректам, найдёт click\\_id, offer\\_id, pid и отправит постбек")
    return "\n".join(lines)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help — справка по командам (зависит от роли)."""
    await update.message.reply_text(
        _help_text(update.effective_user.id),
        parse_mode="Markdown",
        reply_markup=_main_keyboard(),
    )


async def _run_status(message, user_id: int) -> None:
    """Логика проверки статуса (общая для команды и меню)."""
    await message.reply_text("⏳ Проверяю сервисы...")
    lines = []
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{AFFISE_API_URL}/3.0/offers",
                headers={"API-Key": AFFISE_API_KEY},
                params={"limit": 1},
            )
        if resp.status_code == 200:
            lines.append("✅ Affise API — доступен")
        else:
            lines.append(f"⚠️ Affise API — HTTP {resp.status_code}")
    except Exception as e:
        lines.append(f"❌ Affise API — недоступен ({e})")
    if PROXY_URL:
        try:
            with httpx.Client(proxy=PROXY_URL, timeout=10) as client:
                resp = client.get("https://httpbin.org/ip")
            if resp.status_code == 200:
                ip = resp.json().get("origin", "?")
                lines.append(f"✅ Прокси — работает (IP: {ip})")
            else:
                lines.append(f"⚠️ Прокси — HTTP {resp.status_code}")
        except Exception as e:
            lines.append(f"❌ Прокси — недоступен ({e})")
    else:
        lines.append("ℹ️ Прокси — не настроен")
    lines.append(f"ℹ️ Домены трекеров: {', '.join(TRACKER_DOMAINS)}")
    await message.reply_text(
        "📊 *Статус сервисов*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /status — проверка доступности сервисов (только админ)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Эта команда доступна только администраторам.")
        return
    await _run_status(update.message, update.effective_user.id)


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /addadmin <user_id> — добавить админа (только owner)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Только владелец может добавлять админов.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /addadmin <user\\_id>", parse_mode="Markdown")
        return
    uid = int(context.args[0])
    if add_admin(uid):
        await update.message.reply_text(f"✅ Пользователь `{uid}` добавлен как админ.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ Пользователь `{uid}` уже является админом.", parse_mode="Markdown")


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /removeadmin <user_id> — удалить админа (только owner)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Только владелец может удалять админов.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /removeadmin <user\\_id>", parse_mode="Markdown")
        return
    uid = int(context.args[0])
    if remove_admin(uid):
        await update.message.reply_text(f"✅ Пользователь `{uid}` удалён из админов.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ Невозможно удалить (owner или не найден).", parse_mode="Markdown")


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /admins — показать список админов (только админ)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Эта команда доступна только администраторам.")
        return
    owner, admins = list_admins()
    lines = []
    for uid in admins:
        role = " (owner)" if uid == owner else ""
        lines.append(f"• `{uid}`{role}")
    text = "👥 *Администраторы:*\n\n" + "\n".join(lines) if lines else "Список админов пуст."
    await update.message.reply_text(text, parse_mode="Markdown")


async def request_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /request_access — запрос доступа админа."""
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text("ℹ️ Вы уже являетесь администратором.")
        return

    owner_id = get_owner()
    if not owner_id:
        await update.message.reply_text("❌ Владелец бота не настроен.")
        return

    name = user.full_name or "Без имени"
    username = f"@{user.username}" if user.username else "нет"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"access_approve_{user.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"access_reject_{user.id}"),
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=owner_id,
            text=(
                f"🔔 *Новая заявка на доступ*\n\n"
                f"Имя: {name}\n"
                f"Username: {username}\n"
                f"ID: `{user.id}`"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        await update.message.reply_text("✅ Заявка отправлена владельцу. Ожидайте подтверждения.")
    except Exception as e:
        logger.error(f"Не удалось отправить заявку owner: {e}")
        await update.message.reply_text("❌ Не удалось отправить заявку. Попробуйте позже.")


async def access_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка кнопок Одобрить/Отклонить заявки на доступ."""
    query = update.callback_query
    await query.answer()

    if not is_owner(update.effective_user.id):
        await query.answer("⛔ Только владелец может одобрять заявки.", show_alert=True)
        return

    data = query.data
    uid = int(data.split("_")[-1])

    if data.startswith("access_approve_"):
        if add_admin(uid):
            await query.edit_message_text(
                query.message.text + "\n\n✅ *Одобрено*",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="🎉 Ваша заявка одобрена! Теперь у вас есть права администратора.\nОтправьте /start для обновления меню.",
                )
                await _set_commands_for_user(context.bot, uid)
            except Exception:
                pass
        else:
            await query.edit_message_text(
                query.message.text + "\n\nℹ️ Уже является админом.",
                parse_mode="Markdown",
            )

    elif data.startswith("access_reject_"):
        await query.edit_message_text(
            query.message.text + "\n\n❌ *Отклонено*",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="😔 Ваша заявка на доступ отклонена.",
            )
        except Exception:
            pass


def _main_keyboard():
    """Клавиатура над полем ввода."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_REG), KeyboardButton(BTN_DEPOSIT)]],
        resize_keyboard=True,
    )


def _menu_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Inline-кнопки команд в зависимости от роли."""
    buttons = [
        [InlineKeyboardButton("📖 Справка", callback_data="cmd_help")],
    ]
    if is_admin(user_id):
        buttons.append([
            InlineKeyboardButton("📊 Статус сервисов", callback_data="cmd_status"),
            InlineKeyboardButton("👥 Список админов", callback_data="cmd_admins"),
        ])
    if is_owner(user_id):
        buttons.append([
            InlineKeyboardButton("➕ Добавить админа", callback_data="cmd_addadmin"),
            InlineKeyboardButton("➖ Удалить админа", callback_data="cmd_removeadmin"),
        ])
    return InlineKeyboardMarkup(buttons)


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка 'Меню' — показать доступные команды."""
    user_id = update.effective_user.id
    await update.message.reply_text(
        "📋 Выберите команду:",
        reply_markup=_menu_inline_keyboard(user_id),
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий inline-кнопок меню."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cmd_help":
        await query.message.reply_text(
            _help_text(update.effective_user.id),
            parse_mode="Markdown",
        )
    elif data == "cmd_status":
        if not is_admin(update.effective_user.id):
            await query.message.reply_text("⛔ Нет доступа.")
            return
        context.user_data["_from_menu"] = True
        fake_update = update
        fake_update._effective_message = query.message
        await _run_status(query.message, update.effective_user.id)
    elif data == "cmd_admins":
        if not is_admin(update.effective_user.id):
            await query.message.reply_text("⛔ Нет доступа.")
            return
        owner, admins_list = list_admins()
        lines = []
        for uid in admins_list:
            role = " (owner)" if uid == owner else ""
            lines.append(f"• `{uid}`{role}")
        text = "👥 *Администраторы:*\n\n" + "\n".join(lines) if lines else "Список админов пуст."
        await query.message.reply_text(text, parse_mode="Markdown")
    elif data == "cmd_addadmin":
        if not is_owner(update.effective_user.id):
            await query.message.reply_text("⛔ Нет доступа.")
            return
        await query.message.reply_text("Отправьте команду:\n/addadmin <user\\_id>", parse_mode="Markdown")
    elif data == "cmd_removeadmin":
        if not is_owner(update.effective_user.id):
            await query.message.reply_text("⛔ Нет доступа.")
            return
        await query.message.reply_text("Отправьте команду:\n/removeadmin <user\\_id>", parse_mode="Markdown")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start - приветствие и кнопки над полем ввода."""
    user_id = update.effective_user.id
    await _set_commands_for_user(context.bot, user_id)
    await update.message.reply_text(
        "👋 Привет! Это бот для тестирования X-Partners!\n\n"
        "Выберите действие:",
        reply_markup=_main_keyboard(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка нажатия кнопки (текст сообщения) - запрос ссылки."""
    text = (update.message.text or "").strip()
    context.user_data["action"] = CB_REG if text == BTN_REG else CB_DEPOSIT
    action_name = "тестовой регистрации" if text == BTN_REG else "тестового депозита"
    
    await update.message.reply_text(
        f"📎 Отправьте аффилиатную ссылку партнера для {action_name}.\n\n"
        "Бот отправит постбек.\n\n"
        "Или отправьте /cancel для отмены.",
        reply_markup=ReplyKeyboardRemove(),
    )
    
    return AWAITING_LINK


async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка полученной ссылки - извлечение clickid, получение secure, отправка постбека."""
    try:
        link = (update.message.text or "").strip()
        if not link:
            await update.message.reply_text("❌ Пустое сообщение. Отправьте ссылку.")
            return AWAITING_LINK

        action = context.user_data.get("action", CB_REG)

        # Проверяем, что это похоже на URL
        if not (link.startswith("http://") or link.startswith("https://")):
            await update.message.reply_text("❌ Пожалуйста, отправьте корректную ссылку (начинается с http:// или https://)")
            return AWAITING_LINK

        await update.message.reply_text("⏳ Обрабатываю ссылку...")

        # 1. Извлекаем clickid, offer_id и pid из редиректа
        clickid, offer_id, pid, error = extract_clickid_from_redirect(link)

        if error and not clickid:
            await update.message.reply_text(f"❌ {error}")
            return AWAITING_LINK

        if not offer_id:
            await update.message.reply_text(
                "❌ Не удалось определить offer_id из ссылки.\n"
                "Убедитесь, что ссылка содержит ID оффера (в пути или параметрах)."
            )
            return AWAITING_LINK

        if not clickid:
            await update.message.reply_text(f"❌ {error}")
            return AWAITING_LINK

        await update.message.reply_text(
            f"✅ ClickID: `{clickid}`\n✅ Offer ID: `{offer_id}`\n✅ PID: `{pid}`\n\n⏳ Секунду...",
            parse_mode="Markdown"
        )

        # 2. Получаем secure из Affise API
        secure, error = get_offer_secure(offer_id)

        if not secure:
            await update.message.reply_text(f"❌ {error}")
            return AWAITING_LINK

        # 3. Отправляем постбекf
        if action == CB_REG:
            goal = "registration"
            status = 1
        else:
            goal = "deposit"
            status = 2

        success, message = send_postback(clickid, secure, goal, status, pid)

        keyboard = _main_keyboard()
        if success:
            await update.message.reply_text(
                f"🎉 {message}\n\n"
                f"📋 Детали:\n"
                f"• Goal: {goal}\n"
                f"• Status: {status}\n"
                f"• ClickID: {clickid}\n"
                f"• Action ID: TEST_{pid}",
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_text(f"❌ {message}", reply_markup=keyboard)

        return ConversationHandler.END

    except Exception as e:
        logger.exception("Ошибка при обработке ссылки")
        await update.message.reply_text(
            f"❌ Произошла ошибка: {str(e)}\n\nПопробуйте /start и отправьте ссылку снова.",
            reply_markup=_main_keyboard(),
        )
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена операции."""
    await update.message.reply_text("Операция отменена.", reply_markup=_main_keyboard())
    return ConversationHandler.END


async def start_in_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Команда /start во время диалога - возврат в главное меню."""
    await start(update, context)
    return ConversationHandler.END


def main() -> None:
    """Запуск бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_set_default_commands).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([BTN_REG, BTN_DEPOSIT]), button_handler),
        ],
        states={
            AWAITING_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_link),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_in_conversation),
        ],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("addadmin", addadmin_command))
    application.add_handler(CommandHandler("removeadmin", removeadmin_command))
    application.add_handler(CommandHandler("admins", admins_command))
    application.add_handler(CommandHandler("request_access", request_access_command))
    application.add_handler(MessageHandler(filters.Text([BTN_MENU]), menu_handler))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^cmd_"))
    application.add_handler(CallbackQueryHandler(access_callback, pattern="^access_"))
    application.add_handler(conv_handler)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
