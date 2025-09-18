from flask import Flask, request, jsonify
import requests
import time

app = Flask(__name__)

# --- Configuration ---
USERNAME = "supportalertalarm@zentrades.pro"
PASSWORD = "#6D1i7ytdX95"
LOGIN_URL = "https://services.zentrades.pro/api/auth/login"
TIMECARD_URL = "https://services.zentrades.pro/api/timecard/create"
TOKEN_VALIDITY = 2 * 60 * 60   # 2 hours

# --- Client Class ---
class TimecardClient:
    def __init__(self, login_url, username, password):
        
        self.login_url = login_url
        self.username = username
        self.password = password
        self.base_headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://app.zentrades.pro",
            "referer": "https://app.zentrades.pro/",
            "request-from": "WEB_APP",
            "user-agent": "Mozilla/5.0",
            "timezone-offset": "-330",
            "timezonename": "Asia/Calcutta",
        }
        self._cached_token = None
        self._cached_company_id = None
        self._cached_user_id = None
        self._token_timestamp = 0

    def login(self, force=False):
        if not force and self._cached_token and (time.time() - self._token_timestamp < TOKEN_VALIDITY):
            return self._cached_token, self._cached_company_id, self._cached_user_id

        url = f"{self.login_url}?timestamp={int(time.time() * 1000)}"
        payload = {"username": self.username, "password": self.password, "rememberMe": True}
        resp = requests.post(url, headers=self.base_headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if "result" in data and "access-token" in data["result"]:
            token = data["result"]["access-token"]
            company_id = data["result"]["user"]["company"]["id"]
            user_id = data["result"]["user"]["id"]
        elif "access-token" in data:  # fallback
            token = data["access-token"]
            company_id = data.get("companyId") or data.get("company-id")
            user_id = data.get("userId") or data.get("user-id")
        else:
            raise ValueError("❌ No access-token returned in login response")

        self._cached_token = token
        self._cached_company_id = company_id
        self._cached_user_id = user_id
        self._token_timestamp = time.time()
        return token, company_id, user_id

    def create_timecard(self, payload):
        token, company_id, user_id = self.login()
        headers = self.base_headers.copy()
        headers.update({
            "access-token": token,
            "company-id": str(company_id),
            "user-id": str(user_id),
        })

        url = f"{TIMECARD_URL}?timestamp={int(time.time() * 1000)}"
        resp = requests.post(url, headers=headers, json=payload)

        if resp.status_code == 401 or "access-token" in resp.text.lower():
            token, company_id, user_id = self.login(force=True)
            headers.update({
                "access-token": token,
                "company-id": str(company_id),
                "user-id": str(user_id),
            })
            resp = requests.post(url, headers=headers, json=payload)

        resp.raise_for_status()
        return resp.json()

# --- Initialize Client ---
client = TimecardClient(LOGIN_URL, USERNAME, PASSWORD)

# --- Flask Routes ---
@app.route("/")
def home():
    return jsonify({"message": "✅ Timecard API is running"})

@app.route("/timecard", methods=["POST"])
def handle_timecards():
    data = request.get_json()

    if isinstance(data, dict):  # Single entry
        try:
            resp = client.create_timecard(data)
            return jsonify({"status": "success", "response": resp})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    elif isinstance(data, list):  # Bulk entries
        results = []
        for entry in data:
            try:
                resp = client.create_timecard(entry)
                results.append({"entry": entry, "status": "success", "response": resp})
            except Exception as e:
                results.append({"entry": entry, "status": "error", "message": str(e)})
        return jsonify(results)

    else:
        return jsonify({"status": "error", "message": "Invalid payload format"}), 400

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
