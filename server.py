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
    redirect, url_for, session, send_from_directory, make_response, abort, send_file
)
from flask_cors import CORS
import paypalrestsdk
import time
import secrets
from dotenv import load_dotenv
import hmac
import hashlib
import base64

load_dotenv()  # load .env file if it exists (for local development)

# Debug: Check if .env file exists (only for local development)
env_file = os.path.join(os.getcwd(), '.env')
if os.path.exists(env_file):
    print(f"✅ .env file found at {env_file} (local development)")
else:
    print(f"ℹ️ .env file not found (using environment variables from Render dashboard)")

# -----------------------
# Configuration
# -----------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)  # allow cross-origin for simple API access

# Secrets & GitHub config from env (safer)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_replace_in_prod")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_locally")
DOWNLOAD_SECRET = app.secret_key
# PayPal config
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live
PAYPAL_TEST_MODE = os.getenv("PAYPAL_TEST_MODE", "false").lower() == "true"  # Skip actual PayPal calls for testing


paypalrestsdk.configure({
    "mode": PAYPAL_MODE,
    "client_id": PAYPAL_CLIENT_ID,
    "client_secret": PAYPAL_CLIENT_SECRET
})

# Test PayPal configuration
try:
    # Try to get an access token to verify credentials
    import paypalrestsdk.api as paypal_api
    api = paypal_api.default()
    token = api.get_token_hash()
    print("✅ PayPal credentials verified successfully")
except Exception as e:
    print(f"⚠️ PayPal credentials verification failed: {e}")
    print("   This might be normal if running without network or with invalid credentials")

# Check configuration on startup
if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
    print("⚠️ WARNING: PayPal credentials not found in .env. Payments will not work.")
    print(f"   PAYPAL_CLIENT_ID: {'Set' if PAYPAL_CLIENT_ID else 'Not set'}")
    print(f"   PAYPAL_CLIENT_SECRET: {'Set' if PAYPAL_CLIENT_SECRET else 'Not set'}")
    print(f"   PAYPAL_MODE: {PAYPAL_MODE}")
else:
    print("✅ PayPal configured")
    print(f"   Mode: {PAYPAL_MODE}")
    print(f"   Client ID starts with: {PAYPAL_CLIENT_ID[:10] if PAYPAL_CLIENT_ID else 'None'}...")
    
    # Warning for live mode
    if PAYPAL_MODE == "live":
        print("⚠️ WARNING: Using LIVE mode! Make sure your PayPal credentials are for LIVE, not sandbox!")
        if PAYPAL_CLIENT_ID and PAYPAL_CLIENT_ID.startswith("AUNBEKK"):
            print("   ⚠️ Client ID looks like sandbox credentials (starts with 'AUNBEKK') but mode is LIVE!")
    elif PAYPAL_MODE == "sandbox":
        print("ℹ️ Using SANDBOX mode for testing")


# ------------------------------------
# Admin web UI (login + dashboard)
# ------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

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
# Payment routes
# -----------------------

@app.route("/buy/<item>", methods=["GET", "POST"])
def buy(item):
    prices = {
        "test": {"amount": "0.01", "description": "Test Purchase", "days": 1},
        "1month": {"amount": "2.00", "description": "1 Month Subscription", "days": 30},
        "2months": {"amount": "4.00", "description": "2 Months Subscription", "days": 60},
        "3months": {"amount": "5.00", "description": "3 Months Subscription", "days": 90},
        "1year": {"amount": "10.00", "description": "1 Year Subscription", "days": 365},
        "rawcode": {"amount": "20.00", "description": "Raw Code", "days": 0},  # Permanent license
        "custombot": {"amount": "15.00", "description": "Custom Bot", "days": 0}  # Permanent license
    }
    
    if item not in prices:
        return "Invalid item", 400
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        
        # Store in session
        session["payment_username"] = username
        session["payment_item"] = item
        
        return redirect(url_for("pay", item=item))
    
    return render_template("buy.html", item=item, price=prices[item])

