import os
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, session, send_from_directory
)
from flask_cors import CORS

# -----------------------
# Configuration
# -----------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Secret key & admin password from environment (safer than hardcoding)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_replace_in_prod")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_locally")

USERS_FILE = "users.json"  # list of {"username": "...", "expires": "YYYY-MM-DD"}

# -----------------------
# Utilitaires
# -----------------------
def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def find_user(users, username):
    for u in users:
        if u["username"].lower() == username.lower():
            return u
    return None

def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

# Decorator pour routes admin
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# -----------------------
# Public API used by extension
# -----------------------
@app.route("/auth", methods=["GET"])
def auth():
    """
    GET /auth?username=XXX
    Returns: 200 + {"message":"authorized","expires":"YYYY-MM-DD"} or 403 + {"message":"unauthorized"/"expired"}
    """
    username = request.args.get("username")
    if not username:
        return jsonify({"message": "username parameter is missing"}), 400

    users = load_users()
    user = find_user(users, username)
    if not user:
        return jsonify({"message": "unauthorized"}), 403

    try:
        expiry = parse_date(user["expires"])
    except Exception:
        # malformed date -> treat as unauthorized
        return jsonify({"message": "unauthorized"}), 403

    if expiry >= datetime.now():
        return jsonify({"message": "authorized", "expires": user["expires"]}), 200
    else:
        return jsonify({"message": "expired", "expires": user["expires"]}), 403

# ------------------------------------
# Admin web UI (login + dashboard)
# ------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        else:
            error = "Mot de passe incorrect."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Admin dashboard page
@app.route("/admin")
@login_required
def admin():
    users = load_users()
    # Clean expired (but keep them until explicit delete if you prefer)
    # We show all users (expired or not).
    return render_template("admin.html", users=users)

# Classic form routes (kept for compatibility)
@app.route("/admin/add", methods=["POST"])
@login_required
def admin_add():
    # This route expects either:
    # - form field 'expires' as YYYY-MM-DD
    # - or form field 'duration' as number of days
    username = request.form.get("username", "").strip()
    expires = request.form.get("expires", "").strip()
    duration = request.form.get("duration", "").strip()

    if not username:
        return redirect(url_for("admin"))

    if not expires and duration:
        try:
            days = int(duration)
            expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        except:
            expires = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    if not expires:
        # default 7 days
        expires = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    users = load_users()
    # replace if exists
    existing = find_user(users, username)
    if existing:
        existing["expires"] = expires
    else:
        users.append({"username": username, "expires": expires})
    save_users(users)
    return redirect(url_for("admin"))

@app.route("/admin/delete/<username>", methods=["GET"])
@login_required
def admin_delete(username):
    users = load_users()
    users = [u for u in users if u["username"].lower() != username.lower()]
    save_users(users)
    return redirect(url_for("admin"))

# -----------------------
# Modern AJAX endpoints for admin page
# -----------------------
@app.route("/api/users", methods=["GET"])
@login_required
def api_get_users():
    users = load_users()
    return jsonify(users)

@app.route("/api/add", methods=["POST"])
@login_required
def api_add():
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    # duration in days OR expires in YYYY-MM-DD
    duration = body.get("duration")  # integer days
    expires = body.get("expires")    # date string

    if not username:
        return jsonify({"error": "username missing"}), 400

    if not expires and duration:
        try:
            expires = (datetime.now() + timedelta(days=int(duration))).strftime("%Y-%m-%d")
        except:
            expires = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    if not expires:
        expires = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    users = load_users()
    existing = find_user(users, username)
    if existing:
        existing["expires"] = expires
    else:
        users.append({"username": username, "expires": expires})
    save_users(users)
    return jsonify({"message": "ok", "username": username, "expires": expires}), 200

@app.route("/api/delete", methods=["POST"])
@login_required
def api_delete():
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username missing"}), 400
    users = load_users()
    users = [u for u in users if u["username"].lower() != username.lower()]
    save_users(users)
    return jsonify({"message": "deleted", "username": username}), 200

# -----------------------
# Serve admin static (if needed)
# -----------------------
@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    # PORT taken from env by Render, else fallback 10000
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
