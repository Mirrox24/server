import logging
import time
import threading
import requests
import uuid
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib3.exceptions import InsecureRequestWarning

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# --- Конфигурация GigaChat ---
GIGACHAT_OAUTH_URL = "https://gigachat.devices.sberbank.ru/api/v1/models"
GIGACHAT_COMPLETIONS_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

# --- Вставь сюда Authorization key из панели Сбера ---
AUTHORIZATION_KEY = "MDE5OWE2ZDgtZjA3NC03MzBmLTg1MWMtYjg0MjZmMjIyYmFlOmFhMTljMGI2LTYwYzAtNDllNi1hODk1LTc2Y2IzZGRiNzhiMQ=="

# --- Хранение токена ---
token_storage = {"access_token": None, "expires_at": 0}
token_lock = threading.Lock()


def kill_port(port):
    """Освобождает порт перед запуском сервера."""
    try:
        os.system(f"lsof -ti :{port} | xargs kill -9 2>/dev/null")
        logging.info(f"🧹 Освобожден порт {port}")
    except Exception as e:
        logging.warning(f"⚠️ Не удалось освободить порт {port}: {e}")


def get_new_gigachat_token():
    """Получает новый токен доступа."""
    request_id = str(uuid.uuid4())
    app.logger.info(f"🔑 Запрос нового токена GigaChat (RqUID: {request_id})")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": request_id,
        "Authorization": f"Basic {AUTHORIZATION_KEY}"
    }

    payload = {"scope": "GIGACHAT_API_B2B"}

    try:
        response = requests.post(
            GIGACHAT_OAUTH_URL,
            headers=headers,
            data=payload,
            verify=False,
            timeout=10
        )

        if response.status_code != 200:
            app.logger.error(f"❌ Ошибка токена ({response.status_code}): {response.text}")
            return None

        token_info = response.json()

        with token_lock:
            token_storage["access_token"] = token_info["access_token"]
            token_storage["expires_at"] = (token_info["expires_at"] / 1000) - 60

        app.logger.info("✅ Новый токен успешно получен.")
        return token_storage["access_token"]

    except requests.exceptions.RequestException as e:
        app.logger.error(f"💥 Ошибка при получении токена: {e}")
        return None


def get_valid_token():
    """Возвращает актуальный токен, обновляя его при необходимости."""
    with token_lock:
        if token_storage["access_token"] is None or token_storage["expires_at"] <= time.time():
            app.logger.info("♻️ Токен истёк или отсутствует — обновляем...")
            return get_new_gigachat_token()
        return token_storage["access_token"]


def background_token_refresher(interval_minutes=50):
    """Фоновое обновление токена каждые 50 минут."""
    while True:
        time.sleep(interval_minutes * 60)
        app.logger.info("🔄 Фоновое обновление токена...")
        get_new_gigachat_token()


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def proxy_chat():
    if request.method == "OPTIONS":
        return "", 204

    app.logger.info("📩 Получен POST-запрос на /api/chat")
    client_data = request.get_json(silent=True)

    if not client_data:
        return jsonify({"error": "Пустое тело запроса"}), 400

    access_token = get_valid_token()
    if not access_token:
        return jsonify({"error": "Не удалось получить токен авторизации от GigaChat"}), 502

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}

    try:
        response = requests.post(
            GIGACHAT_COMPLETIONS_URL,
            headers=headers,
            json=client_data,
            verify=False,
            timeout=30
        )
        app.logger.info(f"✅ Ответ GigaChat: {response.status_code}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        app.logger.error(f"💥 Ошибка при обращении к GigaChat: {e}")
        return jsonify({"error": "Ошибка при обращении к GigaChat"}), 500


if __name__ == "__main__":
    kill_port(5000)
    get_new_gigachat_token()
    threading.Thread(target=background_token_refresher, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)


