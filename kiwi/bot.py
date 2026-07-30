"""Telegram-слой: меню, тексты, хендлеры команд и сообщений, сборка Application."""
import asyncio
import base64
import contextlib
import os
import time

import telegramify_markdown
from litellm import completion, transcription
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

from kiwi.config import (
    DB_FILE,
    GROQ_MODEL,
    GROQ_STT_MODEL,
    GROQ_VISION_MODEL,
    LLM_TIMEOUT,
    LOG_FILE,
    MAX_INPUT,
    MAX_VOICE_SEC,
    RATE_LIMIT,
    RATE_WINDOW,
    SUMMARY_EVERY,
    log,
)
from kiwi.persona import build_messages, summary_messages
from kiwi.ratelimit import allow
from kiwi.storage import (
    add_turn,
    clear_history,
    count_user_messages,
    get_history,
    get_mode,
    get_summary,
    is_enabled,
    set_enabled,
    set_mode,
    set_summary,
    upsert_user,
    user_info_text,
)


def describe_user(u) -> str:
    """Компактный идентификатор для логов. Имя/язык/premium — PII, в логи не пишем;
    при нужде ищутся в БД по id. Публичный @username оставляем для отладки."""
    if u is None:
        return "id=?"
    return f"id={u.id}" + (f" @{u.username}" if u.username else "")


# --- Меню ------------------------------------------------------------------
def menu_markup(mode: str) -> InlineKeyboardMarkup:
    def mark(m, label):
        return ("✅ " + label) if mode == m else label

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
    BotCommand("reset", "Забыть наш разговор"),
]

