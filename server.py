import os
import json
import base64
import jwt
import requests
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

SCRIPT_PATH = os.path.join("protected", "notpayload.js")

# GitHub sync config
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # MUST be set to allow push
GITHUB_REPO = os.getenv("GITHUB_REPO", "cSxrpent/auth-users")  # owner/repo
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_PATH = os.getenv("GITHUB_PATH", "users.json")  # path in repo, typically users.json

# GitHub API base
GITHUB_API_BASE = "https://api.github.com"


# -----------------------
# Utilitaires
# -----------------------
def github_api_headers():
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def load_users_from_github():
    """Récupère users.json depuis GitHub via API (préf) ou raw URL."""
    try:
        if GITHUB_TOKEN:
            url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
            params = {"ref": GITHUB_BRANCH}
            r = requests.get(url, headers=github_api_headers(), params=params, timeout=6)
            if r.status_code == 200:
                data = r.json()
                content_b64 = data.get("content", "")
                decoded = base64.b64decode(content_b64).decode("utf-8")
                return json.loads(decoded)
            else:
                print(f"⚠️ GitHub API returned {r.status_code} when loading users.json: {r.text}")
                return []
        else:
            # fallback: raw.githubusercontent URL (public required)
            raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_PATH}"
            r = requests.get(raw_url, timeout=6)
            if r.status_code == 200:
                return r.json()
            else:
                print(f"⚠️ Raw fetch returned {r.status_code} when loading users.json")
                return []
    except Exception as e:
        print("❌ Error loading users from GitHub:", e)
        return []


def get_github_file_sha():
    """Get current file SHA on GitHub (needed for updates). Returns None if not found."""
    try:
        url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        params = {"ref": GITHUB_BRANCH}
        r = requests.get(url, headers=github_api_headers(), params=params, timeout=6)
        if r.status_code == 200:
            return r.json().get("sha")
        return None
    except Exception as e:
        print("❌ Error getting file sha:", e)
        return None


def push_users_to_github(users):
    """
    Push the users list (JSON) to the GitHub repo path.
    Returns True on success, False otherwise.
    """
    payload_json = json.dumps(users, indent=2, ensure_ascii=False)
    content_b64 = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    sha = get_github_file_sha()

    body = {
        "message": f"Update users.json via admin panel ({datetime.utcnow().isoformat()})",
        "content": content_b64,
        "branch": GITHUB_BRANCH
    }
    if sha:
        body["sha"] = sha

    try:
        if not GITHUB_TOKEN:
            print("⚠️ No GITHUB_TOKEN set — fallback to local save (no remote push).")
            return False

        r = requests.put(url, headers=github_api_headers(), json=body, timeout=8)
        if r.status_code in (200, 201):
            print("✅ users.json successfully pushed to GitHub.")
            return True
        else:
            print(f"❌ GitHub push failed: {r.status_code} {r.text}")
            return False
    except Exception as e:
        print("❌ Exception while pushing to GitHub:", e)
        return False


def load_users():
    """Source de vérité : retourne la liste d'utilisateurs (list of dicts).
       On charge depuis GitHub à chaque appel (pour instantané)."""
    users = load_users_from_github()
    # Normalize: accept either dict-form {"TARIK": "2025-..."} or list-of-objects
    if isinstance(users, dict):
        # convert to list of {"username": ..., "expires": ...}
        arr = []
        for k, v in users.items():
            # if value is dict, try to get 'expires'
            if isinstance(v, dict) and "expires" in v:
                arr.append({"username": k, "expires": v["expires"]})
            else:
                # assume v is expiry string
                arr.append({"username": k, "expires": v})
        return arr
    if isinstance(users, list):
        # assume already list of {"username","expires"}
        return users
    return []


def save_users_local(users):
    """Fallback local save (only used if no GITHUB_TOKEN)."""
    try:
        with open(GITHUB_PATH, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print("❌ Local save failed:", e)
        return False


def find_user(users, username):
    for u in users:
        if u.get("username", "").lower() == username.lower():
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

    users = load_users()
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
            # Ne pas rediriger : afficher directement l'admin sous la même URL (POST /login)
            users = load_users()
            return render_template("admin.html", users=users)
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
# Admin API (edits push to GitHub)
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

    # Try to push to GitHub
    success = False
    if GITHUB_TOKEN:
        success = push_users_to_github(users)
    else:
        success = save_users_local(users)

    if not success:
        return jsonify({"error": "Failed to save users remotely. Check GITHUB_TOKEN or logs."}), 500

    return jsonify({"message": "ok", "username": username, "expires": expires}), 200


@app.route("/api/delete", methods=["POST"])
@login_required
def api_delete():
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username missing"}), 400

    users = [u for u in load_users() if u["username"].lower() != username.lower()]

    # push deletion to GitHub (or save locally)
    success = False
    if GITHUB_TOKEN:
        success = push_users_to_github(users)
    else:
        success = save_users_local(users)

    if not success:
        return jsonify({"error": "Failed to save users remotely. Check GITHUB_TOKEN or logs."}), 500

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
