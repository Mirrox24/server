import logging
import time
import threading
import requests
import uuid
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib3.exceptions import InsecureRequestWarning

# --- 1. Настройка ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
app = Flask(__name__)
CORS(app)

# --- 2. Конфигурация GigaChat ---
GIGACHAT_CLIENT_ID = "0199ca88-1ca2-7766-89d1-fe395b8267fc"
GIGACHAT_CLIENT_SECRET = "dd87c36f-0c27-4867-8262-a83ea80996e8"


GIGACHAT_OAUTH_URL = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
GIGACHAT_COMPLETIONS_URL = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'

# --- 3. Хранение токена ---
token_storage = {"access_token": None, "expires_at": 0}
token_lock = threading.Lock()


def get_new_gigachat_token():
    """Получает новый токен доступа."""
    request_id = str(uuid.uuid4())
    app.logger.info(f"🔑 Запрос нового токена GigaChat (RqUID: {request_id})")

    # Формируем Authorization заголовок
    credentials = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': request_id,
        'Authorization': f'Basic {encoded_credentials}'
    }

    payload = {'scope': 'GIGACHAT_API_PERS'}

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
            token_storage["expires_at"] = (token_info["expires_at"] / 1000) - 60  # -1 минута для запаса

        app.logger.info("✅ Новый токен успешно получен.")
        return token_storage["access_token"]

    except requests.exceptions.RequestException as e:
        app.logger.error(f"💥 Ошибка при получении токена: {e}")
        return None


def get_valid_token():
    """Возвращает актуальный токен, обновляя его при необходимости."""
    with token_lock:
        if token_storage["access_token"] is None or token_storage["expires_at"] <= time.time():
            app.logger.info("♻️  Токен истёк или отсутствует — обновляем...")
            return get_new_gigachat_token()
        return token_storage["access_token"]


def background_token_refresher(interval_minutes=50):
    """Фоновая задача для автоматического обновления токена каждые 50 минут."""
    while True:
        time.sleep(interval_minutes * 60)
        app.logger.info("🔄 Фоновое обновление токена...")
        get_new_gigachat_token()


# --- 4. Основной маршрут API ---
@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def proxy_chat():
    if request.method == 'OPTIONS':
        return '', 204

    app.logger.info("📩 Получен POST-запрос на /api/chat")
    client_data = request.get_json(silent=True)

    if not client_data:
        return jsonify({"error": "Пустое тело запроса"}), 400

    access_token = get_valid_token()
    if not access_token:
        return jsonify({
            "error": "Не удалось получить токен авторизации от GigaChat. Проверьте Client ID/Secret."
        }), 502

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    try:
        app.logger.info(f"🚀 Отправляем запрос в GigaChat...")
        response = requests.post(
            GIGACHAT_COMPLETIONS_URL,
            headers=headers,
            json=client_data,
            verify=False,
            timeout=30
        )

        app.logger.info(f"✅ Ответ GigaChat: {response.status_code}")
        app.logger.debug(f"Ответ: {response.text[:300]}")
        if response.status_code != 200:
            return jsonify({
                "error": f"GigaChat вернул ошибку {response.status_code}",
                "details": response.text
            }), response.status_code

        return jsonify(response.json()), 200

    except requests.exceptions.Timeout:
        app.logger.error("⏰ Превышено время ожидания ответа от GigaChat.")
        return jsonify({"error": "Время ожидания ответа от GigaChat истекло."}), 504
    except Exception as e:
        app.logger.error(f"💥 Неизвестная ошибка при обращении к GigaChat: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера."}), 500


# --- 5. Запуск сервера ---
if __name__ == '__main__':
    # Сразу получаем токен при старте
    get_new_gigachat_token()

    # Запускаем фоновое обновление токена каждые 50 минут
    threading.Thread(target=background_token_refresher, daemon=True).start()

    # Запускаем Flask
    app.run(host='0.0.0.0', port=5000, debug=True)