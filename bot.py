"""
Telegram бот для отправки тестовых постбеков X-Partners.
Команды:
1. Тестовая регистрация
2. Тестовый депозит
"""
import asyncio
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
from admin_service import is_admin, is_owner, get_owner, is_approved, add_approved, can_request_access, log_request_access, get_users_with_access
from postback_service import (
    extract_clickid_from_redirect,
    extract_offer_id_from_url,
    extract_pid_from_url,
    get_offer_secure,
    get_offer_details,
    get_offer_links,
    send_postback,
    build_postback_urls_for_advertiser,
)
from postback_logger import log_postback

# Состояния для ConversationHandler
AWAITING_LINK = 1
AWAITING_OFFER_ID = 2
AWAITING_OFFER_PID = 3

# Текст кнопок (Reply Keyboard)
BTN_START = "🔄 Главное меню"
BTN_TESTING = "🧪 Тестирование"
BTN_CREATE_POSTBACKS = "📋 Создать постбеки"
BTN_GET_LINKS = "🔗 Получить ссылки"
BTN_HELP = "📖 Справка"
BTN_BACK = "⬅️ Назад"
CB_GOAL_PREFIX = "goal_pick_"
CB_GOAL_CANCEL = "goal_cancel"

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
        commands.append(BotCommand("users", "Список пользователей с доступом"))
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
        "🧪 Тестирование — отправить ссылку, затем обязательно выбрать goal оффера",
        "📋 Создать постбеки — сформировать URL постбеков по offer_id для передачи рекламодателю",
        "🔗 Получить ссылки — трекинг-ссылка и лендинги оффера для вебмастера",
        "📖 Справка — эта подсказка",
        "",
        "В начале нажмите кнопку «Главное меню» под полем ввода.",
        "",
        "*Команды:*",
        "/cancel — отмена текущей операции",
        "",
        "*Как отправить тестовый постбек:*",
        "1. Нажмите «Тестирование»",
        "2. Отправьте ссылку",
        "3. Выберите goal оффера (обязательно)",
    ]
    if is_approved(user_id):
        lines.append("/postback\\_url <offer\\_id> — то же, что кнопка «Создать постбеки»")
    if is_owner(user_id):
        lines.append("/status — проверка работы бота и сервисов")
        lines.append("/users — список пользователей с доступом к боту")
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


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /users — список пользователей с доступом к боту (только админ)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Эта команда доступна только администраторам.")
        return

    data = get_users_with_access()
    owner_id = data.get("owner")
    approved = data.get("approved", [])

    lines = ["👥 *Пользователи с доступом к боту*\n"]

    if owner_id:
        try:
            chat = await context.bot.get_chat(owner_id)
            name = chat.full_name or "—"
            username = f"@{chat.username}" if chat.username else "—"
            lines.append(f"*Владелец (админ):*\n  • ID: `{owner_id}`\n  • Имя: {name}\n  • Username: {username}\n")
        except Exception:
            lines.append(f"*Владелец (админ):* ID `{owner_id}`\n")
    else:
        lines.append("*Владелец:* не настроен\n")

    if approved:
        lines.append("*Одобренные пользователи:*")
        for uid in approved:
            try:
                chat = await context.bot.get_chat(uid)
                name = chat.full_name or "—"
                username = f"@{chat.username}" if chat.username else "—"
                lines.append(f"  • ID `{uid}` — {name} ({username})")
            except Exception:
                lines.append(f"  • ID `{uid}`")
    else:
        lines.append("*Одобренные пользователи:* нет")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
        "Рекламодатель подставляет свой click_id вместо `{{adv_click_id}}`.\n\n"
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


