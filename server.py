import logging
import time
import threading
import requests
import uuid
import base64
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib3.exceptions import InsecureRequestWarning
from dotenv import load_dotenv

# Load .env in local dev only (if exists)
load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
app = Flask(__name__)

# --- Config from env ---
GIGACHAT_CLIENT_ID = os.getenv("0199ca88-1ca2-7766-89d1-fe395b8267fc")
GIGACHAT_CLIENT_SECRET = os.getenv("dd87c36f-0c27-4867-8262-a83ea80996e8")
GIGACHAT_OAUTH_URL = os.getenv("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_COMPLETIONS_URL = os.getenv("GIGACHAT_COMPLETIONS_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")

if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
    app.logger.warning("GIGACHAT_CLIENT_ID or GIGACHAT_CLIENT_SECRET are not set. Set them as environment variables in production.")

# Allow CORS from frontend domains. In prod, set FRONTEND_ORIGINS env var as comma-separated
frontend_origins = os.getenv("FRONTEND_ORIGINS")
if frontend_origins:
    origins = [o.strip() for o in frontend_origins.split(",") if o.strip()]
    CORS(app, origins=origins)
else:
    # permissive during testing; in production set FRONTEND_ORIGINS
    CORS(app)

# --- Token storage ---
token_storage = {"access_token": None, "expires_at": 0}
token_lock = threading.Lock()

def get_new_gigachat_token():
    request_id = str(uuid.uuid4())
    app.logger.info(f"🔑 Requesting new GigaChat token (RqUID: {request_id})")

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
        response = requests.post(GIGACHAT_OAUTH_URL, headers=headers, data=payload, verify=False, timeout=10)
        if response.status_code != 200:
            app.logger.error(f"Token error ({response.status_code}): {response.text}")
            return None
        token_info = response.json()
        with token_lock:
            token_storage["access_token"] = token_info.get("access_token")
            # expires_at provided in ms in original code: convert and subtract 60s safety
            expires_ms = token_info.get("expires_at") or 0
            token_storage["expires_at"] = (expires_ms / 1000) - 60
        app.logger.info("✅ New token obtained.")
        return token_storage["access_token"]
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching token: {e}")
        return None

def get_valid_token():
    with token_lock:
        if token_storage["access_token"] is None or token_storage["expires_at"] <= time.time():
            app.logger.info("♻️ Token missing or expired — refreshing...")
            return get_new_gigachat_token()
        return token_storage["access_token"]

def background_token_refresher(interval_minutes=50):
    while True:
        time.sleep(interval_minutes * 60)
        app.logger.info("🔄 Background token refresh...")
        get_new_gigachat_token()

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def proxy_chat():
    if request.method == 'OPTIONS':
        return '', 204
    app.logger.info("📩 Received POST /api/chat")
    client_data = request.get_json(silent=True)
    if not client_data:
        return jsonify({"error": "Empty request body"}), 400

    access_token = get_valid_token()
    if not access_token:
        return jsonify({"error": "Failed to obtain authorization token from GigaChat."}), 502

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    try:
        app.logger.info("🚀 Forwarding request to GigaChat...")
        response = requests.post(GIGACHAT_COMPLETIONS_URL, headers=headers, json=client_data, verify=False, timeout=30)
        app.logger.info(f"✅ GigaChat responded: {response.status_code}")
        if response.status_code != 200:
            return jsonify({"error": f"GigaChat returned {response.status_code}", "details": response.text}), response.status_code
        return jsonify(response.json()), 200
    except requests.exceptions.Timeout:
        app.logger.error("⏰ Timeout contacting GigaChat.")
        return jsonify({"error": "Timeout contacting GigaChat."}), 504
    except Exception as e:
        app.logger.exception("Unhandled exception while contacting GigaChat:")
        return jsonify({"error": "Internal server error."}), 500

if __name__ == '__main__':
    # Pre-warm token in dev if possible
    try:
        get_new_gigachat_token()
    except Exception:
        app.logger.warning("Couldn't prefetch token (this is OK for local dev).")
    threading.Thread(target=background_token_refresher, daemon=True).start()
    port = int(os.getenv("PORT", "5000"))
    app.run(host='0.0.0.0', port=port, debug=False)