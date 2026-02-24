"""
Telegram бот для отправки тестовых постбеков X-Partners.
Команды:
1. Тестовая регистрация
2. Тестовый депозит
"""
import logging

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
from admin_service import is_admin, is_owner, get_owner, is_approved, add_approved, can_request_access, log_request_access
from postback_service import (
    extract_clickid_from_redirect,
    extract_offer_id_from_url,
    extract_pid_from_url,
    get_offer_secure,
    send_postback,
    build_postback_urls_for_advertiser,
)
from postback_logger import log_postback

# Состояния для ConversationHandler
AWAITING_LINK = 1
AWAITING_OFFER_ID = 2

# Текст кнопок (Reply Keyboard)
BTN_START = "🔄 Главное меню"
BTN_REG = "📝 Тестовая регистрация"
BTN_DEPOSIT = "💰 Тестовый депозит"
BTN_CREATE_POSTBACKS = "📋 Создать постбеки"
BTN_HELP = "📖 Справка"
BTN_BACK = "⬅️ Назад"
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
        BotCommand("help", "Справка"),
        BotCommand("cancel", "Отмена операции"),
    ]
    if is_approved(user_id):
        commands.append(BotCommand("postback_url", "URL постбеков для рекламодателя"))
    if is_owner(user_id):
        commands.append(BotCommand("status", "Статус сервисов"))
    if not is_approved(user_id):
        commands.append(BotCommand("request_access", "Запросить доступ"))
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception:
        pass


async def _set_default_commands(app: Application) -> None:
    """Устанавливает команды по умолчанию (для всех) при запуске бота."""
    commands = [
        BotCommand("help", "Справка"),
        BotCommand("request_access", "Запросить доступ"),
        BotCommand("cancel", "Отмена операции"),
    ]
    await app.bot.set_my_commands(commands)


def _help_text(user_id: int) -> str:
    """Текст справки в зависимости от роли."""
    lines = [
        "📖 *Справка*\n",
        "*Бот:* тестирование постбеков X-Partners и формирование URL постбеков для рекламодателей.",
        "",
        "*Кнопки:*",
        "📝 Тестовая регистрация — отправить тестовый постбек (goal=registration, status=1)",
        "💰 Тестовый депозит — отправить тестовый постбек (goal=deposit, status=2)",
        "📋 Создать постбеки — сформировать URL постбеков по offer_id для передачи рекламодателю",
        "📖 Справка — эта подсказка",
        "",
        "В начале нажмите кнопку «Главное меню» под полем ввода.",
        "",
        "*Команды:*",
        "/cancel — отмена текущей операции",
        "",
        "*Как отправить тестовый постбек:*",
        "1. Нажмите «Тестовая регистрация» или «Тестовый депозит»",
        "2. Отправьте ссылку",
    ]
    if is_approved(user_id):
        lines.append("/postback\\_url <offer\\_id> — то же, что кнопка «Создать постбеки»")
    if is_owner(user_id):
        lines.append("/status — проверка работы бота и сервисов")
    if not is_approved(user_id):
        lines.append("/request\\_access — запросить доступ к боту")
    return "\n".join(lines)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help — справка по командам (зависит от роли)."""
    await update.message.reply_text(
        _help_text(update.effective_user.id),
        parse_mode="Markdown",
        reply_markup=_menu_keyboard(),
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


async def postback_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /postback_url <offer_id> — выдать URL постбеков для рекламодателя (clickid={adv_click_id})."""
    if not is_approved(update.effective_user.id):
        await update.message.reply_text("⛔ Для использования бота необходимо получить доступ.")
        return
    if not context.args or not context.args[0].strip():
        await update.message.reply_text(
            "Использование: /postback_url <offer_id>\n\nПример: /postback_url 4837",
            parse_mode="Markdown",
        )
        return
    offer_id = context.args[0].strip()
    if not offer_id.isdigit():
        await update.message.reply_text("❌ offer_id должен быть числом.")
        return
    await update.message.reply_text("⏳ Получаю secure по API...")
    url_reg, url_dep, error = build_postback_urls_for_advertiser(offer_id, pid="108")
    if error:
        await update.message.reply_text(f"❌ {error}")
        return
    text = (
        "📋 *Постбеки для рекламодателя* (offer_id={})\n\n"
        "Рекламодатель подставляет: свой click_id вместо `{{adv_click_id}}`, id заявки/юзера вместо `{{id_заявки_id_юзера}}`.\n\n"
        "*Регистрация:*\n`{}`\n\n"
        "*Депозит:*\n`{}`"
    ).format(offer_id, url_reg, url_dep)
    await update.message.reply_text(text, parse_mode="Markdown")


async def request_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /request_access — запрос доступа к боту."""
    user = update.effective_user
    if is_approved(user.id):
        await update.message.reply_text("ℹ️ У вас уже есть доступ к боту.")
        return

    can_request, used = can_request_access(user.id)
    if not can_request:
        await update.message.reply_text(
            f"⛔ Лимит запросов исчерпан (3 в день). Использовано сегодня: {used}. Попробуйте завтра.",
        )
        return

    owner_id = get_owner()
    if not owner_id:
        await update.message.reply_text("❌ Владелец бота не настроен.")
        return

    log_request_access(user.id)

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
        if add_approved(uid):
            await query.edit_message_text(
                query.message.text + "\n\n✅ *Одобрено*",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="🎉 Ваша заявка одобрена! Теперь вы можете использовать бота.\nОтправьте /start для обновления меню.",
                )
                await _set_commands_for_user(context.bot, uid)
            except Exception:
                pass
        else:
            await query.edit_message_text(
                query.message.text + "\n\nℹ️ Уже одобрен.",
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


def _entry_keyboard():
    """Клавиатура после /start — только «Главное меню»."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_START)]],
        resize_keyboard=True,
    )


