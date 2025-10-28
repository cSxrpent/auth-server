import os
import json
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, session, send_from_directory, Response
)
from flask_cors import CORS

# -----------------------
# Configuration
# -----------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_replace_in_prod")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_locally")
JWT_SECRET = os.getenv("JWT_SECRET", "dev_jwt_secret_replace")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")

USERS_FILE = "users.json"
SCRIPT_PATH = os.path.join("protected", "notpayload.js")

# -----------------------
# Utilitaires
# -----------------------
def load_users():
    """Recharge toujours le fichier users.json depuis le disque."""
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

# -----------------------
# Decorator pour routes admin
# -----------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# -----------------------
# AUTH ENDPOINT
# -----------------------
@app.route("/auth", methods=["GET"])
def auth():
    username = request.args.get("username")
    if not username:
        return jsonify({"message": "username parameter is missing"}), 400

    # ✅ Recharge users.json à chaque requête
    users = load_users()
    user = find_user(users, username)
    if not user:
        return jsonify({"message": "unauthorized"}), 403

    try:
        expiry = parse_date(user["expires"])
    except Exception:
        return jsonify({"message": "unauthorized"}), 403

    if expiry >= datetime.now():
        payload = {
            "sub": username,
            "script_access": True,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10)
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
        return jsonify({
            "message": "authorized",
            "expires": user["expires"],
            "token": token
        }), 200
    else:
        return jsonify({"message": "expired", "expires": user["expires"]}), 403

# -----------------------
# Protected script
# -----------------------
@app.route("/script/notpayload.js", methods=["GET"])
def serve_notpayload():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "missing token"}), 401
    token = auth_header.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "token expired"}), 401
    except Exception:
        return jsonify({"error": "invalid token"}), 401

    username = payload.get("sub")
    if not username:
        return jsonify({"error": "invalid token payload"}), 401

    users = load_users()  # ✅ recharge ici aussi
    user = find_user(users, username)
    if not user:
        return jsonify({"error": "user not found"}), 403

    try:
        expiry = parse_date(user["expires"])
    except Exception:
        return jsonify({"error": "user expiry malformed"}), 403

    if expiry < datetime.now():
        return jsonify({"error": "subscription expired"}), 403

    try:
        with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
            js = f.read()
        resp = Response(js, mimetype="application/javascript")
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp
    except FileNotFoundError:
        return jsonify({"error": "script not found"}), 404

# -----------------------
# Admin pages
# -----------------------
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

@app.route("/admin")
@login_required
def admin():
    users = load_users()
    return render_template("admin.html", users=users)

# -----------------------
# Admin API
# -----------------------
@app.route("/api/users", methods=["GET"])
@login_required
def api_get_users():
    return jsonify(load_users())

@app.route("/api/add", methods=["POST"])
@login_required
def api_add():
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    duration = body.get("duration")
    expires = body.get("expires")

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

    users = [u for u in load_users() if u["username"].lower() != username.lower()]
    save_users(users)
    return jsonify({"message": "deleted", "username": username}), 200

# -----------------------
# Static + run
# -----------------------
@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
