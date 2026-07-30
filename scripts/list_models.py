"""Печатает доступные модели Groq — чтобы выбрать значение для GROQ_MODEL в .env."""
import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")


def get_list_of_models():
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError) as e:
        print(f"Ошибка при запросе к API: {e}")
        return
    print("Список доступных моделей Groq:")
    for model in data.get("data", []):
        print(f" - groq/{model['id']}")


if __name__ == "__main__":
    get_list_of_models()