def _menu_keyboard():
    """Клавиатура после нажатия «Главное меню» — 5 кнопок."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_REG), KeyboardButton(BTN_DEPOSIT)],
            [KeyboardButton(BTN_CREATE_POSTBACKS)],
            [KeyboardButton(BTN_HELP)],
            [KeyboardButton(BTN_BACK)],
        ],
        resize_keyboard=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start — приветствие и кнопка «Главное меню»."""
    user_id = update.effective_user.id
    await _set_commands_for_user(context.bot, user_id)
    await update.message.reply_text(
        "👋 Привет! Это бот для тестирования X-Partners.\n\n"
        "Нажмите «Главное меню», чтобы продолжить.",
        reply_markup=_entry_keyboard(),
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать меню с кнопками (после нажатия «Главное меню»)."""
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=_menu_keyboard(),
    )


async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка «Назад» — вернуться на экран с кнопкой «Главное меню»."""
    await update.message.reply_text(
        "Нажмите «Главное меню», чтобы продолжить.",
        reply_markup=_entry_keyboard(),
    )


async def back_handler_and_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """«Назад» во время диалога — вернуться на главный экран и завершить диалог."""
    await back_handler(update, context)
    return ConversationHandler.END


async def show_menu_and_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню и завершить диалог (для fallback в ConversationHandler)."""
    await show_menu(update, context)
    return ConversationHandler.END


async def help_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка «Справка» — краткая информация по командам и боту."""
    await update.message.reply_text(
        _help_text(update.effective_user.id),
        parse_mode="Markdown",
        reply_markup=_menu_keyboard(),
    )


async def create_postbacks_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Кнопка «Создать постбеки» — запрос offer_id."""
    if not is_approved(update.effective_user.id):
        await update.message.reply_text(
            "⛔ Для использования бота необходимо получить доступ.",
            reply_markup=_menu_keyboard(),
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "Введите offer_id (число):\n\nИли /cancel для отмены.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AWAITING_OFFER_ID


async def create_postbacks_offer_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка введённого offer_id для «Создать постбеки»."""
    text = (update.message.text or "").strip()
    if not text or not text.isdigit():
        await update.message.reply_text("❌ Введите число (offer_id).")
        return AWAITING_OFFER_ID
    offer_id = text
    await update.message.reply_text("⏳ Получаю secure по API...")
    url_reg, url_dep, error = build_postback_urls_for_advertiser(offer_id, pid="108")
    if error:
        await update.message.reply_text(f"❌ {error}", reply_markup=_menu_keyboard())
        return ConversationHandler.END
    resp_text = (
        "📋 *Постбеки для рекламодателя* (offer_id={})\n\n"
        "Рекламодатель подставляет: свой click_id вместо `{{adv_click_id}}`, id заявки/юзера вместо `{{id_заявки_id_юзера}}`.\n\n"
        "*Регистрация:*\n`{}`\n\n"
        "*Депозит:*\n`{}`"
    ).format(offer_id, url_reg, url_dep)
    await update.message.reply_text(resp_text, parse_mode="Markdown", reply_markup=_menu_keyboard())
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка нажатия кнопки (текст сообщения) - запрос ссылки."""
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text(
            "⛔ Для использования бота необходимо получить доступ.\n\n"
            "Отправьте /request_access и дождитесь одобрения владельца.",
            reply_markup=_menu_keyboard(),
        )
        return ConversationHandler.END

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

        user = update.effective_user
        try:
            log_postback(
                success=success,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                click_id=clickid,
                offer_id=offer_id,
                pid=pid,
                goal=goal,
                status=status,
                error_message=None if success else message,
            )
        except Exception as e:
            logger.warning("Не удалось записать лог постбека: %s", e)

        keyboard = _menu_keyboard()
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
            reply_markup=_menu_keyboard(),
        )
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена операции."""
    await update.message.reply_text("Операция отменена.", reply_markup=_menu_keyboard())
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
            MessageHandler(filters.Text([BTN_START]), show_menu_and_end),
            MessageHandler(filters.Text([BTN_BACK]), back_handler_and_end),
        ],
    )

    conv_create_postbacks = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([BTN_CREATE_POSTBACKS]), create_postbacks_start),
        ],
        states={
            AWAITING_OFFER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_postbacks_offer_id),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_in_conversation),
            MessageHandler(filters.Text([BTN_START]), show_menu_and_end),
            MessageHandler(filters.Text([BTN_BACK]), back_handler_and_end),
        ],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("postback_url", postback_url_command))
    application.add_handler(CommandHandler("request_access", request_access_command))
    application.add_handler(MessageHandler(filters.Text([BTN_START]), show_menu))
    application.add_handler(MessageHandler(filters.Text([BTN_HELP]), help_button_handler))
    application.add_handler(MessageHandler(filters.Text([BTN_BACK]), back_handler))
    application.add_handler(CallbackQueryHandler(access_callback, pattern="^access_"))
    application.add_handler(conv_handler)
    application.add_handler(conv_create_postbacks)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