ABOUT_TEXT = (
    "Ну наконец-то! Я — *Киви Арага*, она же Леопард из Энормиты, самая яркая девочка "
    "с самой громкой взрывчаткой и самой большой армией подписчиков. Пиши мне что угодно — "
    "поболтаем, а я буду капризничать и требовать твоего внимания, как и положено~ 💣\n\n"
    "*Мои команды:*\n"
    + "\n".join(f"/{c.command} — {c.description}" for c in COMMANDS)
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    log.info("start | %s", describe_user(update.effective_user))
    if is_group(update.effective_chat):
        await send_reply(update.message, ABOUT_TEXT)
        await update.message.reply_text(
            "Чтобы я болтала в этой группе, админ пусть напишет /enable. "
            "А по душам — пиши мне в личку~ 💣"
        )
        return
    upsert_user(chat_id, update.effective_user)
    await send_reply(update.message, ABOUT_TEXT)
    await update.message.reply_text(MENU_TEXT, reply_markup=menu_markup(get_mode(chat_id)))


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if is_group(update.effective_chat):
        await update.message.reply_text(PRIVATE_ONLY)
        return
    upsert_user(chat_id, update.effective_user)
    log.info("me | %s", describe_user(update.effective_user))
    await send_reply(update.message, user_info_text(chat_id))


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if is_group(update.effective_chat):
        await update.message.reply_text(PRIVATE_ONLY)
        return
    upsert_user(chat_id, update.effective_user)
    log.info("menu | %s", describe_user(update.effective_user))
    await update.message.reply_text(MENU_TEXT, reply_markup=menu_markup(get_mode(chat_id)))


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if is_group(update.effective_chat):
        await update.message.reply_text(PRIVATE_ONLY)
        return
    upsert_user(chat_id, update.effective_user)
    clear_history(chat_id)
    log.info("reset | %s", describe_user(update.effective_user))
    await update.message.reply_text("Всё, забыла. Начнём заново~ 💣")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat.id
    mode = query.data.split(":", 1)[1]
    upsert_user(chat_id, update.effective_user)
    set_mode(chat_id, mode)
    log.info("mode -> %s | %s", mode, describe_user(update.effective_user))
    await query.answer("Хорошо, как скажешь~")
    await query.edit_message_text(MENU_TEXT, reply_markup=menu_markup(mode))


# --- Группы ----------------------------------------------------------------
PRIVATE_ONLY = "Это только для лички~ Приходи поболтать со мной наедине! 💣"


def is_group(chat) -> bool:
    return chat.type in ("group", "supergroup")


def speaker(u) -> str:
    """Имя автора для подписи реплики в групповой истории."""
    return (u and (u.first_name or u.username)) or "кто-то"


def addressed_to_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """В группе Киви реагирует только на упоминание @bot или reply на её сообщение."""
    msg = update.message
    replied = msg.reply_to_message
    if replied and replied.from_user and replied.from_user.id == context.bot.id:
        return True
    mention = f"@{context.bot.username}".lower()
    return mention in (msg.text or msg.caption or "").lower()  # текст или подпись к фото


async def is_group_admin(update: Update) -> bool:
    admins = await update.effective_chat.get_administrators()
    return update.effective_user.id in {a.user.id for a in admins}


async def group_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True, если Киви должна отвечать: личка — всегда; группа — если включена админом и к ней обращаются."""
    chat = update.effective_chat
    if not is_group(chat):
        return True
    return is_enabled(chat.id) and addressed_to_bot(update, context)


async def cmd_enable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not is_group(chat):
        await update.message.reply_text("Мы и так наедине, глупенький~ Тут я всегда с тобой. 💣")
        return
    if not await is_group_admin(update):
        await update.message.reply_text("Не-а! Только админ группы может меня сюда позвать.")
        return
    set_enabled(chat.id, True)
    log.info("enabled | chat=%s | %s", chat.id, describe_user(update.effective_user))
    await update.message.reply_text(
        f"Ну наконец-то позвали! Теперь я тут~ 💣 Тегай меня @{context.bot.username} "
        "или отвечай на мои сообщения."
    )


async def cmd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not is_group(chat):
        await update.message.reply_text("А тут меня и не выключить~ Никуда я не денусь. 💣")
        return
    if not await is_group_admin(update):
        await update.message.reply_text("Не-а! Только админ группы тут распоряжается.")
        return
    set_enabled(chat.id, False)
    log.info("disabled | chat=%s | %s", chat.id, describe_user(update.effective_user))
    await update.message.reply_text("Фу, ну и ладно! Умолкаю. Позовёте /enable — вернусь. 💣")


# --- Диалог ----------------------------------------------------------------
def clip(text: str, limit: int = 500) -> str:
    """Жёсткий потолок на ответ LLM: обрезать до limit по границе предложения/слова + '…'."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit - 1]  # -1 под '…'
    cut = max(head.rfind(c) for c in ".!?~")
    if cut >= limit * 0.6:  # граница предложения близко к концу — режем по ней
        return head[: cut + 1].rstrip() + "…"
    sp = head.rfind(" ")  # иначе по последнему слову, чтобы не рвать посреди
    return head[: sp if sp > 0 else len(head)].rstrip() + "…"


async def send_reply(message, text: str) -> None:
    """Отправить ответ с рендерингом markdown. При кривой разметке — plain, чтобы ответ не потерять."""
    try:
        await message.reply_text(
            telegramify_markdown.markdownify(text), parse_mode="MarkdownV2"
        )
    except Exception:  # ponytail: сбой конвертации/парсинга -> plain fallback
        log.warning("MarkdownV2 send failed, fallback to plain", exc_info=True)
        await message.reply_text(text)


async def rate_ok(update: Update, chat_id: int) -> bool:
    """False + ответ пользователю, если превышен лимит обращений (до дорогих вызовов).
    В группе лимит per-user — иначе один флудер молчал бы всю комнату."""
    key = (chat_id, update.effective_user.id) if is_group(update.effective_chat) else chat_id
    if allow(key, time.monotonic(), RATE_LIMIT, RATE_WINDOW):
        return True
    log.info("rate limited | %s", describe_user(update.effective_user))
    await update.message.reply_text("Эй, не тараторь! Дай отдышаться~ 💣")
    return False


@contextlib.asynccontextmanager
async def typing(chat):
    """Держит статус «печатает…» пока идёт долгий вызов (LLM/STT): Telegram гасит его через ~5с."""
    async def loop():
        while True:
            await chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(4)
    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()


async def respond(update: Update, chat_id: int, text: str,
                  image_url: str | None = None, model: str = GROQ_MODEL) -> None:
    """LLM-ответ на текст (+картинку для vision) и сохранение хода. Rate limit проверяет вызывающий."""
    if len(text) > MAX_INPUT:
        log.info("too long (%d) | %s", len(text), describe_user(update.effective_user))
        await update.message.reply_text(
            f"Э-э, куда столько?! Я такие простыни не читаю — не больше {MAX_INPUT} символов за раз. "
            "Это сообщение я пропускаю, сократи и давай заново~ 💣"
        )
        return  # в историю не попадает
    group = is_group(update.effective_chat)  # в группе досье не ведём — оно смешивало бы участников
    try:
        async with typing(update.effective_chat):
            resp = await asyncio.to_thread(
                completion,
                model=model,
                messages=build_messages(
                    get_mode(chat_id), get_history(chat_id), text,
                    None if group else get_summary(chat_id), group=group, image_url=image_url,
                ),
                timeout=LLM_TIMEOUT,
            )
        reply = clip(resp.choices[0].message.content or "")
    except Exception:
        log.exception("LLM error | %s", describe_user(update.effective_user))
        await update.message.reply_text("Хм?! Что-то сломалось, и это не моя вина! Спроси ещё раз, живо.")
        return
    if not reply:
        log.warning("empty LLM reply | %s", describe_user(update.effective_user))
        await update.message.reply_text("Хм?! У меня слова кончились. Спроси как-нибудь иначе~")
        return  # в историю не пишем
    await send_reply(update.message, reply)
    add_turn(chat_id, text, reply)
    log.info("reply | %s | %d chars", describe_user(update.effective_user), len(reply))
    if not group:
        await maybe_summarize(update, chat_id)


async def maybe_summarize(update: Update, chat_id: int) -> None:
    """Каждые SUMMARY_EVERY ходов пользователя обновить досье о нём (старое + свежие ходы)."""
    n = count_user_messages(chat_id)
    if n == 0 or n % SUMMARY_EVERY != 0:
        return
    try:
        history = get_history(chat_id, SUMMARY_EVERY * 2)  # ровно ходы с прошлого досье (2 строки/ход)
        resp = await asyncio.to_thread(
            completion,
            model=GROQ_MODEL,
            messages=summary_messages(get_summary(chat_id), history),
            timeout=LLM_TIMEOUT,
        )
        set_summary(chat_id, resp.choices[0].message.content.strip())
        log.info("summary updated | %s | after %d msgs", describe_user(update.effective_user), n)
    except Exception:  # ponytail: досье — не критичный путь, ошибку глотаем, ответ уже ушёл
        log.exception("summary error | %s", describe_user(update.effective_user))


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    chat_id = chat.id
    if not await group_gate(update, context):
        return
    text = update.message.text
    if is_group(chat):  # в группе профиль не ведём — история общая, реплики подписываем автором
        text = f"[{speaker(update.effective_user)}] {text}"
    else:
        upsert_user(chat_id, update.effective_user)
    log.info("message | %s | %d chars", describe_user(update.effective_user), len(text))
    log.debug("message text | %s | %r", describe_user(update.effective_user), text)
    if not await rate_ok(update, chat_id):
        return
    await respond(update, chat_id, text)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    chat_id = chat.id
    if not await group_gate(update, context):  # в группе голос ловим только как reply на бота
        return
    if not is_group(chat):
        upsert_user(chat_id, update.effective_user)
    log.info("voice | %s", describe_user(update.effective_user))
    if update.message.voice.duration > MAX_VOICE_SEC:
        log.info("voice too long (%ds) | %s", update.message.voice.duration, describe_user(update.effective_user))
        await update.message.reply_text(
            f"Э-э, целую поэму наговорил?! Больше {MAX_VOICE_SEC} секунд я не слушаю — покороче давай~ 💣"
        )
        return
    if not await rate_ok(update, chat_id):
        return
    try:
        async with typing(update.effective_chat):
            tg_file = await update.message.voice.get_file()
            data = await tg_file.download_as_bytearray()
            resp = await asyncio.to_thread(
                transcription, model=GROQ_STT_MODEL, file=("voice.ogg", bytes(data)), timeout=LLM_TIMEOUT
            )
        text = (resp.text or "").strip()
    except Exception:
        log.exception("STT error | %s", describe_user(update.effective_user))
        await update.message.reply_text("Что ты там бормочешь? Я не разобрала, повтори!")
        return
    if not text:
        await update.message.reply_text("Молчишь в микрофон? Скажи что-нибудь~")
        return
    if is_group(chat):
        text = f"[{speaker(update.effective_user)}] {text}"
    log.info("voice text | %s | %d chars", describe_user(update.effective_user), len(text))
    log.debug("voice text | %s | %r", describe_user(update.effective_user), text)
    await respond(update, chat_id, text)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    chat_id = chat.id
    if not await group_gate(update, context):  # в группе фото ловим только с @упоминанием/reply на бота
        return
    if not is_group(chat):
        upsert_user(chat_id, update.effective_user)
    log.info("photo | %s", describe_user(update.effective_user))
    if not await rate_ok(update, chat_id):
        return
    try:
        async with typing(chat):
            tg_file = await update.message.photo[-1].get_file()  # [-1] — наибольший размер
            data = await tg_file.download_as_bytearray()
    except Exception:
        log.exception("photo download error | %s", describe_user(update.effective_user))
        await update.message.reply_text("Не разглядела картинку — пришли ещё раз!")
        return
    image_url = "data:image/jpeg;base64," + base64.b64encode(bytes(data)).decode()
    text = (update.message.caption or "").strip() or "*присылает тебе картинку и молча ждёт реакции*"
    if is_group(chat):
        text = f"[{speaker(update.effective_user)}] {text}"
    await respond(update, chat_id, text, image_url=image_url, model=GROQ_VISION_MODEL)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный отлов необработанных исключений в хендлерах."""
    log.exception("unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Ой-ёй, я запуталась! Попробуй ещё разок, ну~")


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
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("enable", cmd_enable))   # включить бота в группе (только админ)
    app.add_handler(CommandHandler("disable", cmd_disable))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^mode:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_error_handler(on_error)
    log.info("Kiwi bot started, model=%s, db=%s, log=%s", GROQ_MODEL, DB_FILE, LOG_FILE)
    return app