async def goal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора goal из inline-клавиатуры — отправка постбека."""
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_postback")
    if not pending:
        try:
            await query.edit_message_text(
                "⌛ Сессия устарела. Начните заново с кнопки «Тестовая регистрация» или «Тестовый депозит».",
            )
        except Exception:
            pass
        return

    data = query.data or ""

    if data == CB_GOAL_CANCEL:
        context.user_data.pop("pending_postback", None)
        try:
            await query.edit_message_text("❎ Отправка постбека отменена.")
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Выберите действие:",
                reply_markup=_menu_keyboard(),
            )
        except Exception:
            pass
        return

    if not data.startswith(CB_GOAL_PREFIX):
        return

    try:
        idx = int(data[len(CB_GOAL_PREFIX):])
    except ValueError:
        await query.edit_message_text("❌ Некорректный выбор цели.")
        context.user_data.pop("pending_postback", None)
        return

    goals = pending.get("goals") or []
    if idx < 0 or idx >= len(goals):
        await query.edit_message_text("❌ Цель не найдена. Начните заново.")
        context.user_data.pop("pending_postback", None)
        return

    goal_value = goals[idx].get("value") or ""
    goal_title = goals[idx].get("title") or goal_value
    click_id = pending.get("click_id", "")
    secure = pending.get("secure", "")
    pid = pending.get("pid", "")
    offer_id = pending.get("offer_id", "")
    # Бизнес-правило: registration => status=1, остальные goals => status=2
    status = 1 if goal_value.strip().lower() == "registration" else 2
    context.user_data.pop("pending_postback", None)

    try:
        await query.edit_message_text(
            f"⏳ Отправляю постбек с goal=`{goal_value}`...",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    success, message = await asyncio.to_thread(
        send_postback, click_id, secure, goal_value, status, pid
    )

    user = update.effective_user
    try:
        log_postback(
            success=success,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            click_id=click_id,
            offer_id=offer_id,
            pid=pid,
            goal=goal_value,
            status=status,
            error_message=None if success else message,
        )
    except Exception as e:
        logger.warning("Не удалось записать лог постбека: %s", e)

    if success:
        result_text = (
            f"🎉 {message}\n\n"
            f"📋 Детали:\n"
            f"• Goal: {goal_title} ({goal_value})\n"
            f"• Status: {status}\n"
            f"• ClickID: {click_id}\n"
            f"• Offer ID: {offer_id}\n"
            f"• Action ID: TEST_{pid or '0'}"
        )
    else:
        result_text = f"❌ {message}"

    try:
        await query.edit_message_text(result_text)
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=result_text,
            )
        except Exception:
            pass

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите действие:",
            reply_markup=_menu_keyboard(),
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
    """Клавиатура после нажатия «Главное меню» — 6 кнопок."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_TESTING)],
            [KeyboardButton(BTN_CREATE_POSTBACKS), KeyboardButton(BTN_GET_LINKS)],
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
        "Рекламодатель подставляет свой click_id вместо `{{adv_click_id}}`.\n\n"
        "*Регистрация:*\n`{}`\n\n"
        "*Депозит:*\n`{}`"
    ).format(offer_id, url_reg, url_dep)
    await update.message.reply_text(resp_text, parse_mode="Markdown", reply_markup=_menu_keyboard())
    return ConversationHandler.END


async def get_links_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Кнопка «Получить ссылки» — запрос offer_id и pid."""
    if not is_approved(update.effective_user.id):
        await update.message.reply_text(
            "⛔ Для использования бота необходимо получить доступ.",
            reply_markup=_menu_keyboard(),
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "Введите *offer_id* и *pid* через пробел.\n\n"
        "Пример: `1234 108`\n\n"
        "Или /cancel для отмены.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AWAITING_OFFER_PID


async def get_links_offer_pid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка введённых offer_id и pid для «Получить ссылки»."""
    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Введите два числа через пробел: offer_id pid\n"
            "Пример: 1234 108"
        )
        return AWAITING_OFFER_PID
    offer_id, pid = parts[0], parts[1]
    if not offer_id.isdigit() or not pid.isdigit():
        await update.message.reply_text("❌ Оба значения должны быть числами (offer_id pid).")
        return AWAITING_OFFER_PID

    await update.message.reply_text("⏳ Получаю ссылки")
    tracking_url, landings, error = await asyncio.to_thread(get_offer_links, offer_id, pid)
    if error:
        await update.message.reply_text(f"❌ {error}", reply_markup=_menu_keyboard())
        return ConversationHandler.END

    lines = [
        f"🔗 <b>Трекинг-ссылка</b> (offer_id={offer_id}, pid={pid}):",
        f"<code>{tracking_url}</code>",
        "",
    ]
    if landings:
        lines.append("📄 <b>Лендинги:</b>")
        for i, lnd in enumerate(landings, 1):
            title = (lnd.get("title") or f"Лендинг {i}").replace("<", "&lt;").replace(">", "&gt;")
            url = lnd.get("url") or lnd.get("url_preview") or "—"
            lines.append(f"{i}. {title}")
            lines.append(f"   <code>{url}</code>")
    else:
        lines.append("📄 <b>Лендинги:</b> нет")

    try:
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_menu_keyboard(),
        )
    except Exception as e:
        logger.exception("Ошибка при отправке ссылок")
        await update.message.reply_text(
            f"🔗 Трекинг-ссылка:\n{tracking_url}\n\n"
            + ("📄 Лендинги: нет" if not landings else "📄 Лендинги отправлены отдельно"),
            reply_markup=_menu_keyboard(),
        )
    return ConversationHandler.END


