"""Telegram-слой: меню, тексты, хендлеры команд и сообщений, сборка Application."""
import asyncio
import os

import telegramify_markdown
from litellm import completion
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from kiwi.config import GROQ_MODEL, DB_FILE, LOG_FILE, log
from kiwi.persona import build_messages
from kiwi.storage import (
    MODE_LABEL,
    add_turn,
    get_history,
    get_mode,
    set_mode,
    upsert_user,
    user_info_text,
)


def describe_user(u) -> str:
    if u is None:
        return "id=?"
    parts = [f"id={u.id}"]
    if u.username:
        parts.append(f"@{u.username}")
    name = " ".join(filter(None, [u.first_name, u.last_name]))
    if name:
        parts.append(name)
    flags = " ".join(filter(None, [u.language_code, "premium" if u.is_premium else ""]))
    if flags:
        parts.append(f"({flags})")
    return " ".join(parts)


# --- Меню ------------------------------------------------------------------
def menu_markup(mode: str) -> InlineKeyboardMarkup:
    mark = lambda m, label: ("✅ " + label) if mode == m else label
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(mark("utena", "💘 Влюблена в Утену"), callback_data="mode:utena")],
        [InlineKeyboardButton(mark("user", "💘 Влюблена в тебя"), callback_data="mode:user")],
    ])


MENU_TEXT = "Выбери, в кого я влюблена, м-м~ 💣"

# Команды бота (для нативного меню Telegram и текстового списка в /start).
COMMANDS = [
    BotCommand("start", "Привет и что я умею"),
    BotCommand("menu", "Выбрать, в кого я влюблена"),
    BotCommand("me", "Что я о тебе знаю"),
]

ABOUT_TEXT = (
    "Ну наконец-то! Я — *Киви Арага*, она же Леопард из Энормиты, самая яркая девочка "
    "с самой громкой взрывчаткой. Пиши мне что угодно — поболтаем, а я буду капризничать и "
    "требовать твоего внимания, как и положено~ 💣\n\n"
    "*Мои команды:*\n"
    + "\n".join(f"/{c.command} — {c.description}" for c in COMMANDS)
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    upsert_user(chat_id, update.effective_user)
    log.info("start | %s", describe_user(update.effective_user))
    await send_reply(update.message, ABOUT_TEXT)
    await update.message.reply_text(MENU_TEXT, reply_markup=menu_markup(get_mode(chat_id)))


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    upsert_user(chat_id, update.effective_user)
    log.info("me | %s", describe_user(update.effective_user))
    await send_reply(update.message, user_info_text(chat_id))


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    upsert_user(chat_id, update.effective_user)
    log.info("menu | %s", describe_user(update.effective_user))
    await update.message.reply_text(MENU_TEXT, reply_markup=menu_markup(get_mode(chat_id)))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat.id
    mode = query.data.split(":", 1)[1]
    upsert_user(chat_id, update.effective_user)
    set_mode(chat_id, mode)
    log.info("mode -> %s | %s", mode, describe_user(update.effective_user))
    await query.answer("Хорошо, как скажешь~")
    await query.edit_message_text(MENU_TEXT, reply_markup=menu_markup(mode))


# --- Диалог ----------------------------------------------------------------
async def send_reply(message, text: str) -> None:
    """Отправить ответ с рендерингом markdown. При кривой разметке — plain, чтобы ответ не потерять."""
    try:
        await message.reply_text(
            telegramify_markdown.markdownify(text), parse_mode="MarkdownV2"
        )
    except Exception:  # ponytail: сбой конвертации/парсинга -> plain fallback
        log.warning("MarkdownV2 send failed, fallback to plain", exc_info=True)
        await message.reply_text(text)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text
    upsert_user(chat_id, update.effective_user)
    log.info("message | %s | %r", describe_user(update.effective_user), text)
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        resp = await asyncio.to_thread(
            completion,
            model=GROQ_MODEL,
            messages=build_messages(get_mode(chat_id), get_history(chat_id), text),
        )
        reply = resp.choices[0].message.content
    except Exception:
        log.exception("LLM error | %s", describe_user(update.effective_user))
        await update.message.reply_text("Хм?! Что-то сломалось, и это не моя вина! Спроси ещё раз, живо.")
        return
    await send_reply(update.message, reply)
    add_turn(chat_id, text, reply)
    log.info("reply | %s | %d chars", describe_user(update.effective_user), len(reply))


async def post_init(app: Application) -> None:
    """Зарегистрировать команды — нативное меню Telegram (кнопка «Menu»)."""
    await app.bot.set_my_commands(COMMANDS)


def build_app() -> Application:
    app = (
        Application.builder()
        .token(os.environ["TELEGRAM_BOT_TOKEN"])
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^mode:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Kiwi bot started, model=%s, db=%s, log=%s", GROQ_MODEL, DB_FILE, LOG_FILE)
    return app