@app.route("/pay/<item>", methods=["GET"])
def pay(item):
    username = session.get("payment_username")
    if not username:
        return redirect(url_for("buy", item=item))
    
    # Check PayPal credentials
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        return "PayPal not configured. Please check .env file.", 500
    
    prices = {
        "test": {"amount": "0.01", "description": "Test Purchase"},
        "1month": {"amount": "2.00", "description": "1 Month Subscription"},
        "2months": {"amount": "4.00", "description": "2 Months Subscription"},
        "3months": {"amount": "5.00", "description": "3 Months Subscription"},
        "1year": {"amount": "10.00", "description": "1 Year Subscription"},
        "rawcode": {"amount": "20.00", "description": "Raw Code (Permanent)"},
        "custombot": {"amount": "15.00", "description": "Custom Bot (Permanent)"}
    }
    
    if item not in prices:
        return "Invalid item", 400
    
    price = prices[item]
    
    # Create PayPal payment
    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {"payment_method": "paypal"},
        "redirect_urls": {
            "return_url": url_for("payment_success", _external=True),
            "cancel_url": url_for("payment_cancel", _external=True)
        },
        "transactions": [{
            "item_list": {
                "items": [{
                    "name": price["description"],
                    "sku": item,
                    "price": price["amount"],
                    "currency": "EUR",
                    "quantity": 1
                }]
            },
            "amount": {
                "total": price["amount"],
                "currency": "EUR"
            },
            "description": f"{price['description']} for {username}"
        }]
    })
    
    if payment.create():
        # Find approval URL
        for link in payment.links:
            if link.rel == "approval_url":
                return redirect(link.href)
    else:
        error_details = getattr(payment, 'error', {})
        error_msg = f"PayPal Error: {error_details}"
        print(f"PayPal payment creation failed: {error_msg}")
        print(f"Mode: {PAYPAL_MODE}")
        print(f"Client ID starts with: {PAYPAL_CLIENT_ID[:10] if PAYPAL_CLIENT_ID else 'None'}...")
        return f"Payment creation failed. Check PayPal credentials for mode '{PAYPAL_MODE}'. Error: {error_msg}", 500


def generate_download_token(username, item, ttl=3600):
    payload = {
        "u": username,
        "i": item,
        "exp": int(time.time()) + ttl
    }
    data = json.dumps(payload, separators=(",", ":")).encode()

    sig = hmac.new(
        DOWNLOAD_SECRET.encode(),
        data,
        hashlib.sha256
    ).digest()

    token = base64.urlsafe_b64encode(data + b"." + sig).decode()
    return token


@app.route("/payment/success")
def payment_success():
    username = session.get("payment_username", "Customer")
    item = session.get("payment_item", "RXZBot")

    if not username or not item:
        abort(400)

    token = generate_download_token(username, item)
    activate_license(username, item)
    return render_template(
        "payment_success.html",
        username=username,
        download_token=token
    )


@app.route("/payment/cancel")
def payment_cancel():
    # Clear session
    session.pop("payment_username", None)
    session.pop("payment_item", None)
    return render_template("payment_cancel.html")

@app.route("/download")
def download():
    token = request.args.get("token")
    if not token:
        abort(403)

    payload = verify_download_token(token)
    if not payload:
        abort(403)

    return send_file("files/rxzbot.zip", as_attachment=True)


def activate_license(username, item):
    days_map = {
        "test": 1,
        "1month": 30,
        "2months": 60,
        "3months": 90,
        "1year": 365,
        "rawcode": 0,  # Permanent
        "custombot": 0  # Permanent
    }
    
    days = days_map.get(item, 30)
    
    users = load_users()
    existing = find_user(users, username)
    
    # Special handling for permanent items
    if item in ["rawcode", "custombot"]:
        expires = "2099-12-31"  # Permanent license
        if existing:
            existing["expires"] = expires
        else:
            users.append({"username": username, "expires": expires})
    else:
        # Normal subscription logic
        if existing:
            # Extend existing
            current_expires = datetime.strptime(existing["expires"], "%Y-%m-%d")
            new_expires = current_expires + timedelta(days=days)
            existing["expires"] = new_expires.strftime("%Y-%m-%d")
        else:
            # New user
            expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            users.append({"username": username, "expires": expires})
    
    save_users(users)
    log_event(f"payment activated: {username} for {item}")


def verify_download_token(token):
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        data, sig = raw.rsplit(b".", 1)

        expected = hmac.new(
            DOWNLOAD_SECRET.encode(),
            data,
            hashlib.sha256
        ).digest()

        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(data.decode())
        if payload["exp"] < int(time.time()):
            return None

        return payload
    except Exception:
        return None



@app.route("/debug")
@login_required
def debug():
    """Debug route to check configuration"""
    info = {
        "env_file_exists": os.path.exists('.env'),
        "paypal_client_id_set": bool(PAYPAL_CLIENT_ID),
        "paypal_client_id_prefix": PAYPAL_CLIENT_ID[:10] if PAYPAL_CLIENT_ID else None,
        "paypal_client_secret_set": bool(PAYPAL_CLIENT_SECRET),
        "paypal_mode": PAYPAL_MODE,
        "secret_key_set": bool(app.secret_key),
        "admin_password_set": bool(ADMIN_PASSWORD),
        "github_token_set": bool(GITHUB_TOKEN)
    }
    return jsonify(info)

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

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin_page"))
        else:
            error = "Incorrect password."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/test")
