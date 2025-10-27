from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)  # 🔥 autorise les requêtes venant du navigateur (chrome-extension://)

ADMIN_PASSWORD = "ElamdaElammm"  # ⚠️ change-le évidemment !

def load_users():
    with open("users.json", "r") as f:
        return json.load(f)

def save_users(users):
    with open("users.json", "w") as f:
        json.dump(users, f, indent=2)

@app.route('/')
def home():
    return "✅ Auth server with admin panel is running."

# ==============================
# 🔑 API utilisée par l’extension
# ==============================
@app.route('/auth', methods=['GET'])
def auth():
    username = request.args.get('username')
    if not username:
        return jsonify({"message": "username parameter is missing"}), 400

    users = load_users()
    for user in users:
        if user["username"].lower() == username.lower():
            expiry = datetime.strptime(user["expires"], "%Y-%m-%d")
            if expiry >= datetime.now():
                return jsonify({"message": "authorized", "expires": user["expires"]}), 200
            else:
                return jsonify({"message": "expired", "expires": user["expires"]}), 403

    return jsonify({"message": "unauthorized"}), 403

# ==============================
# 🧑‍💻 ADMIN PANEL
# ==============================
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    password = request.args.get("password")
    if password != ADMIN_PASSWORD:
        return "Unauthorized", 403

    users = load_users()
    return render_template("admin.html", users=users, password=password)

@app.route('/admin/add', methods=['POST'])
def add_user():
    password = request.args.get("password")
    if password != ADMIN_PASSWORD:
        return "Unauthorized", 403

    username = request.form["username"]
    expires = request.form["expires"]

    users = load_users()
    users.append({"username": username, "expires": expires})
    save_users(users)

    return redirect(url_for("admin", password=password))

@app.r
