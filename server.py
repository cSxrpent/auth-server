from flask import Flask, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

def load_users():
    with open("users.json", "r") as f:
        return json.load(f)

@app.route('/')
def home():
    return "Auth server with subscriptions is running."

@app.route('/auth', methods=['GET'])
def auth():
    username = request.args.get('username')
    if not username:
        return jsonify({"error": "username parameter is missing"}), 400

    users = load_users()
    for user in users:
        if user["username"].lower() == username.lower():
            expiry = datetime.strptime(user["expires"], "%Y-%m-%d")
            if expiry >= datetime.now():
                return jsonify({"status": "authorized", "expires": user["expires"]})
            else:
                return jsonify({"status": "expired", "expires": user["expires"]}), 403

    return jsonify({"status": "unauthorized"}), 403

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)
