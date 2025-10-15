import logging
import time
import threading
import requests
import uuid
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib3.exceptions import InsecureRequestWarning

# ==========================
# 🔧 НАСТРОЙКИ
# ==========================
GIGACHAT_CLIENT_ID = "0199ca88-1ca2-7766-89d1-fe395b8267fc"
GIGACHAT_CLIENT_SECRET = "dd87c36f-0c27-4867-8262-a83ea80996e8"
GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_COMPLETIONS_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

# ==========================
# 🧠 НАСТРОЙКА FLASK
# ==========================
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

token_data = {"access_token": None, "expires_at": 0}
token_lock = threading.Lock()

# ==========================
# 🔑 ПОЛУЧЕНИЕ ТОКЕНА
# ==========================
def get_new_token():
    req_id = str(uuid.uuid4())
    app.logger.info(f"🔑 Запрос нового токена (RqUID: {req_id})")

    creds = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
    encoded = base64.b64encode(creds.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": req_id,
    }

    data = {"scope": "GIGACHAT_API_PERS"}
    try:
        r = requests.post(GIGACHAT_OAUTH_URL, headers=headers, data=data, verify=False, timeout=10)
        if r.status_code != 200:
            app.logger.error(f"❌ Ошибка токена: {r.status_code} {r.text}")
            return None
        j = r.json()
        with token_lock:
            token_data["access_token"] = j["access_token"]
            token_data["expires_at"] = (j["expires_at"] / 1000) - 60
        app.logger.info("✅ Новый токен получен.")
        return token_data["access_token"]
    except Exception as e:
        app.logger.error(f"💥 Ошибка токена: {e}")
        return None


def get_valid_token():
    with token_lock:
        if not token_data["access_token"] or token_data["expires_at"] <= time.time():
            app.logger.info("♻️  Токен истёк — обновляем...")
            return get_new_token()
        return token_data["access_token"]


def refresh_token_background():
    while True:
        time.sleep(50 * 60)
        get_new_token()

# ==========================
# 📡 API /api/chat
# ==========================
@app.route("/api/chat", methods=["POST", "OPTIONS"])
def proxy_chat():
    if request.method == "OPTIONS":
        response = app.response_class(status=204)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return response

    data = request.get_json()
    if not data:
        return jsonify({"error": "Пустое тело запроса"}), 400

    token = get_valid_token()
    if not token:
        return jsonify({"error": "Не удалось получить токен GigaChat"}), 502

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(GIGACHAT_COMPLETIONS_URL, headers=headers, json=data, verify=False, timeout=30)
        return jsonify(r.json()), r.status_code
    except requests.exceptions.Timeout:
        return jsonify({"error": "Время ожидания истекло"}), 504
    except Exception as e:
        app.logger.error(f"Ошибка: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return "✅ Flask сервер GigaChat запущен!"

# ==========================
# 🚀 ЗАПУСК
# ==========================
if __name__ == "__main__":
    get_new_token()
    threading.Thread(target=refresh_token_background, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