async def testing_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт тестирования: сразу запрашивает ссылку партнёра."""
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text(
            "⛔ Для использования бота необходимо получить доступ.\n\n"
            "Отправьте /request_access и дождитесь одобрения владельца.",
            reply_markup=_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📎 Отправьте аффилиатную ссылку партнера для тестирования.\n\n"
        "Бот отправит постбек.\n\n"
        "Или отправьте /cancel для отмены.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AWAITING_LINK


def _build_goals_keyboard(goals: list[dict]) -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру со списком целей оффера + кнопкой Отмена."""
    rows = []
    for i, g in enumerate(goals):
        title = g.get("title") or g.get("value") or f"Goal {i + 1}"
        value = g.get("value") or "—"
        label = f"{title} ({value})" if title != value else title
        if len(label) > 60:
            label = label[:57] + "..."
        rows.append([InlineKeyboardButton(label, callback_data=f"{CB_GOAL_PREFIX}{i}")])
    rows.append([InlineKeyboardButton("⬅️ Отмена", callback_data=CB_GOAL_CANCEL)])
    return InlineKeyboardMarkup(rows)


async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ссылки: click_id из редиректа, secure/goals из оффера, затем выбор цели."""
    try:
        link = (update.message.text or "").strip()
        if not link:
            await update.message.reply_text("❌ Пустое сообщение. Отправьте ссылку.")
            return AWAITING_LINK

        if not (link.startswith("http://") or link.startswith("https://")):
            await update.message.reply_text("❌ Пожалуйста, отправьте корректную ссылку (начинается с http:// или https://)")
            return AWAITING_LINK

        await update.message.reply_text("⏳ Обрабатываю ссылку...")

        # 1. Извлекаем click_id, offer_id и pid из редиректа партнёрской ссылки
        click_id, offer_id, pid, redirect_error = await asyncio.to_thread(
            extract_clickid_from_redirect, link
        )

        if redirect_error and not click_id:
            await update.message.reply_text(f"❌ {redirect_error}")
            return AWAITING_LINK

        if not offer_id:
            await update.message.reply_text(
                "❌ Не удалось определить offer_id из ссылки.\n"
                "Убедитесь, что ссылка содержит ID оффера (в пути или параметрах)."
            )
            return AWAITING_LINK

        if not click_id:
            await update.message.reply_text(f"❌ {redirect_error}")
            return AWAITING_LINK

        await update.message.reply_text(
            f"✅ ClickID: `{click_id}`\n✅ Offer ID: `{offer_id}`\n✅ PID: `{pid}`\n\n⏳ Получаю цели оффера...",
            parse_mode="Markdown"
        )

        # 2. Получаем secure и список целей оффера по offer_id (click_id сюда не относится)
        secure, goals, offer_error = await asyncio.to_thread(get_offer_details, offer_id)

        if not secure or not goals:
            await update.message.reply_text(
                f"❌ {offer_error or 'Не удалось получить данные оффера'}",
                reply_markup=_menu_keyboard(),
            )
            return ConversationHandler.END

        # 3. Сохраняем контекст и показываем пользователю выбор цели
        context.user_data["pending_postback"] = {
            "click_id": click_id,
            "secure": secure,
            "pid": pid or "",
            "offer_id": offer_id,
            "goals": goals,
        }

        await update.message.reply_text(
            "🎯 Выберите goal оффера для тестового постбека:",
            reply_markup=_build_goals_keyboard(goals),
        )

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
            MessageHandler(filters.Text([BTN_TESTING]), testing_start),
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

    conv_get_links = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([BTN_GET_LINKS]), get_links_start),
        ],
        states={
            AWAITING_OFFER_PID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_links_offer_pid),
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
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("postback_url", postback_url_command))
    application.add_handler(CommandHandler("request_access", request_access_command))
    application.add_handler(MessageHandler(filters.Text([BTN_START]), show_menu))
    application.add_handler(MessageHandler(filters.Text([BTN_HELP]), help_button_handler))
    application.add_handler(MessageHandler(filters.Text([BTN_BACK]), back_handler))
    application.add_handler(CallbackQueryHandler(access_callback, pattern="^access_"))
    application.add_handler(
        CallbackQueryHandler(
            goal_callback,
            pattern=f"^({CB_GOAL_PREFIX}|{CB_GOAL_CANCEL})",
        )
    )
    application.add_handler(conv_handler)
    application.add_handler(conv_create_postbacks)
    application.add_handler(conv_get_links)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
