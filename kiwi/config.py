"""Загрузка окружения, настройка логирования и константы бота."""
import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
    ],
)
log = logging.getLogger("kiwi")

GROQ_MODEL = os.getenv("GROQ_MODEL", "groq/llama-3.3-70b-versatile")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "groq/whisper-large-v3")
# ponytail: дефолт-предположение — проверь актуальный vision-id через scripts/list_models.py
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "groq/meta-llama/llama-4-scout-17b-16e-instruct")
HISTORY_LEN = int(os.getenv("HISTORY_LEN", "20"))
DB_FILE = os.getenv("DB_FILE", "state.db")
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "5"))  # сообщений
RATE_WINDOW = float(os.getenv("RATE_WINDOW", "30"))  # за столько секунд
MAX_INPUT = int(os.getenv("MAX_INPUT", "2000"))  # потолок длины входящего сообщения, символов
SUMMARY_EVERY = int(os.getenv("SUMMARY_EVERY", "20"))  # обновлять досье каждые N ходов пользователя
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))  # таймаут вызовов LLM/STT, секунд
MAX_VOICE_SEC = int(os.getenv("MAX_VOICE_SEC", "120"))  # потолок длительности голосового, секунд
