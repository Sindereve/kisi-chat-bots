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
HISTORY_LEN = int(os.getenv("HISTORY_LEN", "20"))
DB_FILE = os.getenv("DB_FILE", "state.db")