def test_page():
    return render_template("index.html", show_test=True)

@app.route("/admin")
@login_required
def admin_page():
    return render_template("admin.html")

@app.route("/admin/add", methods=["POST"])
@login_required
def admin_add():
    username = request.form.get("username", "").strip()
    expires = request.form.get("expires", "").strip()
    duration = request.form.get("duration", "").strip()

    if not username:
        return redirect(url_for("admin_page"))

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
    return redirect(url_for("admin_page"))

@app.route("/admin/delete/<username>", methods=["GET"])
@login_required
def admin_delete(username):
    users = load_users()
    users = [u for u in users if u["username"].lower() != username.lower()]
    save_res = save_users(users)
    log_event(f"web delete: {username}")
    return redirect(url_for("admin_page"))

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
    """Extend an existing user's access by X days"""
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    days = body.get("days")
    
    # Validation
    if not username:
        return jsonify({"error": "username missing"}), 400
    
    if not days or not isinstance(days, int) or days <= 0:
        return jsonify({"error": "invalid days value"}), 400
    
    # Load users
    users = load_users()
    user = find_user(users, username)
    
    # Check if user exists
    if not user:
        return jsonify({"error": f"User '{username}' not found"}), 404
    
    try:
        # Parse current expiry date
        current_expiry = parse_date(user["expires"])
        
        # If date has already passed, start from today
        if current_expiry < datetime.now():
            base_date = datetime.now()
            print(f"⏰ User '{username}' was expired, extending from today")
        else:
            base_date = current_expiry
            print(f"📅 User '{username}' is active, extending from {user['expires']}")
        
        # Add the days
        new_expiry = base_date + timedelta(days=days)
        new_expiry_str = new_expiry.strftime("%Y-%m-%d")
        
        # Update the user
        user["expires"] = new_expiry_str
        
        # Save to GitHub
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
PING_ADMIN_URL = os.getenv("PING_ADMIN_URL", "http://auth-server-aj8k.onrender.com/admin")
try:
    PING_ADMIN_INTERVAL = int(os.getenv("PING_ADMIN_INTERVAL", "300"))
except Exception:
    PING_ADMIN_INTERVAL = 300
PING_ADMIN_ENABLED = os.getenv("PING_ADMIN_ENABLED", "1").lower() in ("1", "true", "yes", "on")

# In-memory logs and ping state
LOGS = deque(maxlen=500)
RECENT_CONN = deque(maxlen=300)

def log_event(msg, level="info"):
    """Store a structured log and print to console."""
    ts = (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d %H:%M:%SZ")
    entry = {"ts": ts, "msg": str(msg), "level": level}
    LOGS.appendleft(entry)
    print(f"[{ts}] [{level.upper()}] {msg}")

def record_connection(username, ip, status):
    """Record a recent connection attempt."""
    ts = (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d %H:%M:%SZ")
    entry = {"ts": ts, "username": username, "ip": ip, "status": status}
    RECENT_CONN.appendleft(entry)
    lvl = "info" if status == "authorized" else "warn"
    log_event(f"conn {status}: {username} @{ip}", level=lvl)
    
    if status == "authorized":
        stats = load_stats()
        stats[username] = stats.get(username, 0) + 1
        save_stats(stats)
        
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
    session_req = requests.Session()
    while not stop_event.is_set():
        now = datetime.utcnow() + CET_OFFSET
        if now.hour == 300 and now.minute < 30:
            log_event("Skipping ping as it's between 3:00 and 3:30 CET")
        else:
            try:
                start = time.time()
                r = session_req.get(url, timeout=10)
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

@app.route("/api/ping", methods=["POST"])
@login_required
def api_ping():
    """Trigger a manual ping"""
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
    return jsonify(list(LOGS))

@app.route("/api/recent", methods=["GET"])
@login_required
def api_recent():
    """Recent connection attempts"""
    return jsonify(list(RECENT_CONN))

@app.route("/api/stats", methods=["GET"])
@login_required
def api_stats():
    """Return user connection stats"""
    stats = load_stats()
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    return jsonify(sorted_stats)

# Start background ping if configured
if PING_ADMIN_ENABLED:
    start_ping_thread()
else:
    print("ℹ️ ping_admin is disabled (PING_ADMIN_ENABLED not set)")

# Schedule shutdown at 3:30 AM CET every day
def shutdown_at_3am():
    while True:
        now = datetime.utcnow() + CET_OFFSET
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
    app.run(host="0.0.0.0", port=port, debug=True)  # DEBUG MODE ACTIVÉ