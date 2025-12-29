import os
import json
import base64
import requests
import time
import threading
from datetime import datetime, timedelta
from collections import deque
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, session, send_from_directory, make_response
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

STATS_FILE = "stats.json"  # track user connection counts

LAST_CONNECTED_FILE = "last_connected.json"  # track last connection per user

CET_OFFSET = timedelta(hours=1)  # CET = UTC+1 in winter

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
        "message": f"Update users.json via server at {(datetime.utcnow() + CET_OFFSET).isoformat()}Z",
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
    """Try GitHub first, then fallback to local users.json. Overwrite local if different from GitHub."""
    print("🔍 Loading users...")
    
    # Try GitHub API first
    users = load_users_from_github()
    if users is not None:
        print(f"✅ Loaded from GitHub: {len(users)} users")
        
        # Check if local file exists and differs
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                local_users = json.load(f)
            
            # Normalize for comparison (sort by username)
            def normalize(u_list):
                return sorted(u_list, key=lambda x: x.get('username', '').lower())
            
            github_normalized = normalize(users)
            local_normalized = normalize(local_users)
            
            if github_normalized != local_normalized:
                print("🔄 Local file differs from GitHub, overwriting local with GitHub data")
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(users, f, indent=2, ensure_ascii=False)
                log_event("Overwrote local users.json with GitHub data")
            else:
                print("✅ Local file matches GitHub")
        
        except FileNotFoundError:
            print("📝 Local users.json not found, creating it with GitHub data")
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error checking/comparing local file: {e}")
        
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

def load_stats():
    """Load stats from local file."""
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"⚠ Error loading stats: {e}")
        return {}

def save_stats(stats):
    """Save stats to local file."""
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠ Error saving stats: {e}")

def load_last_connected():
    """Load last connected times from local file."""
    try:
        with open(LAST_CONNECTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"⚠ Error loading last_connected: {e}")
        return {}

