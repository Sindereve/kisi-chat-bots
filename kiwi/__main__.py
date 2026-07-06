"""Точка входа: python -m kiwi — запускает бота в режиме polling."""
from kiwi.bot import build_app


def main() -> None:
    build_app().run_polling()


if __name__ == "__main__":
    main()
