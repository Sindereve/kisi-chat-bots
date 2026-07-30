"""Изоляция: DB_FILE читается при импорте kiwi.config, поэтому temp-БД выставляем
здесь — conftest грузится pytest'ом до любого тестового модуля."""
import os
import tempfile

os.environ["DB_FILE"] = os.path.join(tempfile.mkdtemp(), "test.db")