def save_last_connected(last_conn):
    """Save last connected to local file."""
    try:
        with open(LAST_CONNECTED_FILE, "w", encoding="utf-8") as f:
            json.dump(last_conn, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠ Error saving last_connected: {e}")

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

    # client IP (support proxied headers)
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    users = load_users()
    user = find_user(users, username)
    
    if not user:
        log_event(f"auth fail: username '{username}' not found", level="warn")
        record_connection(username, ip, "unauthorized")
        return jsonify({"message": "unauthorized"}), 403

    try:
        expiry = parse_date(user["expires"])
    except Exception:
        log_event(f"auth fail: invalid expiry date for '{username}'", level="error")
        record_connection(username, ip, "unauthorized")
        return jsonify({"message": "unauthorized"}), 403

    if expiry >= datetime.now():
        log_event(f"auth success: '{username}' valid until {user['expires']}", level="info")
        record_connection(username, ip, "authorized")
        return jsonify({"message": "authorized", "expires": user["expires"]}), 200
    else:
        log_event(f"auth expired: '{username}' expired on {user['expires']}", level="warn")
        record_connection(username, ip, "expired")
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
    log_event(f"web add: {username} expires {expires}")
    return redirect(url_for("admin"))

@app.route("/admin/delete/<username>", methods=["GET"])
@login_required
def admin_delete(username):
    users = load_users()
    users = [u for u in users if u["username"].lower() != username.lower()]
    save_res = save_users(users)
    log_event(f"web delete: {username}")
    return redirect(url_for("admin"))

# -----------------------
# Modern AJAX endpoints for admin page
# -----------------------
@app.route("/api/users", methods=["GET"])
@login_required
def api_get_users():
    users = load_users()
    last_conn = load_last_connected()
    for u in users:
        u["last_connected"] = last_conn.get(u["username"])
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
    log_event(f"api_add: {username} expires {expires}")
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
    log_event(f"api_delete: {username}")
    return jsonify({"message": "deleted", "username": username, "save_result": save_res}), 200

@app.route("/api/extend", methods=["POST"])
@login_required
def api_extend():
    """Prolonge l'accès d'un utilisateur existant de X jours"""
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    days = body.get("days")
    
    # Validation
    if not username:
        return jsonify({"error": "username missing"}), 400
    
    if not days or not isinstance(days, int) or days <= 0:
        return jsonify({"error": "invalid days value"}), 400
    
    # Charger les utilisateurs
    users = load_users()
    user = find_user(users, username)
    
    # Vérifier que l'utilisateur existe
    if not user:
        return jsonify({"error": f"User '{username}' not found"}), 404
    
    try:
        # Parser la date d'expiration actuelle
        current_expiry = parse_date(user["expires"])
        
        # Si la date est déjà passée, partir d'aujourd'hui
        if current_expiry < datetime.now():
            base_date = datetime.now()
            print(f"⏰ User '{username}' was expired, extending from today")
        else:
            base_date = current_expiry
            print(f"📅 User '{username}' is active, extending from {user['expires']}")
        
        # Ajouter les jours
        new_expiry = base_date + timedelta(days=days)
        new_expiry_str = new_expiry.strftime("%Y-%m-%d")
        
        # Mettre à jour l'utilisateur
        user["expires"] = new_expiry_str
        
        # Sauvegarder sur GitHub
        save_res = save_users(users)
        
        print(f"✅ Extended '{username}' by {days} days. New expiry: {new_expiry_str}")
        log_event(f"extended: {username} +{days} days -> {new_expiry_str}")
        
        return jsonify({
            "message": "extended",
            "username": username,
            "addedDays": days,
            "newExpires": new_expiry_str,
            "save_result": save_res
        }), 200
        
    except Exception as e:
        print(f"❌ Error extending user: {e}")
        return jsonify({"error": f"Failed to extend: {str(e)}"}), 500

# -----------------------
# Serve admin static (if needed)
# -----------------------
@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

# -----------------------
# Background ping to admin (enhanced)
# -----------------------
# Configurable via environment variables:
# - PING_ADMIN_URL (default: http://auth-server-aj8k.onrender.com/admin)
# - PING_ADMIN_INTERVAL (seconds, default: 300)
# - PING_ADMIN_ENABLED (1/true to enable, default: 1)
PING_ADMIN_URL = os.getenv("PING_ADMIN_URL", "http://auth-server-aj8k.onrender.com/admin")
try:
    PING_ADMIN_INTERVAL = int(os.getenv("PING_ADMIN_INTERVAL", "300"))
except Exception:
    PING_ADMIN_INTERVAL = 300
PING_ADMIN_ENABLED = os.getenv("PING_ADMIN_ENABLED", "1").lower() in ("1", "true", "yes", "on")

# In-memory logs and ping state (kept for admin panel)
LOGS = deque(maxlen=500)
# Recent connections (username, ip, status) to show who used the bot recently
RECENT_CONN = deque(maxlen=300)

def log_event(msg, level="info"):
    """Store a structured log and still print a compact line for console."""
    ts = (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d %H:%M:%SZ")
    entry = {"ts": ts, "msg": str(msg), "level": level}
    LOGS.appendleft(entry)
    # keep console-friendly output
    print(f"[{ts}] [{level.upper()}] {msg}")


def record_connection(username, ip, status):
    """Record a recent connection attempt (used by /auth endpoint)."""
    ts = (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d %H:%M:%SZ")
    entry = {"ts": ts, "username": username, "ip": ip, "status": status}
    RECENT_CONN.appendleft(entry)
    # Log a short message for visibility
    lvl = "info" if status == "authorized" else "warn"
    log_event(f"conn {status}: {username} @{ip}", level=lvl)
    
    # Update stats if authorized
    if status == "authorized":
        stats = load_stats()
        stats[username] = stats.get(username, 0) + 1
        save_stats(stats)
        
        # Update last connected
        last_conn = load_last_connected()
        last_conn[username] = ts
        save_last_connected(last_conn)

PING_STATE = {
    "enabled": PING_ADMIN_ENABLED,
    "url": PING_ADMIN_URL,
    "interval": PING_ADMIN_INTERVAL,
    "last_time": None,
    "last_code": None,
    "last_error": None
}

_ping_stop_event = threading.Event()
_ping_thread = None
_ping_lock = threading.Lock()

def _ping_admin_loop(url, interval, stop_event):
    session = requests.Session()
    while not stop_event.is_set():
        now = datetime.utcnow() + CET_OFFSET
        if now.hour == 3 and now.minute < 30:
            # Skip pinging between 3:00 and 3:30 CET
            log_event("Skipping ping as it's between 3:00 and 3:30 CET")
        else:
            try:
                start = time.time()
                r = session.get(url, timeout=10)
                elapsed = time.time() - start
                PING_STATE["last_time"] = now.isoformat() + "Z"
                PING_STATE["last_code"] = r.status_code
                PING_STATE["last_error"] = None
                log_event(f"ping -> {url} {r.status_code} ({elapsed:.2f}s)")
            except Exception as e:
                PING_STATE["last_time"] = now.isoformat() + "Z"
                PING_STATE["last_code"] = None
                PING_STATE["last_error"] = str(e)
                log_event(f"ping error -> {e}", level="error")
        # wait but allow early exit
        stop_event.wait(interval)

def start_ping_thread():
    global _ping_thread, _ping_stop_event
    with _ping_lock:
        if _ping_thread and _ping_thread.is_alive():
            return False
        _ping_stop_event = threading.Event()
        _ping_thread = threading.Thread(target=_ping_admin_loop, args=(PING_ADMIN_URL, PING_ADMIN_INTERVAL, _ping_stop_event), daemon=True)
        _ping_thread.start()
        PING_STATE["enabled"] = True
        log_event(f"Started ping thread: {PING_ADMIN_URL} every {PING_ADMIN_INTERVAL}s")
        return True

def stop_ping_thread():
    global _ping_thread, _ping_stop_event
    with _ping_lock:
        if _ping_thread and _ping_thread.is_alive():
            _ping_stop_event.set()
            _ping_thread.join(timeout=2)
            _ping_thread = None
            PING_STATE["enabled"] = False
            log_event("Stopped ping thread")
            return True
        return False

# expose API endpoints for admin
@app.route("/api/ping", methods=["POST"])
@login_required
def api_ping():
    """Trigger a manual ping to the admin URL"""
    try:
        session_req = requests.Session()
        start = time.time()
        r = session_req.get(PING_ADMIN_URL, timeout=10)
        elapsed = time.time() - start
        PING_STATE["last_time"] = datetime.utcnow().isoformat() + "Z"
        PING_STATE["last_code"] = r.status_code
        PING_STATE["last_error"] = None
        log_event(f"manual ping -> {PING_ADMIN_URL} {r.status_code} ({elapsed:.2f}s)")
        return jsonify({"ok": True, "status": r.status_code, "elapsed": elapsed}), 200
    except Exception as e:
        PING_STATE["last_time"] = datetime.utcnow().isoformat() + "Z"
        PING_STATE["last_code"] = None
        PING_STATE["last_error"] = str(e)
        log_event(f"manual ping error -> {e}", level="error")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/ping/status", methods=["GET"])
@login_required
def api_ping_status():
    return jsonify(PING_STATE)

@app.route("/api/ping/toggle", methods=["POST"])
@login_required
def api_ping_toggle():
    body = request.get_json() or {}
    enabled = body.get("enabled")
    if enabled is None:
        return jsonify({"error":"missing 'enabled' parameter"}), 400
    if enabled:
        started = start_ping_thread()
        return jsonify({"ok": started, "enabled": True}), 200
    else:
        stopped = stop_ping_thread()
        return jsonify({"ok": stopped, "enabled": False}), 200

@app.route("/api/logs", methods=["GET"])
@login_required
def api_logs():
    # return structured logs
    return jsonify(list(LOGS))


@app.route("/api/recent", methods=["GET"])
@login_required
def api_recent():
    """Recent connection attempts to the bot (most recent first)."""
    return jsonify(list(RECENT_CONN))

@app.route("/api/stats", methods=["GET"])
@login_required
def api_stats():
    """Return user connection stats."""
    stats = load_stats()
    # Sort by count descending
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    return jsonify(sorted_stats)

# start background ping if configured
if PING_ADMIN_ENABLED:
    start_ping_thread()
else:
    print("ℹ️ ping_admin is disabled (PING_ADMIN_ENABLED not set)")

# Schedule shutdown at 3:30 AM CET every day
def shutdown_at_3am():
    while True:
        now = datetime.utcnow() + CET_OFFSET
        # Calculate next 3:30 AM CET
        next_3am = now.replace(hour=3, minute=30, second=0, microsecond=0)
        if now >= next_3am:
            next_3am += timedelta(days=1)
        sleep_time = (next_3am - now).total_seconds()
        time.sleep(sleep_time)
        log_event("Shutting down server at 3:30 AM CET")
        stop_ping_thread()
        os._exit(0)

shutdown_thread = threading.Thread(target=shutdown_at_3am, daemon=True)
shutdown_thread.start()

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Starting server on port {port}")
    print(f"📁 GitHub repo: {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"📄 GitHub file: {GITHUB_PATH}")
    app.run(host="0.0.0.0", port=port)