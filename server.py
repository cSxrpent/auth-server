from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import json
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

ADMIN_PASSWORD = "motdepassefort"  # 🔒 à changer évidemment !

def load_users():
    with open("users.json", "r") as f:
        return json.load(f)

def save_users(users):
    with open("users.json", "w") as f:
        json.dump(users, f, indent=2)

@app.route('/')
def home():
    return "Auth server with admin panel is running."

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


# ==============================
# 🔐 ADMIN PANEL (remis ici)
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


@app.route('/admin/add_duration', methods=['POST'])
def add_user_with_duration():
    password = request.args.get("password")
    if password != ADMIN_PASSWORD:
        return "Unauthorized", 403

    username = request.form["username"]
    duration = int(request.form["duration"])
    expires = (datetime.now() + timedelta(days=duration)).strftime("%Y-%m-%d")

    users = load_users()
    users.append({"username": username, "expires": expires})
    save_users(users)

    return redirect(url_for("admin", password=password))


@app.route('/admin/delete/<username>', methods=['GET'])
def delete_user(username):
    password = request.args.get("password")
    if password != ADMIN_PASSWORD:
        return "Unauthorized", 403

    users = load_users()
    users = [u for u in users if u["username"].lower() != username.lower()]
    save_users(users)

    return redirect(url_for("admin", password=password))


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)
