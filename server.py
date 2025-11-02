import os
import json
import base64
import requests
import time
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
CORS(app)  # allow cross-origin for simple API access

# Secrets & GitHub config from env (safer)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_replace_in_prod")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_locally")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = "cSxrpent"
GITHUB_REPO = "auth-users"
GITHUB_BRANCH = "main"
GITHUB_PATH = "users.json"

# GitHub raw URL (public access, no token needed if repo is public)
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_PATH}"

USERS_FILE = "users.json"  # local fallback file

# -----------------------
# GitHub helpers
# -----------------------
def load_users_from_github():
    """Fetch users.json from GitHub API (no cache). Returns list of users or None on failure."""
    try:
        # Use GitHub API instead of raw URL to avoid cache
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Accept": "application/vnd.github.v3+json"}
        
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
        # Add cache-busting parameter
        params = {"ref": GITHUB_BRANCH, "t": int(time.time())}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            content_b64 = data.get("content", "")
            decoded = base64.b64decode(content_b64.encode()).decode("utf-8")
            users = json.loads(decoded)
            print(f"✓ Loaded {len(users)} users from GitHub API")
            return users
        else:
            print(f"✗ GitHub API fetch failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Error fetching from GitHub API: {e}")
        return None

def _github_get_file():
    """Return (ok, info). If ok True: info={'content': <python obj list>, 'sha': <sha>}"""
    if not GITHUB_TOKEN:
        return False, {"error": "no_github_token"}
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    params = {"ref": GITHUB_BRANCH}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            j = r.json()
            content_b64 = j.get("content", "")
            sha = j.get("sha")
            decoded = base64.b64decode(content_b64.encode()).decode("utf-8")
            try:
                data = json.loads(decoded)
            except Exception as e:
                return False, {"error": f"invalid_json_in_github:{e}"}
            return True, {"content": data, "sha": sha}
        else:
            return False, {"error": f"gh_get_status_{r.status_code}", "detail": r.text}
    except Exception as e:
        return False, {"error": f"gh_get_exception:{e}"}

def _github_put_file(new_users, sha=None):
    """Create/Update users.json on GitHub. Return (ok, detail)."""
    if not GITHUB_TOKEN:
        return False, {"error": "no_github_token"}
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    content_b64 = base64.b64encode(json.dumps(new_users, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"Update users.json via server at {datetime.utcnow().isoformat()}Z",
        "content": content_b64,
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            return True, r.json()
        else:
            return False, {"error": f"gh_put_status_{r.status_code}", "detail": r.text}
    except Exception as e:
        return False, {"error": f"gh_put_exception:{e}"}

# -----------------------
# User storage helpers
# -----------------------
def load_users():
    """Try GitHub first, then fallback to local users.json."""
    print("🔍 Loading users...")
    
    # Try GitHub API first
    users = load_users_from_github()
    if users is not None:
        print(f"✅ Loaded from GitHub: {len(users)} users")
        return users
    
    # Fallback to local file
    print("⚠️ GitHub failed, falling back to local file")
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            local_users = json.load(f)
            print(f"✅ Loaded from local: {len(local_users)} users")
            return local_users
    except FileNotFoundError:
        print("⚠ Local users.json not found")
        return []
    except Exception as e:
        print(f"⚠ Error loading local users.json: {e}")
        return []

def save_users(users):
    """
    Write local file then try to push to GitHub if token is present.
    Returns dict describing results.
    """
    result = {"saved_local": False, "github": None}
    # write local
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        result["saved_local"] = True
    except Exception as e:
        result["saved_local"] = False
        result["local_error"] = str(e)
    # try pushing to GitHub
    if GITHUB_TOKEN:
        ok, info = _github_get_file()
        sha = info.get("sha") if ok else None
        ok2, put_res = _github_put_file(users, sha=sha)
        result["github"] = {"ok": ok2, "detail": put_res}
    else:
        result["github"] = {"ok": False, "detail": "no_github_token"}
    return result

# -----------------------
# Utilities
# -----------------------
def find_user(users, username):
    for u in users:
        try:
            if u["username"].lower() == username.lower():
                return u
        except Exception:
            continue
    return None

def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")

# -----------------------
# Auth API used by extension
# -----------------------
@app.route("/auth", methods=["GET"])
def auth():
    """
    GET /auth?username=XXX
    Returns:
      - 200 + {"message":"authorized","expires":"YYYY-MM-DD"}
      - 403 + {"message":"unauthorized"/"expired"}
      - 400 + {"message":"username parameter is missing"}
    """
    username = request.args.get("username")
    if not username:
        return jsonify({"message": "username parameter is missing"}), 400

    users = load_users()
    user = find_user(users, username)
    
    if not user:
        print(f"❌ Auth failed: username '{username}' not found")
        return jsonify({"message": "unauthorized"}), 403

    try:
        expiry = parse_date(user["expires"])
    except Exception:
        print(f"❌ Auth failed: invalid expiry date for '{username}'")
        return jsonify({"message": "unauthorized"}), 403

    if expiry >= datetime.now():
        print(f"✅ Auth success: '{username}' valid until {user['expires']}")
        return jsonify({"message": "authorized", "expires": user["expires"]}), 200
    else:
        print(f"⏰ Auth failed: '{username}' expired on {user['expires']}")
        return jsonify({"message": "expired", "expires": user["expires"]}), 403

# ------------------------------------
# Admin web UI (login + dashboard)
# ------------------------------------
#laisse moi tester
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

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

@app.route("/admin/add", methods=["POST"])
@login_required
def admin_add():
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
        expires = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    users = load_users()
    existing = find_user(users, username)
    if existing:
        existing["expires"] = expires
    else:
        users.append({"username": username, "expires": expires})
    save_res = save_users(users)
    return redirect(url_for("admin"))

@app.route("/admin/delete/<username>", methods=["GET"])
@login_required
def admin_delete(username):
    users = load_users()
    users = [u for u in users if u["username"].lower() != username.lower()]
    save_res = save_users(users)
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
    save_res = save_users(users)
    return jsonify({"message": "ok", "username": username, "expires": expires, "save_result": save_res}), 200

@app.route("/api/delete", methods=["POST"])
@login_required
def api_delete():
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username missing"}), 400
    users = [u for u in load_users() if u["username"].lower() != username.lower()]
    save_res = save_users(users)
    return jsonify({"message": "deleted", "username": username, "save_result": save_res}), 200

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
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Starting server on port {port}")
    print(f"📁 GitHub repo: {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"📄 GitHub file: {GITHUB_PATH}")
    app.run(host="0.0.0.0", port=port)