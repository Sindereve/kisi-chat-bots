"""Печатает доступные модели Groq — чтобы выбрать значение для GROQ_MODEL в .env."""
from dotenv import load_dotenv
import os
import requests

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")


def get_list_of_models():
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        print("Список доступных моделей Groq:")
        for model in response.json().get("data", []):
            print(f" - groq/{model['id']}")
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API: {e}")


if __name__ == "__main__":
    get_list_of_models()
