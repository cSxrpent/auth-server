import os
import json
import base64
import bcrypt
import requests
import time
import threading
import secrets
import string
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
from dotenv import load_dotenv
import hmac
import hashlib
import base64
import html
from wolvesville_api import wolvesville_api
from token_manager import token_manager
import db_helper
from db_helper import (
    load_users, save_users, find_user,
    load_keys, save_keys, find_key,
    load_testimonials, save_testimonials,
    get_user_by_email, create_user, verify_user_password,
    get_user_accounts, add_account_to_user, remove_account_from_user,
    get_license,
    pause_license, resume_license,
    get_user_xp,
    load_stats, save_stats,
    load_last_connected, save_last_connected,
    save_log, get_recent_logs,
    save_recent_connection, get_recent_connections,
    get_user_by_player_id, update_user_player_id, update_user_nickname,
    get_custom_message, set_custom_message,
    get_latest_bot_version, set_latest_bot_version, update_user_bot_version
)
from gem_account_manager import gem_account_manager
from coupon_manager import coupon_manager
from shop_data_fetcher import shop_data_fetcher


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

# Secrets & storage config from env (safer)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_replace_in_prod")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_locally")
DOWNLOAD_SECRET = app.secret_key
# PayPal config
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live
PAYPAL_TEST_MODE = os.getenv("PAYPAL_TEST_MODE", "false").lower() == "true"  # Skip actual PayPal calls for testing
TESTIMONIALS_FILE = "testimonials.json"  # testimonials storage

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
        
        
# Simple cache
_cache = {}
_cache_time = {}

def get_cached_or_fetch(key, fetch_func, ttl=30):
    """Cache data for TTL seconds"""
    now = datetime.now()
    
    if key in _cache:
        cache_age = (now - _cache_time[key]).total_seconds()
        if cache_age < ttl:
            print(f"✓ Cache hit: {key}")
            return _cache[key]
    
    print(f"⟳ Fetching fresh: {key}")
    data = fetch_func()
    _cache[key] = data
    _cache_time[key] = now
    return data

# ------------------------------------
# Admin web UI (login + dashboard)
# ------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Allow either admin session or authenticated user session
        if not (session.get("logged_in") or session.get("user_id")):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# Storage integration — runtime storage is DB-backed via `db_helper`

USERS_FILE = "users.json"  # local fallback file
KEYS_FILE = "keys.json"  # activation keys storage
STATS_FILE = "stats.json"  # track user connection counts
LAST_CONNECTED_FILE = "last_connected.json"  # track last connection per user

CET_OFFSET = timedelta(hours=1)  # CET = UTC+1 in winter

# -----------------------
# Keys management helpers
# -----------------------
# Storage helper functions — use DB-backed `db_helper` instead.

def generate_key():
    """Generate a random 6-character key with uppercase, lowercase, and numbers."""
    characters = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(6))

def find_key(keys, key_code):
    """Find a key by its code."""
    for k in keys:
        if k["code"] == key_code:
            return k
    return None


# -----------------------
# Utilities
# -----------------------

def search_wolvesville_player(username):
    """Search for player using managed tokens"""
    return wolvesville_api.search_player(username)

def get_wolvesville_player_profile(player_id):
    """Get player profile using managed tokens"""
    return wolvesville_api.get_player_profile(player_id)


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")
        
# -----------------------
# Key redemption routes
# -----------------------

@app.route("/redeem", methods=["GET", "POST"])
def redeem():
    """Page to redeem an activation key"""
    if request.method == "POST":
        key_code = request.form.get("key", "").strip()
        username = request.form.get("username", "").strip()
        
        if not key_code or not username:
            return render_template("redeem.html", error="Key and username are required")
        
        # Load keys
        keys = load_keys()
        # Case-insensitive key lookup
        key = None
        for k in keys:
            if k["code"].lower() == key_code.lower():
                key = k
                break
        
        if not key:
            log_event(f"redeem fail: key '{key_code}' not found", level="warn")
            return render_template("redeem.html", error="Invalid key")
        
        if key.get("used"):
            log_event(f"redeem fail: key '{key_code}' already used", level="warn")
            return render_template("redeem.html", error="This key has already been used")
        
        # Activate the key
        days = key["duration"]
        users = load_users()
        existing = find_user(users, username)

        today = datetime.now()

        if existing:
            # User exists - check if license is still valid or expired
            try:
                current_expires = datetime.strptime(existing["expires"], "%Y-%m-%d")
                
                # If license is still valid, extend from expiry date
                if current_expires > today:
                    new_expires = current_expires + timedelta(days=days)
                    log_event(f"Key redemption - Extended valid license: {username} from {existing['expires']} to {new_expires.strftime('%Y-%m-%d')}")
                else:
                    # License expired, start fresh from today
                    new_expires = today + timedelta(days=days)
                    log_event(f"Key redemption - Renewed expired license: {username} from today to {new_expires.strftime('%Y-%m-%d')}")
                
                existing["expires"] = new_expires.strftime("%Y-%m-%d")
            except Exception as e:
                log_event(f"Key redemption - Error parsing date for {username}, starting fresh: {e}", level="warn")
                new_expires = today + timedelta(days=days)
                existing["expires"] = new_expires.strftime("%Y-%m-%d")
        else:
            # New user - create from today
            expires = (today + timedelta(days=days)).strftime("%Y-%m-%d")
            users.append({"username": username, "expires": expires})
            log_event(f"Key redemption - New user created: {username} expires {expires}")
        
        # Mark key as used
        key["used"] = True
        key["used_by"] = username
        key["used_at"] = (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d %H:%M:%SZ")
        
        # Save everything
        save_users(users)
        save_keys(keys)
        
        log_event(f"key redeemed: {key_code} by {username} for {days} days")
        
        # Generate download token
        token = generate_download_token(username, f"{days}days")
        
        return render_template("payment_success.html", username=username, download_token=token, from_key=True)
    
    return render_template("redeem.html", error=None)

@app.route("/testimonial-success")
def testimonial_success():
    """Success page after submitting a testimonial"""
    return render_template("testimonial_success.html")


# -----------------------
# Admin API for keys
# -----------------------

@app.route("/api/keys", methods=["GET"])
@login_required
def api_get_keys():
    """Get all activation keys"""
    keys = load_keys()
    return jsonify(keys)

@app.route("/api/keys/generate", methods=["POST"])
@login_required
def api_generate_key():
    """Generate a new activation key"""
    body = request.get_json() or {}
    duration = body.get("duration")
    
    if not duration or not isinstance(duration, int) or duration <= 0:
        return jsonify({"error": "Invalid duration"}), 400
    
    # Generate unique key
    keys = load_keys()
    key_code = generate_key()
    
    # Ensure uniqueness
    while find_key(keys, key_code):
        key_code = generate_key()
    
    # Create key object
    new_key = {
        "code": key_code,
        "duration": duration,
        "created": (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d %H:%M:%SZ"),
        "used": False
    }
    
    keys.append(new_key)
    save_keys(keys)
    
    log_event(f"key generated: {key_code} for {duration} days")
    
    return jsonify({"message": "Key generated", "key": new_key}), 200

@app.route("/api/keys/delete", methods=["POST"])
@login_required
def api_delete_key():
    """Delete an activation key"""
    body = request.get_json() or {}
    key_code = body.get("code", "").strip()
    
    if not key_code:
        return jsonify({"error": "Key code required"}), 400
    
    keys = load_keys()
    keys = [k for k in keys if k["code"] != key_code]
    save_keys(keys)
    
    log_event(f"key deleted: {key_code}")
    
    return jsonify({"message": "Key deleted"}), 200

# -----------------------
# Payment routes
# -----------------------

@app.route("/buy/<item>", methods=["GET", "POST"])
def buy(item):
    prices = {
        "1month": {"amount": "2.00", "description": "1 Month Subscription", "days": 30},
        "2months": {"amount": "4.00", "description": "2 Months Subscription", "days": 60},
        "3months": {"amount": "5.00", "description": "3 Months Subscription", "days": 90},
        "1year": {"amount": "10.00", "description": "1 Year Subscription", "days": 365},
        "lifetime": {"amount": "20.00", "description": "Lifetime bot with updates", "days": 0},  # Permanent license
        "custombot": {"amount": "25.00", "description": "Custom Bot", "days": 0}  # Permanent license
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
        "test": {"amount": "0.05", "description": "Test Purchase"},
        "1month": {"amount": "2.00", "description": "1 Month Subscription"},
        "2months": {"amount": "4.00", "description": "2 Months Subscription"},
        "3months": {"amount": "5.00", "description": "3 Months Subscription"},
        "1year": {"amount": "10.00", "description": "1 Year Subscription"},
        "lifetime": {"amount": "20.00", "description": "Lifetime bot with updates (Permanent)"},
        "custombot": {"amount": "25.00", "description": "Custom Bot (Permanent)"}
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
    payment_id = request.args.get("paymentId")
    payer_id = request.args.get("PayerID")

    if not payment_id or not payer_id:
        abort(400)

    payment = paypalrestsdk.Payment.find(payment_id)

    if payment.execute({"payer_id": payer_id}):
        if payment.state != "approved":
            abort(400)

        username = session.get("payment_username")
        item = session.get("payment_item")

        if not username or not item:
            abort(400)

        activate_license(username, item)
        token = generate_download_token(username, item)

        return render_template(
            "payment_success.html",
            username=username,
            download_token=token
        )
    else:
        print(payment.error)
        abort(500)



@app.route("/payment/cancel")
def payment_cancel():
    # Clear session
    session.pop("payment_username", None)
    session.pop("payment_item", None)
    return render_template("payment_cancel.html")

@app.route("/download")
def download():
    token = request.args.get("token")
    
    # ✅ LOG THE RAW TOKEN
    log_event(f"Download attempt - Token: {token[:50] if token else 'MISSING'}... (len={len(token) if token else 0})", level="info")
    
    if not token:
        log_event("Download failed: No token in request", level="error")
        abort(403)

    # ✅ TRY TO FIX COMMON TOKEN ISSUES
    # Some browsers/proxies replace spaces with +, or URL-encode the token
    token = token.strip()  # Remove whitespace
    token = token.replace(' ', '+')  # Fix space->plus conversion
    
    # Try to decode and verify
    payload = verify_download_token(token)
    
    if not payload:
        # ✅ LOG EXACTLY WHAT FAILED
        log_event(f"Download failed: Token verification failed for token: {token[:50]}...", level="error")
        
        # Try URL-decoding the token (in case browser double-encoded it)
        import urllib.parse
        decoded_token = urllib.parse.unquote(token)
        
        if decoded_token != token:
            log_event(f"Trying URL-decoded token: {decoded_token[:50]}...", level="info")
            payload = verify_download_token(decoded_token)
        
        if not payload:
            abort(403)

    log_event(f"Download successful for user: {payload.get('u')}", level="info")

    file_path = "files/rxzbot.zip"
    
    if not os.path.exists(file_path):
        log_event(f"Download failed: File not found at {file_path}", level="error")
        abort(404, description="Download file not found")
    
    if not os.access(file_path, os.R_OK):
        log_event(f"Download failed: No read permission for {file_path}", level="error")
        abort(500, description="File permission error")
    
    try:
        return send_file(
            file_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name='rxzbot.zip'
        )
    except Exception as e:
        log_event(f"Download failed: {e}", level="error")
        abort(500, description=f"Download error: {str(e)}")


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
        # Normal subscription logic with PROPER RENEWAL
        today = datetime.now()
        
        if existing:
            # User exists - check if license is still valid or expired
            try:
                current_expires = datetime.strptime(existing["expires"], "%Y-%m-%d")
                
                # If license is still valid, extend from expiry date
                if current_expires > today:
                    new_expires = current_expires + timedelta(days=days)
                    log_event(f"Extended valid license: {username} from {existing['expires']} to {new_expires.strftime('%Y-%m-%d')}")
                else:
                    # License expired, start fresh from today
                    new_expires = today + timedelta(days=days)
                    log_event(f"Renewed expired license: {username} from today to {new_expires.strftime('%Y-%m-%d')}")
                
                existing["expires"] = new_expires.strftime("%Y-%m-%d")
            except Exception as e:
                # If date parsing fails, start fresh
                log_event(f"Error parsing date for {username}, starting fresh: {e}", level="warn")
                new_expires = today + timedelta(days=days)
                existing["expires"] = new_expires.strftime("%Y-%m-%d")
        else:
            # New user - create from today
            expires = (today + timedelta(days=days)).strftime("%Y-%m-%d")
            users.append({"username": username, "expires": expires})
            log_event(f"New user created: {username} expires {expires}")
    
    save_users(users)
    log_event(f"License activated: {username} for {item} ({days} days)")


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
    
    # Get latest bot version from recent connections
    latest_version = "Unknown"
    try:
        recent_logs = db_helper.get_recent_logs(limit=100)
        for log in recent_logs:
            if "bot version" in log.get("msg", ""):
                # Extract version from log message
                import re
                match = re.search(r'v\d+\.\d+\.\d+', log["msg"])
                if match:
                    latest_version = match.group(0)
                    break
    except:
        pass
    
    info = {
        "env_file_exists": os.path.exists('.env'),
        "paypal_mode": PAYPAL_MODE,
        "admin_password_set": bool(ADMIN_PASSWORD),
        "latest_bot_version": latest_version  
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
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            session["logged_in"] = True
            return redirect(url_for("admin_page"))
        else:
            error = "Incorrect password."
    return render_template("login.html", error=error)


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
    
    try:
        with db_helper.get_db() as db:
            from init_database import User
            from sqlalchemy import func
            # Case-insensitive search
            user = db.query(User).filter(func.lower(User.username) == username.lower()).first()
            if user:
                db.delete(user)
                db.commit()
                log_event(f"api_delete: {username}")
                return jsonify({"message": "deleted", "username": username}), 200
            else:
                return jsonify({"error": "user not found"}), 404
    except Exception as e:
        log_event(f"api_delete error: {username} - {e}", level="error")
        return jsonify({"error": str(e)}), 500

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
        
        # Persist changes to storage
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
PING_ADMIN_URL = os.getenv("PING_ADMIN_URL", "https://rxzbot.com/admin")
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
    
    # Save to database
    try:
        db_helper.save_log(ts, str(msg), level)
    except Exception as e:
        print(f"Failed to save log to database: {e}")

def record_connection(username, ip, status):
    """Record a recent connection attempt."""
    ts = (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d %H:%M:%SZ")
    entry = {"ts": ts, "username": username, "ip": ip, "status": status}
    RECENT_CONN.appendleft(entry)
    lvl = "info" if status == "authorized" else "warn"
    log_event(f"conn {status}: {username} @{ip}", level=lvl)
    
    # Save to database
    try:
        db_helper.save_recent_connection(ts, username, ip, status)
    except Exception as e:
        print(f"Failed to save connection to database: {e}")
    
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

def send_wolvesville_gift(username, product, message):
    """
    Send a gift to a Wolvesville user using the gem account manager
    
    Args:
        username: Wolvesville username
        product: Product dict with 'type', 'name', 'price', 'cost', etc.
        message: Gift message
    
    Returns:
        dict: API response from Wolvesville
    """
    try:
        # Use the gem account manager with automatic account switching
        result = gem_account_manager.send_gift_with_auto_switch(username, product, message)
        
        log_event(f"Gift sent: {product['name']} to {username} ({product['cost']} gems)")
        
        return result
            
    except Exception as e:
        log_event(f"send_wolvesville_gift error: {e}", level="error")
        raise

@app.route('/admin/gem-accounts')
@login_required
def admin_gem_accounts():
    """Admin page for managing gem accounts"""
    return render_template('admin_gem_accounts.html')

@app.route('/api/gem-accounts', methods=['GET'])
@login_required
def api_get_gem_accounts():
    """Get all gem accounts"""
    accounts = gem_account_manager.get_all_gem_accounts()
    # Don't send passwords to frontend
    for acc in accounts:
        acc.pop('password', None)
    return jsonify(accounts)

@app.route('/api/gem-accounts/add', methods=['POST'])
@login_required
def api_add_gem_account():
    """Add a new gem account"""
    body = request.get_json() or {}
    account_number = body.get('account_number')
    email = body.get('email')
    password = body.get('password')
    
    if not all([account_number, email, password]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if gem_account_manager.add_gem_account(account_number, email, password):
        log_event(f"Gem account added: #{account_number} ({email})")
        return jsonify({'success': True, 'message': 'Account added successfully'})
    else:
        return jsonify({'error': 'Failed to add account (may already exist)'}), 400

@app.route('/api/gem-accounts/recharge', methods=['POST'])
@login_required
def api_recharge_gem_account():
    """Recharge an account's gems"""
    body = request.get_json() or {}
    account_id = body.get('account_id')
    gems_amount = body.get('gems_amount', 5000)
    
    if not account_id:
        return jsonify({'error': 'Account ID required'}), 400
    
    if gem_account_manager.recharge_account(account_id, gems_amount):
        log_event(f"Gem account #{account_id} recharged to {gems_amount} gems")
        return jsonify({'success': True, 'message': 'Account recharged'})
    else:
        return jsonify({'error': 'Failed to recharge account'}), 400

@app.route('/api/gem-accounts/toggle', methods=['POST'])
@login_required
def api_toggle_gem_account():
    """Enable/disable a gem account"""
    body = request.get_json() or {}
    account_id = body.get('account_id')
    is_active = body.get('is_active')
    
    if not account_id or is_active is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        with db_helper.get_db() as db:
            from init_database import GemAccount
            
            account = db.query(GemAccount).filter_by(id=account_id).first()
            if not account:
                return jsonify({'error': 'Account not found'}), 404
            
            account.is_active = is_active
            db.commit()
            
            status = 'enabled' if is_active else 'disabled'
            log_event(f"Gem account #{account.account_number} {status}")
            
            return jsonify({'success': True, 'message': f'Account {status}'})
            
    except Exception as e:
        log_event(f"Error toggling gem account: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gem-accounts/delete', methods=['POST'])
@login_required
def api_delete_gem_account():
    """Delete a gem account"""
    body = request.get_json() or {}
    account_id = body.get('account_id')
    
    if not account_id:
        return jsonify({'error': 'Account ID required'}), 400
    
    try:
        with db_helper.get_db() as db:
            from init_database import GemAccount
            
            account = db.query(GemAccount).filter_by(id=account_id).first()
            if not account:
                return jsonify({'error': 'Account not found'}), 404
            
            account_number = account.account_number
            db.delete(account)
            db.commit()
            
            log_event(f"Gem account #{account_number} deleted")
            
            return jsonify({'success': True, 'message': 'Account deleted'})
            
    except Exception as e:
        log_event(f"Error deleting gem account: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gem-accounts/stats', methods=['GET'])
@login_required
def api_gem_accounts_stats():
    """Get gem accounts statistics"""
    accounts = gem_account_manager.get_all_gem_accounts()
    
    total_gems = sum(acc['gems_remaining'] for acc in accounts)
    active_accounts = len([acc for acc in accounts if acc['is_active']])
    total_accounts = len(accounts)
    
    return jsonify({
        'total_accounts': total_accounts,
        'active_accounts': active_accounts,
        'total_gems': total_gems,
        'average_gems': total_gems // total_accounts if total_accounts > 0 else 0
    })
    
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
    """Get recent logs from database"""
    try:
        logs = db_helper.get_recent_logs(limit=500)
        return jsonify(logs)
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return jsonify([])

@app.route("/api/recent", methods=["GET"])
@login_required
def api_recent():
    """Recent connection attempts from database"""
    try:
        connections = db_helper.get_recent_connections(limit=300)
        return jsonify(connections)
    except Exception as e:
        print(f"Error fetching recent connections: {e}")
        return jsonify([])

@app.route("/api/stats", methods=["GET"])
@login_required
def api_stats():
    """Return user connection stats"""
    stats = load_stats()
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    return jsonify(sorted_stats)

    # -----------------------
# Testimonials API
# -----------------------

@app.route("/api/testimonials", methods=["GET"])
def api_get_testimonials():
    """Get testimonials - public gets approved only, logged in gets all"""
    testimonials = load_testimonials()
    
    # If admin is logged in, return all testimonials (including pending)
    if session.get("logged_in"):
        # Sort by approved status (pending first) then by date
        testimonials.sort(key=lambda x: (x.get('approved', False), x.get('date', '')), reverse=True)
        return jsonify(testimonials)
    
    # Public endpoint - only return approved testimonials
    approved = [t for t in testimonials if t.get('approved', False) == True]
    approved.sort(key=lambda x: x.get('date', ''), reverse=True)
    return jsonify(approved)

@app.route("/api/testimonials/add", methods=["POST"])
@login_required
def api_add_testimonial():
    """Add a new testimonial"""
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    rating = body.get("rating", 5)
    comment = (body.get("comment") or "").strip()
    anonymous = body.get("anonymous", False)
    
    if not username:
        return jsonify({"error": "username missing"}), 400
    if not comment:
        return jsonify({"error": "comment missing"}), 400
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"error": "invalid rating (must be 1-5)"}), 400
    
    testimonials = load_testimonials()
    
    # Generate unique ID
    import uuid
    testimonial_id = str(uuid.uuid4())[:8]
    
    comment = html.escape(comment.strip())
    
    new_testimonial = {
        "id": testimonial_id,
        "username": username,
        "rating": rating,
        "comment": comment,
        "anonymous": anonymous,
        "date": (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d"),
        "approve": True
    }
    
    testimonials.append(new_testimonial)
    save_testimonials(testimonials)
    
    log_event(f"testimonial added: {username} ({rating}★)")
    
    return jsonify({"message": "ok", "testimonial": new_testimonial}), 200

@app.route("/api/testimonials/delete", methods=["POST"])
@login_required
def api_delete_testimonial():
    """Delete a testimonial"""
    body = request.get_json() or {}
    testimonial_id = (body.get("id") or "").strip()
    
    if not testimonial_id:
        return jsonify({"error": "id missing"}), 400
    
    testimonials = load_testimonials()
    testimonials = [t for t in testimonials if t.get("id") != testimonial_id]
    save_testimonials(testimonials)
    
    log_event(f"testimonial deleted: {testimonial_id}")
    
    return jsonify({"message": "deleted"}), 200

@app.route("/api/testimonials/submit", methods=["POST"])
def api_submit_testimonial():
    """Public endpoint for users to submit testimonials (pending approval) + 3 days bonus"""
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    rating = body.get("rating", 5)
    comment = (body.get("comment") or "").strip()
    anonymous = body.get("anonymous", False)
    
    # Validation
    if not username:
        return jsonify({"error": "Username is required"}), 400
    if not comment:
        return jsonify({"error": "Comment is required"}), 400
    if len(comment) < 10:
        return jsonify({"error": "Review must be at least 10 characters"}), 400
    if len(comment) > 500:
        return jsonify({"error": "Review must be less than 500 characters"}), 400
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"error": "Invalid rating"}), 400
    
    # Check if user exists
    users = load_users()
    user = find_user(users, username)
    if not user:
        return jsonify({"error": "User not found. Please use your registered username."}), 404
    
    testimonials = load_testimonials()
    
    # Check if user already submitted a review (ONE REVIEW PER USER MAX)
    existing = next((t for t in testimonials if t.get('username', '').lower() == username.lower()), None)
    if existing:
        return jsonify({"error": "You have already submitted a review. Thank you!"}), 400
    
    # Generate unique ID
    import uuid
    testimonial_id = str(uuid.uuid4())[:8]
    
    new_testimonial = {
        "id": testimonial_id,
        "username": username,
        "rating": rating,
        "comment": comment,
        "anonymous": anonymous,
        "date": (datetime.utcnow() + CET_OFFSET).strftime("%Y-%m-%d"),
        "approved": False  # PENDING - admin must approve
    }
    
    testimonials.append(new_testimonial)
    save_testimonials(testimonials)
    
    # 🎁 BONUS: Add 3 days to user's license as a thank you!
    try:
        today = datetime.now()
        current_expires = datetime.strptime(user["expires"], "%Y-%m-%d")
        
        # If license is still valid, extend from expiry date
        if current_expires > today:
            new_expires = current_expires + timedelta(days=3)
        else:
            # If expired, add 3 days from today
            new_expires = today + timedelta(days=3)
        
        user["expires"] = new_expires.strftime("%Y-%m-%d")
        save_users(users)
        
        log_event(f"testimonial bonus: {username} got +3 days (new expiry: {user['expires']})")
    except Exception as e:
        log_event(f"Error adding bonus to {username}: {e}", level="error")
    
    # Get client IP
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    log_event(f"testimonial submitted (pending): {username} ({rating}★) from {ip}")
    
    return jsonify({
        "success": True,
        "message": "Thank you! Your review has been submitted.",
        "bonus": "+3 days added to your license!",
        "redirect": "/testimonial-success"
    }), 200

@app.route("/api/testimonials/approve", methods=["POST"])
@login_required
def api_approve_testimonial():
    """Approve a pending testimonial"""
    body = request.get_json() or {}
    testimonial_id = (body.get("id") or "").strip()
    
    if not testimonial_id:
        return jsonify({"error": "id missing"}), 400
    
    testimonials = load_testimonials()
    testimonial = next((t for t in testimonials if t.get("id") == testimonial_id), None)
    
    if not testimonial:
        return jsonify({"error": "Testimonial not found"}), 404
    
    testimonial["approved"] = True
    save_testimonials(testimonials)
    
    log_event(f"testimonial approved: {testimonial_id}")
    
    return jsonify({"message": "approved"}), 200

# Start background ping if configured
if PING_ADMIN_ENABLED:
    start_ping_thread()
else:
    print("ℹ️ ping_admin is disabled (PING_ADMIN_ENABLED not set)")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        # Create user in DB-backed credentials
        existing = db_helper.get_user_by_email(email)
        if existing:
            return render_template('register.html', error="Email already exists")

        # Hash password with bcrypt rounds=10
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=10)).decode('utf-8')

        ok = db_helper.create_user(email, hashed_password)
        if ok:
            # Initialize empty accounts relation handled by create_user()
            session['user_id'] = email
            session['user_email'] = email
            return redirect(url_for('dashboard'))
        else:
            return render_template('register.html', error="Registration failed")
    
    return render_template('register.html')

@app.route('/loginuser', methods=['GET', 'POST'])
def loginuser():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        # Verify using DB-backed helper (single DB query + bcrypt check)
        ok, user_email = db_helper.verify_user_password(email, password)
        if ok:
            session['user_id'] = user_email
            session['user_email'] = user_email
            return redirect(url_for('dashboard'))
        else:
            return render_template('loginuser.html', error="Invalid email or password")
    
    return render_template('loginuser.html')

@app.route('/dashboard')
def dashboard():
    # Minimal, fast dashboard render. Heavy data is lazy-loaded via API endpoints.
    if 'user_id' not in session:
        return redirect(url_for('loginuser'))

    return render_template('dashboard.html', email=session.get('user_email'))

@app.route('/api/license/pause', methods=['POST'])
def pause_license():
    """Pause license for an account"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({'success': False, 'error': 'Username required'}), 400

    # Verify ownership via DB
    email = session['user_id']
    user_accounts = db_helper.get_user_accounts(email)
    if username not in user_accounts:
        return jsonify({'success': False, 'error': 'Account not found'}), 403

    # Pause license via DB helper
    license_row = db_helper.get_license(username)
    if not license_row:
        return jsonify({'success': False, 'error': 'License not found'}), 404

    ok = db_helper.pause_license(username)
    if ok:
        log_event(f"License paused: {username}")
        return jsonify({'success': True, 'message': 'License paused'})

    return jsonify({'success': False, 'error': 'License already paused'}), 400

@app.route('/api/license/resume', methods=['POST'])
def resume_license():
    """Resume paused license"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({'success': False, 'error': 'Username required'}), 400

    # Verify ownership
    email = session['user_id']
    user_accounts = db_helper.get_user_accounts(email)
    if username not in user_accounts:
        return jsonify({'success': False, 'error': 'Account not found'}), 403

    license_row = db_helper.get_license(username)
    if not license_row:
        return jsonify({'success': False, 'error': 'License not found'}), 404

    ok = db_helper.resume_license(username)
    if ok:
        new = db_helper.get_license(username)
        new_expiry = new.get('expires') if new else None
        log_event(f"License resumed: {username} (new expiry: {new_expiry})")
        return jsonify({'success': True, 'message': 'License resumed', 'new_expiry': new_expiry})

    return jsonify({'success': False, 'error': 'License not paused'}), 400

@app.route('/api/license/extend', methods=['POST'])
def extend_license_user():
    """Extend license - redirects to payment page"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'error': 'Username required'}), 400
    
    # Store username in session for payment flow
    session['payment_username'] = username
    
    return jsonify({'success': True, 'redirect': '/buy/1month'})
    
from flask import render_template, request, session, redirect, url_for, jsonify
import secrets
import requests
import db_helper

# Store verification codes temporarily (in production, use Redis or database)
verification_sessions = {}

@app.route('/add_account', methods=['GET', 'POST'])
def add_account():
    """Route to add a Wolvesville account to user's dashboard"""
    # Check if user is logged in
    if 'user_email' not in session:
        return redirect(url_for('loginuser'))
    
    user_email = session['user_email']
    
    if request.method == 'GET':
        # Check if there's an active verification session IN FLASK SESSION
        if 'verification_data' in session:
            verification_data = session['verification_data']
            return render_template('add_account.html', 
                                 step='verify',
                                 verification_code=verification_data['code'],
                                 username=verification_data['username'])
        
        # Show initial form
        return render_template('add_account.html', step='username')
    
    # POST request - username submission
    username = request.form.get('username', '').strip()
    
    if not username:
        return render_template('add_account.html', 
                             step='username',
                             error='Please enter a username.')
    
    # Check if username exists in database with active license
    license_data = db_helper.get_license(username)
    
    if not license_data:
        return render_template('add_account.html',
                             step='username',
                             error='This username does not have an active license. Please activate a license key first.')
    
    # Check if license is expired
    from datetime import datetime
    try:
        expires_date = datetime.strptime(license_data['expires'], '%Y-%m-%d')
        if expires_date < datetime.now() and not license_data.get('paused', False):
            return render_template('add_account.html',
                                 step='username',
                                 error='This license has expired. Please renew your license first.')
    except Exception:
        pass
    
    # Check if account is already linked to this user
    existing_accounts = db_helper.get_user_accounts(user_email)
    
    if username in existing_accounts:
        return render_template('add_account.html',
                             step='username',
                             error='This account is already linked to your dashboard.')
    
    # Generate verification code
    verification_code = secrets.token_hex(3).upper()  # 6-character code
    
    # Store verification session IN FLASK SESSION (not in-memory dict)
    session['verification_data'] = {
        'username': username,
        'code': verification_code
    }
    
    # Redirect to the same route with GET to show verification step
    return redirect(url_for('add_account'))


@app.route('/verify_account', methods=['POST'])
def verify_account():
    """Verify account ownership by checking bio"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    user_email = session['user_email']
    
    # Get verification data from FLASK SESSION
    if 'verification_data' not in session:
        return jsonify({'success': False, 'error': 'No verification session found. Please start over.'}), 400
    
    verification_data = session['verification_data']
    username = verification_data['username']
    expected_code = verification_data['code']
    
    try:
        # Import the API helper
        from wolvesville_api import wolvesville_api
        
        # Search for player using authenticated API
        player_data = wolvesville_api.search_player(username)
        
        if not player_data:
            return jsonify({'success': False, 'error': 'Username not found on Wolvesville'}), 404
        
        # Get full profile with bio
        player_id = player_data.get('id')
        profile = wolvesville_api.get_player_profile(player_id)
        
        if not profile:
            return jsonify({'success': False, 'error': 'Failed to fetch profile from Wolvesville API'}), 400
        
        # Check bio for verification code
        bio = profile.get('personalMsg', '') or profile.get('profileDescription', '')
        
        if expected_code not in bio:
            return jsonify({'success': False, 'error': 'Verification code not found in your bio. Please add it and try again.'}), 400
        
        # Add account to user's dashboard
        success = db_helper.add_account_to_user(user_email, username)
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to add account to dashboard'}), 500
        
        # Clear verification data from session
        session.pop('verification_data', None)
        
        return jsonify({'success': True, 'message': 'Account verified and added successfully!'})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'An error occurred: {str(e)}'}), 500

@app.route('/xp/add', methods=['POST'])
def add_xp():
    try:
        data = request.json
        player_id = data.get('player_id')
        xp_amount = data.get('xp_amount')
        username = data.get('username')
        
        if not all([player_id, xp_amount, username]):
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400
        
        # ✅ VERIFY USER HAS VALID LICENSE BEFORE ALLOWING XP TRACKING
        license_data = db_helper.get_license(username)
        
        if not license_data:
            log_event(f"XP add rejected: username '{username}' not found in database", level="warn")
            return jsonify({'success': False, 'error': 'User not registered'}), 403
        
        # Check if license is expired or paused
        try:
            from datetime import datetime
            expires_date = datetime.strptime(license_data['expires'], '%Y-%m-%d')
            
            if license_data.get('paused', False):
                log_event(f"XP add rejected: username '{username}' license is paused", level="warn")
                return jsonify({'success': False, 'error': 'License is paused'}), 403
            
            if expires_date < datetime.now():
                log_event(f"XP add rejected: username '{username}' license expired on {license_data['expires']}", level="warn")
                return jsonify({'success': False, 'error': 'License expired'}), 403
                
        except Exception as e:
            log_event(f"XP add error: failed to parse license date for '{username}': {e}", level="error")
            return jsonify({'success': False, 'error': 'Invalid license data'}), 500
        
        # ✅ OPTIONAL: Verify player_id matches the registered one (if you use authv2)
        if license_data.get('player_id') and license_data['player_id'] != player_id:
            log_event(f"XP add rejected: player_id mismatch for '{username}'", level="warn")
            return jsonify({'success': False, 'error': 'Player ID mismatch'}), 403
        
        # Load XP data from DB
        xp_data, sha = db_helper.read_storage('user-XP.json')
        
        if username not in xp_data:
            xp_data[username] = {"daily": {}, "weekly": {}, "monthly": {}}
        
        # Get current date info
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-W%U')
        month = datetime.now().strftime('%Y-%m')
        
        # Update daily
        xp_data[username]['daily'][today] = xp_data[username]['daily'].get(today, 0) + xp_amount
        
        # Update weekly
        xp_data[username]['weekly'][week] = xp_data[username]['weekly'].get(week, 0) + xp_amount
        
        # Update monthly
        xp_data[username]['monthly'][month] = xp_data[username]['monthly'].get(month, 0) + xp_amount
        
        # Save to storage (DB)
        if db_helper.write_storage('user-XP.json', xp_data, sha):
            log_event(f"XP added: {username} +{xp_amount} XP", level="info")
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': 'Failed to save XP data'}), 500
        
    except Exception as e:
        log_event(f"Error in add_xp: {e}", level="error")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/dashboard/accounts', methods=['GET'])
@login_required
def api_dashboard_accounts():
    """Return accounts owned by the authenticated user (DB only)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    email = session['user_id']
    accounts = db_helper.get_user_accounts(email)
    return jsonify(accounts)

@app.route('/api/dashboard/unlink', methods=['POST'])
def api_dashboard_unlink():
    """Unlink account from user's dashboard"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'error': 'Username required'}), 400
    
    email = session['user_id']
    
    try:
        # Remove account from user's accounts list
        success = db_helper.remove_account_from_user(email, username)
        
        if success:
            log_event(f"Account unlinked: {username} from {email}")
            return jsonify({'success': True, 'message': 'Account unlinked successfully'})
        else:
            return jsonify({'success': False, 'error': 'Account not found or already unlinked'}), 404
            
    except Exception as e:
        log_event(f"Error unlinking account: {e}", level="error")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/license/<username>', methods=['GET'])
@login_required
def api_dashboard_license(username):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    email = session['user_id']
    accounts = db_helper.get_user_accounts(email)
    if username not in accounts:
        return jsonify({'error': 'Account not found'}), 403
    lic = db_helper.get_license(username)
    if not lic:
        return jsonify({'error': 'License not found'}), 404
    return jsonify(lic)


@app.route('/api/dashboard/xp/<username>', methods=['GET'])
@login_required
def api_dashboard_xp(username):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    email = session['user_id']
    accounts = db_helper.get_user_accounts(email)
    if username not in accounts:
        return jsonify({'error': 'Account not found'}), 403
    xp = db_helper.get_user_xp(username)
    return jsonify(xp)


@app.route('/api/dashboard/profile/<username>', methods=['GET'])
@login_required
def api_dashboard_profile(username):
    # This endpoint is the only one allowed to call Wolvesville API
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    email = session['user_id']
    accounts = db_helper.get_user_accounts(email)
    if username not in accounts:
        return jsonify({'error': 'Account not found'}), 403

    player = search_wolvesville_player(username)
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    profile = get_wolvesville_player_profile(player['id'])
    return jsonify(profile or {})

@app.route("/logout")
def logout():
    was_user = 'user_email' in session
    was_admin = session.get("logged_in", False)
    
    session.clear()
    
    # Prioritize user logout over admin
    if was_user:
        return redirect(url_for("loginuser"))
    elif was_admin:
        return redirect(url_for("login"))
    else:
        return redirect(url_for("index"))

@app.route("/authv2", methods=["GET"])
def authv2():
    """
    Enhanced authentication with player ID verification and bot version check
    """
    username = request.args.get("username")
    player_id = request.args.get("player_id")
    bot_version = request.args.get("bot_version", "v1.0.0")
    
    if not username or not player_id:
        return jsonify({"message": "missing parameters"}), 400

    # Get client IP
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    
    # ✅ FIXÉ: Vérifier la version du bot avec normalisation
    latest_version = db_helper.get_latest_bot_version()
    is_up_to_date = bot_version.lstrip('v') == latest_version.lstrip('v')
    
    # Log bot version
    log_event(f"authv2: '{username}' connecting with bot version {bot_version} (latest: {latest_version}, upToDate: {is_up_to_date})", level="info")

    # STEP 1: Try to find by player_id first
    user_by_id = db_helper.get_user_by_player_id(player_id)
    
    # STEP 2: If no ID match, try nickname
    user_by_nickname = None
    if not user_by_id:
        users = load_users()
        user_by_nickname = find_user(users, username)
    
    # SCENARIO 1: Player ID matches an existing account
    if user_by_id:
        # CHECK IF LICENSE IS PAUSED
        if user_by_id.get("paused", False):
            log_event(f"authv2 paused: '{username}' license is paused", level="warn")
            record_connection(username, ip, "paused")
            return jsonify({
                "message": "paused",
                "nickname": username,
                "upToDate": is_up_to_date
            }), 403

        try:
            expiry = parse_date(user_by_id["expires"])
        except Exception:
            log_event(f"authv2 fail: invalid expiry date for ID (nickname: '{username}')", level="error")
            record_connection(username, ip, "unauthorized")
            return jsonify({
                "message": "unauthorized",
                "nickname": username,
                "upToDate": is_up_to_date
            }), 403

        if expiry >= datetime.now():
            # ✅ Update user's last bot version
            db_helper.update_user_bot_version(user_by_id["username"], bot_version)
            
            # Check if nickname changed
            old_nickname = user_by_id.get("username", "")
            custom_msg = ""
            
            if old_nickname != username:
                log_event(f"authv2: nickname changed: '{old_nickname}' → '{username}'")
                db_helper.update_user_nickname(player_id, username, old_nickname)
                custom_msg = f"🔄 Your nickname has been updated from '{old_nickname}' to '{username}'"
            
            # Get global custom message if set
            global_msg = db_helper.get_custom_message()
            if global_msg:
                custom_msg = global_msg + ("\n\n" + custom_msg if custom_msg else "")
            
            log_event(f"authv2 success: '{username}' valid until {user_by_id['expires']}", level="info")
            record_connection(username, ip, "authorized")
            
            return jsonify({
                "message": "authorized",
                "expires": user_by_id["expires"],
                "nickname": username,
                "custom_message": custom_msg if custom_msg else None,
                "bot_version": bot_version,
                "upToDate": is_up_to_date
            }), 200
        else:
            log_event(f"authv2 expired: '{username}' expired on {user_by_id['expires']}", level="warn")
            record_connection(username, ip, "expired")
            return jsonify({
                "message": "expired",
                "expires": user_by_id["expires"],
                "nickname": username,
                "upToDate": is_up_to_date
            }), 403
    
    # SCENARIO 2: No ID match, but nickname exists without ID (first connection)
    elif user_by_nickname:
        if user_by_nickname.get("player_id") is None:
            if user_by_nickname.get("paused", False):
                log_event(f"authv2 paused: '{username}' license is paused", level="warn")
                record_connection(username, ip, "paused")
                return jsonify({
                    "message": "paused",
                    "nickname": username,
                    "upToDate": is_up_to_date
                }), 403

            try:
                expiry = parse_date(user_by_nickname["expires"])
            except Exception:
                log_event(f"authv2 fail: invalid expiry date for '{username}'", level="error")
                record_connection(username, ip, "unauthorized")
                return jsonify({
                    "message": "unauthorized",
                    "nickname": username,
                    "upToDate": is_up_to_date
                }), 403

            if expiry >= datetime.now():
                # First connection - bind player_id to this account
                db_helper.update_user_player_id(username, player_id)
                
                # ✅ Update user's last bot version
                db_helper.update_user_bot_version(username, bot_version)
                
                custom_msg = f"🎉 Welcome! This is your first connection. Your account is now linked."
                
                # Get global custom message if set
                global_msg = db_helper.get_custom_message()
                if global_msg:
                    custom_msg = global_msg + "\n\n" + custom_msg
                
                log_event(f"authv2 first connection: '{username}' linked to ID")
                record_connection(username, ip, "authorized")
                
                return jsonify({
                    "message": "authorized",
                    "expires": user_by_nickname["expires"],
                    "nickname": username,
                    "custom_message": custom_msg,
                    "bot_version": bot_version,
                    "upToDate": is_up_to_date
                }), 200
            else:
                log_event(f"authv2 expired: '{username}' expired on {user_by_nickname['expires']}", level="warn")
                record_connection(username, ip, "expired")
                return jsonify({
                    "message": "expired",
                    "expires": user_by_nickname["expires"],
                    "nickname": username,
                    "upToDate": is_up_to_date
                }), 403
        else:
            log_event(f"authv2 fail: nickname '{username}' already linked to different ID", level="warn")
            record_connection(username, ip, "unauthorized")
            return jsonify({
                "message": "unauthorized",
                "nickname": username,
                "upToDate": is_up_to_date
            }), 403
    
    # SCENARIO 3: Neither ID nor nickname found
    else:
        log_event(f"authv2 fail: no account found for nickname '{username}'", level="warn")
        record_connection(username, ip, "unauthorized")
        return jsonify({
            "message": "unauthorized",
            "nickname": username,
            "upToDate": is_up_to_date
        }), 403


@app.route("/api/custom-message", methods=["GET"])
@login_required
def api_custom_message_get():
    """Get the global custom message"""
    msg = db_helper.get_custom_message()
    return jsonify({"message": msg}), 200

@app.route("/api/custom-message/set", methods=["POST"])
@login_required
def api_custom_message_set():
    """Set the global custom message"""
    body = request.get_json() or {}
    new_message = body.get("message", "").strip()
    
    # Save to database
    if db_helper.set_custom_message(new_message):
        log_event(f"Custom message updated: '{new_message}'")
        return jsonify({"message": "ok", "custom_message": new_message}), 200
    else:
        log_event(f"Failed to update custom message", level="error")
        return jsonify({"error": "Failed to save message"}), 500

@app.route("/api/custom-message/clear", methods=["POST"])
@login_required
def api_custom_message_clear():
    """Clear the global custom message"""
    if db_helper.set_custom_message(""):
        log_event(f"Custom message cleared")
        return jsonify({"message": "ok"}), 200
    else:
        log_event(f"Failed to clear custom message", level="error")
        return jsonify({"error": "Failed to clear message"}), 500

@app.route('/shop')
def shop():
    """Main shop page"""
    return render_template('shop.html')

@app.route('/api/shop/create-order', methods=['POST'])
def create_shop_order():
    """Create PayPal order for shop purchase"""
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        return jsonify({'error': 'PayPal not configured'}), 500
    
    try:
        data = request.json
        product = data.get('product')
        username = data.get('username')
        message = data.get('message', '')
        
        if not product or not username:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Store purchase info in session
        session['shop_purchase'] = {
            'product': product,
            'username': username,
            'message': message,
            'timestamp': time.time()
        }
        
        # Create PayPal payment
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {"payment_method": "paypal"},
            "redirect_urls": {
                "return_url": url_for("shop_payment_success", _external=True),
                "cancel_url": url_for("shop_payment_cancel", _external=True)
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": product.get('name'),
                        "sku": product.get('type'),
                        "price": str(product.get('price')),
                        "currency": "EUR",
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": str(product.get('price')),
                    "currency": "EUR"
                },
                "description": f"{product.get('name')} for {username}"
            }]
        })
        
        if payment.create():
            # Find approval URL
            for link in payment.links:
                if link.rel == "approval_url":
                    return jsonify({'approval_url': link.href})
            return jsonify({'error': 'No approval URL found'}), 500
        else:
            log_event(f"PayPal shop order creation failed: {payment.error}", level="error")
            return jsonify({'error': 'Payment creation failed'}), 500
            
    except Exception as e:
        log_event(f"Error creating shop order: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/shop/payment/success')
def shop_payment_success():
    """Handle successful shop payment"""
    payment_id = request.args.get("paymentId")
    payer_id = request.args.get("PayerID")
    
    if not payment_id or not payer_id:
        return render_template('shop_error.html', error='Invalid payment parameters'), 400
    
    try:
        # Execute payment
        payment = paypalrestsdk.Payment.find(payment_id)
        
        if payment.execute({"payer_id": payer_id}):
            if payment.state != "approved":
                return render_template('shop_error.html', error='Payment not approved'), 400
            
            # Get purchase info from session
            purchase_info = session.get('shop_purchase')
            
            if not purchase_info:
                return render_template('shop_error.html', error='Purchase session expired'), 400
            
            # Check session timeout (30 minutes)
            if time.time() - purchase_info.get('timestamp', 0) > 1800:
                session.pop('shop_purchase', None)
                return render_template('shop_error.html', error='Purchase session expired'), 400
            
            product = purchase_info['product']
            username = purchase_info['username']
            message = purchase_info['message']
            
            # Send gift to user
            try:
                result = send_wolvesville_gift(username, product, message)
                
                # Clear session
                session.pop('shop_purchase', None)
                
                log_event(f"Shop gift sent: {product.get('name')} to {username}")
                
                return render_template('shop_success.html', 
                                     username=username,
                                     product=product,
                                     result=result)
                
            except Exception as e:
                log_event(f"Failed to send gift: {e}", level="error")
                return render_template('shop_error.html', 
                                     error=f'Payment succeeded but gift delivery failed: {str(e)}'), 500
        else:
            log_event(f"PayPal execution failed: {payment.error}", level="error")
            return render_template('shop_error.html', error='Payment execution failed'), 500
            
    except Exception as e:
        log_event(f"Shop payment error: {e}", level="error")
        return render_template('shop_error.html', error=str(e)), 500

@app.route('/shop/payment/cancel')
def shop_payment_cancel():
    """Handle cancelled shop payment"""
    session.pop('shop_purchase', None)
    return render_template('shop_cancel.html')

# --------- COUPON ROUTES ------------
# ==================== COUPON & CART ROUTES ====================

@app.route('/api/shop/validate-coupon', methods=['POST'])
def validate_coupon():
    """Validate a coupon code"""
    try:
        data = request.json
        code = data.get('code', '').strip().upper()
        
        if not code:
            return jsonify({'valid': False, 'message': 'Please enter a coupon code'}), 400
        
        valid, message, discount = coupon_manager.validate_coupon(code)
        
        return jsonify({
            'valid': valid,
            'message': message,
            'discount_percent': discount
        })
        
    except Exception as e:
        log_event(f"Error validating coupon: {e}", level="error")
        return jsonify({'valid': False, 'message': 'An error occurred'}), 500


@app.route('/api/shop/create-cart-order', methods=['POST'])
def create_cart_order():
    """Create PayPal order for shopping cart"""
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        return jsonify({'error': 'PayPal not configured'}), 500
    
    try:
        data = request.json
        cart = data.get('cart', [])
        username = data.get('username')
        message = data.get('message', '')
        coupon = data.get('coupon')
        breakdown = data.get('breakdown', {})
        gift_card = data.get('giftCard')
        final_payment_amount = data.get('finalPaymentAmount', 0)
        
        if not cart or not username:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # If payment is fully covered by gift card, complete purchase without PayPal
        if final_payment_amount <= 0:
            # Create purchase record directly
            gift_code = gift_card.get('code') if gift_card else None
            
            # Filter out gift cards - they don't get sent in-game
            items_to_send = [item for item in cart if item.get('type') != 'GIFT_CARD' and item.get('category') != 'gift_card']
            
            db_helper.create_purchase(
                username=username,
                items=cart,
                total_amount=data.get('total', 0),
                message=message,
                coupon_used=coupon,
                payment_id=f"GIFTCARD-{gift_code}" if gift_code else "GIFTCARD"
            )
            
            # Only send real items, not gift cards
            if items_to_send:
                for item in items_to_send:
                    for i in range(item.get('quantity', 1)):
                        try:
                            send_wolvesville_gift(username, item, message)
                            # Wait 2 seconds between gifts
                            if not (item == items_to_send[-1] and i == item.get('quantity', 1) - 1):
                                time.sleep(2)
                        except Exception as e:
                            log_event(f"Failed to send gift {item.get('name')}: {e}", level="error")
            
            # Redeem gift code
            if gift_code:
                db_helper.redeem_gift_code(gift_code, username)
                log_event(f"Purchase completed with gift card: {gift_code}, user: {username}")
            
            return jsonify({
                'success': True,
                'paid_with_gift_card': True,
                'redirect': url_for('cart_success')
            }), 200
        
        # Helper function to format currency (CRITICAL FOR PAYPAL)
        def format_price(amount):
            """Format price to exactly 2 decimal places as string"""
            return f"{float(amount):.2f}"
        
        # Use breakdown from frontend (already calculated with proper rounding)
        subtotal = breakdown.get('subtotal', 0)
        loyalty_discount = breakdown.get('loyaltyDiscount', 0)
        promo_discount = breakdown.get('promoDiscount', 0)
        coupon_discount = breakdown.get('couponDiscount', 0)
        gift_card_discount = breakdown.get('giftCardDiscount', 0)
        total = data.get('total', 0)
        
        # Store purchase info in session
        session['cart_purchase'] = {
            'cart': cart,
            'username': username,
            'message': message,
            'coupon': coupon,
            'total': total,
            'gift_card': gift_card,
            'timestamp': time.time()
        }
        
        # Create PayPal payment items - MUST format each price properly
        items = []
        for item in cart:
            items.append({
                "name": item.get('name'),
                "sku": item.get('type'),
                "price": format_price(item.get('price')),  # ✅ Format price
                "currency": "EUR",
                "quantity": item.get('quantity', 1)
            })
        
        # PayPal doesn't support negative line items for discounts
        # We need to calculate the final amount and NOT include discount items
        # Just send the items at their regular prices and adjust the total
        
        # Calculate what PayPal will compute as subtotal
        paypal_subtotal = sum(float(format_price(item['price'])) * item['quantity'] for item in cart)
        
        # Create PayPal payment
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {"payment_method": "paypal"},
            "redirect_urls": {
                "return_url": url_for("cart_payment_success", _external=True),
                "cancel_url": url_for("cart_payment_cancel", _external=True)
            },
            "transactions": [{
                "item_list": {"items": items},
                "amount": {
                    "total": format_price(final_payment_amount),  # ✅ Use final payment amount (after gift card)
                    "currency": "EUR",
                    "details": {
                        "subtotal": format_price(paypal_subtotal),  # ✅ Format subtotal
                        "discount": format_price(paypal_subtotal - final_payment_amount) if final_payment_amount < paypal_subtotal else "0.00"  # ✅ Format discount
                    }
                },
                "description": f"Cart purchase for {username}"
            }]
        })
        
        if payment.create():
            for link in payment.links:
                if link.rel == "approval_url":
                    return jsonify({'approval_url': link.href})
            return jsonify({'error': 'No approval URL found'}), 500
        else:
            log_event(f"PayPal cart order creation failed: {payment.error}", level="error")
            return jsonify({'error': 'Payment creation failed'}), 500
            
    except Exception as e:
        log_event(f"Error creating cart order: {e}", level="error")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/cart/payment/success')
def cart_payment_success():
    """Handle successful cart payment with 2-second delays between gifts"""
    payment_id = request.args.get("paymentId")
    payer_id = request.args.get("PayerID")
    
    if not payment_id or not payer_id:
        return render_template('shop_error.html', error='Invalid payment parameters'), 400
    
    try:
        # Execute payment
        payment = paypalrestsdk.Payment.find(payment_id)
        
        if payment.execute({"payer_id": payer_id}):
            if payment.state != "approved":
                return render_template('shop_error.html', error='Payment not approved'), 400
            
            # Get purchase info from session
            purchase_info = session.get('cart_purchase')
            
            if not purchase_info:
                return render_template('shop_error.html', error='Purchase session expired'), 400
            
            # Check session timeout (30 minutes)
            if time.time() - purchase_info.get('timestamp', 0) > 1800:
                session.pop('cart_purchase', None)
                return render_template('shop_error.html', error='Purchase session expired'), 400
            
            cart = purchase_info['cart']
            username = purchase_info['username']
            message = purchase_info['message']
            coupon = purchase_info.get('coupon')
            gift_card = purchase_info.get('gift_card')
            
            # Mark coupon as used if applicable
            if coupon:
                coupon_manager.use_coupon(coupon['code'])
            
            # Filter out gift cards - only send real shop items
            items_to_send = [item for item in cart if item.get('type') != 'GIFT_CARD' and item.get('category') != 'gift_card']
            
            # Send gifts with 2-second delays
            results = []
            failed_items = []
            
            for item in items_to_send:
                for i in range(item['quantity']):
                    try:
                        # Send gift
                        result = send_wolvesville_gift(username, item, message)
                        results.append({
                            'item': item['name'],
                            'success': True
                        })
                        
                        # Wait 2 seconds before next gift (except for last one)
                        if not (item == items_to_send[-1] and i == item['quantity'] - 1):
                            time.sleep(2)
                            
                    except Exception as e:
                        log_event(f"Failed to send gift {item['name']}: {e}", level="error")
                        failed_items.append(item['name'])
                        results.append({
                            'item': item['name'],
                            'success': False,
                            'error': str(e)
                        })
            
            # Create purchase record
            db_helper.create_purchase(
                username=username,
                items=cart,
                total_amount=purchase_info.get('total', 0),
                message=message,
                coupon_used=coupon.get('code') if coupon else None,
                payment_id=payment_id
            )
            
            # Redeem gift code if used
            if gift_card and gift_card.get('code'):
                db_helper.redeem_gift_code(gift_card['code'], username)
                log_event(f"Gift card redeemed during checkout: {gift_card['code']}, user: {username}")
            
            # Clear session
            session.pop('cart_purchase', None)
            
            total_items = sum(item['quantity'] for item in cart)
            successful = len([r for r in results if r['success']])
            
            log_event(f"Cart gifts sent: {successful}/{total_items} to {username}")
            
            return render_template('cart_success.html',
                                 username=username,
                                 cart=cart,
                                 results=results,
                                 successful=successful,
                                 total=total_items,
                                 failed_items=failed_items)
        else:
            log_event(f"PayPal execution failed: {payment.error}", level="error")
            return render_template('shop_error.html', error='Payment execution failed'), 500
            
    except Exception as e:
        log_event(f"Cart payment error: {e}", level="error")
        return render_template('shop_error.html', error=str(e)), 500


@app.route('/cart/payment/cancel')
def cart_payment_cancel():
    """Handle cancelled cart payment"""
    session.pop('cart_purchase', None)
    return render_template('cart_cancel.html')


# ==================== ADMIN COUPON MANAGEMENT ====================

@app.route('/admin/coupons')
@login_required
def admin_coupons():
    """Admin page for managing coupons"""
    return render_template('admin_coupons.html')


@app.route('/api/admin/coupons', methods=['GET'])
@login_required
def api_get_coupons():
    """Get all coupons"""
    coupons = coupon_manager.get_all_coupons()
    return jsonify(coupons)


@app.route('/api/admin/coupons/create', methods=['POST'])
@login_required
def api_create_coupon():
    """Create a new coupon"""
    try:
        data = request.json
        code = data.get('code', '').strip().upper()
        discount_percent = data.get('discount_percent')
        max_uses = data.get('max_uses')
        expires_at = data.get('expires_at')
        
        if not code or not discount_percent:
            return jsonify({'error': 'Code and discount percent required'}), 400
        
        if discount_percent < 1 or discount_percent > 100:
            return jsonify({'error': 'Discount must be between 1-100%'}), 400
        
        success, message = coupon_manager.create_coupon(
            code, discount_percent, max_uses, expires_at
        )
        
        if success:
            log_event(f"Coupon created: {code} ({discount_percent}% off)")
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        log_event(f"Error creating coupon: {e}", level="error")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/coupons/toggle', methods=['POST'])
@login_required
def api_toggle_coupon():
    """Enable/disable a coupon"""
    try:
        data = request.json
        code = data.get('code')
        is_active = data.get('is_active')
        
        if not code or is_active is None:
            return jsonify({'error': 'Missing required fields'}), 400
        
        if coupon_manager.toggle_coupon(code, is_active):
            status = 'enabled' if is_active else 'disabled'
            log_event(f"Coupon {code} {status}")
            return jsonify({'success': True, 'message': f'Coupon {status}'})
        else:
            return jsonify({'error': 'Coupon not found'}), 404
            
    except Exception as e:
        log_event(f"Error toggling coupon: {e}", level="error")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/coupons/delete', methods=['POST'])
@login_required
def api_delete_coupon():
    """Delete a coupon"""
    try:
        data = request.json
        code = data.get('code')
        
        if not code:
            return jsonify({'error': 'Code required'}), 400
        
        if coupon_manager.delete_coupon(code):
            log_event(f"Coupon deleted: {code}")
            return jsonify({'success': True, 'message': 'Coupon deleted'})
        else:
            return jsonify({'error': 'Coupon not found'}), 404
            
    except Exception as e:
        log_event(f"Error deleting coupon: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route("/api/bot-version", methods=["GET"])
@login_required
def api_bot_version_get():
    """Get the latest bot version"""
    version = db_helper.get_latest_bot_version()
    return jsonify({"latest_version": version}), 200

@app.route("/api/bot-version/set", methods=["POST"])
@login_required
def api_bot_version_set():
    """Set the latest bot version"""
    body = request.get_json() or {}
    new_version = body.get("version", "").strip()
    
    if not new_version:
        return jsonify({"error": "Version required"}), 400
    
    # Simple validation: version should be like "0.6.9" or "v0.6.9"
    import re
    if not re.match(r'^v?\d+\.\d+\.\d+$', new_version):
        return jsonify({"error": "Invalid version format (use X.Y.Z or vX.Y.Z)"}), 400
    
    if db_helper.set_latest_bot_version(new_version):
        log_event(f"Bot version updated to: {new_version}")
        return jsonify({"message": "ok", "latest_version": new_version}), 200
    else:
        log_event(f"Failed to update bot version", level="error")
        return jsonify({"error": "Failed to save version"}), 500

@app.route("/api/users/bot-versions", methods=["GET"])
@login_required
def api_users_bot_versions():
    """Get bot version statistics for all users"""
    try:
        with db_helper.get_db() as db:
            from sqlalchemy import func
            from init_database import User
            
            # Get count of users per bot version
            version_stats = db.query(
                User.last_bot_version,
                func.count(User.username).label('count')
            ).filter(
                User.last_bot_version.isnot(None)
            ).group_by(
                User.last_bot_version
            ).order_by(
                func.count(User.username).desc()
            ).all()
            
            results = [
                {"version": v or "Unknown", "count": c}
                for v, c in version_stats
            ]
            
            return jsonify(results), 200
    except Exception as e:
        log_event(f"Error getting bot version stats: {e}", level="error")
        return jsonify({"error": str(e)}), 500

@app.route('/api/shop/validate-username', methods=['POST'])
def validate_shop_username():
    """Validate Wolvesville username exists before allowing purchase"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({'valid': False, 'error': 'Username required'}), 400
        
        # Search player using Wolvesville API
        player = wolvesville_api.search_player(username)
        
        if not player:
            log_event(f"Shop username validation failed: '{username}' not found")
            return jsonify({
                'valid': False,
                'error': f'Username "{username}" not found on Wolvesville'
            }), 404
        
        log_event(f"Shop username validated: '{username}' (ID: {player.get('id')})")
        
        return jsonify({
            'valid': True,
            'player_id': player.get('id'),
            'username': player.get('username')  # Return exact username (case-sensitive)
        }), 200
        
    except Exception as e:
        log_event(f"Username validation error: {e}", level="error")
        return jsonify({
            'valid': False,
            'error': 'Failed to validate username. Please try again.'
        }), 500


@app.route('/api/shop/data', methods=['GET'])
def get_shop_data():
    """Get current shop data (bundles, skins, calendars)"""
    try:
        shop_data = db_helper.get_shop_data()
        
        if not shop_data:
            return jsonify({
                'error': 'Shop data not available yet. Please try again in a few minutes.'
            }), 503
        
        # Filter out "new" items that are older than 7 days
        if 'bundles' in shop_data:
            today = datetime.now()
            for bundle in shop_data['bundles']:
                if bundle.get('isNew') and bundle.get('newSince'):
                    try:
                        new_since = datetime.strptime(bundle['newSince'], '%Y-%m-%d')
                        if (today - new_since).days >= 7:
                            bundle['isNew'] = False
                    except:
                        bundle['isNew'] = False
        
        return jsonify(shop_data), 200
        
    except Exception as e:
        log_event(f"Error getting shop data: {e}", level="error")
        return jsonify({'error': 'Failed to load shop data'}), 500


@app.route('/api/shop/refresh', methods=['POST'])
@login_required
def refresh_shop_data():
    """Admin endpoint to manually trigger shop data refresh"""
    try:
        shop_data_fetcher.sync_shop_data()
        return jsonify({'success': True, 'message': 'Shop data refreshed successfully'}), 200
    except Exception as e:
        log_event(f"Manual shop refresh failed: {e}", level="error")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/shop/new-items', methods=['GET'])
def get_new_shop_items():
    """Get only items marked as "new" (less than 7 days old)"""
    try:
        shop_data, _ = db_helper.read_storage('shop-data.json')
        
        if not shop_data:
            return jsonify({'bundles': [], 'skin_sets': [], 'daily_skins': []}), 200
        
        today = datetime.now()
        
        # Filter new bundles
        new_bundles = []
        for bundle in shop_data.get('bundles', []):
            if bundle.get('isNew') and bundle.get('newSince'):
                try:
                    new_since = datetime.strptime(bundle['newSince'], '%Y-%m-%d')
                    if (today - new_since).days < 7:
                        new_bundles.append(bundle)
                except:
                    pass
        
        return jsonify({
            'bundles': new_bundles,
            'skin_sets': shop_data.get('skin_sets', []),  # Always show current skin sets
            'daily_skins': shop_data.get('daily_skins', [])  # Always show current daily skins
        }), 200
        
    except Exception as e:
        log_event(f"Error getting new items: {e}", level="error")
        return jsonify({'bundles': [], 'skin_sets': [], 'daily_skins': []}), 500

# ==================== GIFT CODE ENDPOINTS ====================

@app.route('/api/gift-codes/create', methods=['POST'])
@login_required
def create_gift_code_endpoint():
    """Admin creates a gift code"""
    try:
        data = request.json
        amount = data.get('amount', 0)
        expires_at = data.get('expires_at')
        
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
        
        code = db_helper.create_gift_code(float(amount), expires_at)
        
        if code:
            log_event(f"Gift code created: {code} for €{amount}")
            return jsonify({'code': code, 'amount': amount}), 200
        else:
            return jsonify({'error': 'Failed to create code'}), 500
    except Exception as e:
        log_event(f"Error creating gift code: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gift-codes/redeem', methods=['POST'])
def redeem_gift_code_endpoint():
    """User redeems a gift code"""
    try:
        data = request.json
        code = data.get('code', '').strip().upper()
        username = data.get('username', '').strip()
        
        if not code or not username:
            return jsonify({'valid': False, 'message': 'Code and username required'}), 400
        
        # Check if code exists and is valid
        gift_code = db_helper.get_gift_code(code)
        if not gift_code:
            return jsonify({'valid': False, 'message': 'Invalid gift code'}), 400
        
        if gift_code['is_redeemed']:
            return jsonify({'valid': False, 'message': 'Code already redeemed'}), 400
        
        # Redeem the code
        success, result = db_helper.redeem_gift_code(code, username)
        if success:
            log_event(f"Gift code redeemed: {code} by {username} for €{result}")
            return jsonify({'valid': True, 'amount': result}), 200
        else:
            return jsonify({'valid': False, 'message': result}), 400
    except Exception as e:
        log_event(f"Error redeeming gift code: {e}", level="error")
        return jsonify({'valid': False, 'message': 'An error occurred'}), 500

@app.route('/api/gift-codes/check', methods=['POST'])
def check_gift_code_endpoint():
    """Check if a gift code is valid and return balance"""
    try:
        data = request.json
        code = data.get('code', '').strip().upper()
        
        if not code:
            return jsonify({'valid': False, 'balance': 0, 'message': 'Please enter a code'}), 400
        
        # Check if code exists and is valid
        gift_code = db_helper.get_gift_code(code)
        if not gift_code:
            return jsonify({'valid': False, 'balance': 0, 'message': 'Invalid gift code'}), 400
        
        if gift_code['is_redeemed']:
            return jsonify({'valid': False, 'balance': 0, 'message': 'Code already redeemed'}), 400
        
        # Check expiry date
        if gift_code.get('expires_at'):
            from datetime import datetime
            expiry_date = datetime.fromisoformat(gift_code['expires_at'])
            if expiry_date < datetime.now():
                return jsonify({'valid': False, 'balance': 0, 'message': 'Code has expired'}), 400
        
        # Return code details
        return jsonify({
            'valid': True,
            'balance': float(gift_code['amount']),
            'message': f'Code valid! Balance: €{gift_code["amount"]:.2f}'
        }), 200
    except Exception as e:
        log_event(f"Error checking gift code: {e}", level="error")
        return jsonify({'valid': False, 'balance': 0, 'message': 'An error occurred'}), 500

@app.route('/api/admin/gift-codes', methods=['GET'])
@login_required
def get_all_gift_codes_endpoint():
    """Get all gift codes for admin"""
    try:
        codes = db_helper.get_all_gift_codes()
        return jsonify({'codes': codes}), 200
    except Exception as e:
        log_event(f"Error getting gift codes: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/send-gift', methods=['POST'])
@login_required
def send_gift_admin():
    """Admin endpoint to send gifts to users"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        item = data.get('item', {})
        message = data.get('message', '').strip()
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        if not item.get('type'):
            return jsonify({'error': 'Item type is required'}), 400
        
        # Prepare product info for sending gift
        product = {
            'type': item.get('type'),
            'name': item.get('name', item.get('type')),
            'price': float(item.get('price', 0)),
            'cost': 0  # Admin gifts don't cost gems
        }
        
        # Send the gift via Wolvesville API
        gift_result = send_wolvesville_gift(username, product, message)
        
        if gift_result.get('success') or gift_result.get('status') == 'success':
            # Record this as a purchase for admin tracking
            admin_user = session.get('user')
            db_helper.create_purchase(
                username=username,
                items=[product],
                total_amount=0,
                message=f"Admin gift from {admin_user}: {message}",
                coupon_used=None,
                payment_id=f"admin-gift-{username}-{int(time.time())}"
            )
            
            return jsonify({
                'success': True,
                'message': f'Gift sent to {username}',
                'username': username,
                'item': item.get('name')
            }), 200
        else:
            error_msg = gift_result.get('error') or 'Failed to send gift'
            return jsonify({'error': error_msg}), 400
            
    except Exception as e:
        log_event(f"Error sending admin gift: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/gift-history', methods=['GET'])
@login_required
def get_gift_history():
    """Get recent gifts sent by admin"""
    try:
        all_purchases = db_helper.get_all_purchases()
        admin_gifts = []
        
        for purchase in all_purchases:
            if purchase and isinstance(purchase, dict):
                payment_id = purchase.get('payment_id', '')
                if 'admin-gift' in str(payment_id):
                    admin_gifts.append({
                        'username': purchase.get('username'),
                        'item': purchase.get('items', [{}])[0].get('name', 'Unknown') if purchase.get('items') else 'Unknown',
                        'item_name': purchase.get('items', [{}])[0].get('name', 'Unknown') if purchase.get('items') else 'Unknown',
                        'item_value': purchase.get('items', [{}])[0].get('price', 0) if purchase.get('items') else 0,
                        'created_at': purchase.get('created_at', 'N/A'),
                        'date': purchase.get('created_at', 'N/A')
                    })
        
        # Return most recent first, limit to 20
        admin_gifts.reverse()
        return jsonify({'gifts': admin_gifts[:20]}), 200
    except Exception as e:
        log_event(f"Error getting gift history: {e}", level="error")
        return jsonify({'gifts': []}), 200

# ==================== PURCHASE HISTORY ENDPOINTS ====================

@app.route('/api/purchases/history', methods=['GET'])
def get_purchase_history():
    """Get purchase history for a user"""
    try:
        username = request.args.get('username', '').strip()
        if not username:
            return jsonify({'error': 'Username required'}), 400
        
        purchases = db_helper.get_user_purchases(username)
        return jsonify({'purchases': purchases}), 200
    except Exception as e:
        log_event(f"Error getting purchase history: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/purchases', methods=['GET'])
@login_required
def get_all_purchases_endpoint():
    """Get all purchases for admin"""
    try:
        purchases = db_helper.get_all_purchases()
        return jsonify({'purchases': purchases}), 200
    except Exception as e:
        log_event(f"Error getting all purchases: {e}", level="error")
        return jsonify({'error': str(e)}), 500

# ==================== SHOP SETTINGS ENDPOINTS ====================

@app.route('/api/shop/settings', methods=['GET'])
def get_shop_settings_endpoint():
    """Get current shop settings"""
    try:
        settings = db_helper.get_shop_settings()
        return jsonify(settings), 200
    except Exception as e:
        log_event(f"Error getting shop settings: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/shop/settings', methods=['POST'])
@login_required
def update_shop_settings_endpoint():
    """Update shop settings"""
    try:
        data = request.json
        enabled = data.get('global_promo_enabled', False)
        percent = data.get('global_promo_percent', 0)
        label = data.get('global_promo_label')
        
        success = db_helper.update_shop_settings(enabled, percent, label)
        
        if success:
            log_event(f"Shop settings updated: promo {percent}% enabled={enabled}")
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Failed to update settings'}), 500
    except Exception as e:
        log_event(f"Error updating shop settings: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gift-cards/top-up', methods=['POST'])
def gift_card_top_up_endpoint():
    """Create a PayPal payment to top up gift card balance"""
    try:
        data = request.json
        amount = data.get('amount')
        gift_code = data.get('giftCode')
        
        if not amount or amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
        
        if not gift_code:
            return jsonify({'error': 'Gift code required'}), 400
        
        # Verify gift code exists and is valid
        code_data = db_helper.get_gift_code(gift_code)
        if not code_data:
            return jsonify({'error': 'Invalid gift code'}), 400
        
        if code_data['is_redeemed']:
            return jsonify({'error': 'Code already redeemed'}), 400
        
        # Create PayPal payment for top-up
        from paypalrestsdk import Payment
        
        payment = Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": url_for('shop_top_up_success', _external=True),
                "cancel_url": url_for('shop_top_up_cancel', _external=True)
            },
            "transactions": [{
                "amount": {
                    "total": str(amount),
                    "currency": "EUR",
                    "details": {
                        "subtotal": str(amount)
                    }
                },
                "description": f"Gift Card Top-Up: {gift_code}",
                "invoice_number": f"TOPUP-{gift_code}-{int(time.time())}"
            }]
        })
        
        if payment.create():
            # Store top-up in session or database for later redemption
            session['top_up_amount'] = amount
            session['top_up_code'] = gift_code
            session['payment_id'] = payment.id
            
            # Get approval URL
            for link in payment.links:
                if link.rel == "approval_url":
                    log_event(f"Gift card top-up initiated: {gift_code}, amount: €{amount}")
                    return jsonify({'approval_url': link.href}), 200
            
            return jsonify({'error': 'No approval URL found'}), 500
        else:
            log_event(f"PayPal error for gift card top-up: {payment.error}", level="error")
            return jsonify({'error': 'Failed to create payment: ' + payment.error.get('message', 'Unknown error')}), 500
            
    except Exception as e:
        log_event(f"Error creating gift card top-up payment: {e}", level="error")
        return jsonify({'error': str(e)}), 500

@app.route('/shop/top-up/success')
def shop_top_up_success():
    """Handle successful gift card top-up payment"""
    try:
        payment_id = request.args.get('paymentId')
        payer_id = request.args.get('PayerID')
        
        if not payment_id or not payer_id:
            return render_template('payment_cancel.html', reason='Missing payment information')
        
        # Execute payment
        from paypalrestsdk import Payment
        payment = Payment.find(payment_id)
        
        if payment.execute({"payer_id": payer_id}):
            # Add balance to gift code
            gift_code = session.get('top_up_code')
            top_up_amount = session.get('top_up_amount')
            
            if gift_code and top_up_amount:
                # Update gift code amount in database
                code_data = db_helper.get_gift_code(gift_code)
                new_balance = float(code_data['amount']) + float(top_up_amount)
                db_helper.update_gift_code_balance(gift_code, new_balance)
                
                log_event(f"Gift card top-up completed: {gift_code}, amount: €{top_up_amount}, new balance: €{new_balance}")
                
                # Clear session
                session.pop('top_up_amount', None)
                session.pop('top_up_code', None)
                session.pop('payment_id', None)
                
            return render_template('payment_success.html', message="Gift Card Balance Updated! ✅")
        else:
            log_event(f"PayPal execution error: {payment.error}", level="error")
            return render_template('payment_cancel.html', reason=payment.error.get('message', 'Unknown error'))
            
    except Exception as e:
        log_event(f"Error processing gift card top-up success: {e}", level="error")
        return render_template('payment_cancel.html', reason=str(e))

@app.route('/shop/top-up/cancel')
def shop_top_up_cancel():
    """Handle cancelled gift card top-up payment"""
    session.pop('top_up_amount', None)
    session.pop('top_up_code', None)
    session.pop('payment_id', None)
    return render_template('shop_cancel.html')

# ==================== ADMIN SHOP MANAGEMENT PAGE ====================

@app.route('/admin/shop')
@login_required
def admin_shop():
    """Admin page for shop data management"""
    return render_template('admin_shop.html')

# -----------------------
# Run
# -----------------------
# Initialize token manager BEFORE starting Flask
print("=" * 60)
print("🔧 Initializing Wolvesville Token Manager...")
print("=" * 60)
try:
    # Start automatic token refresh (this authenticates immediately)
    token_manager.start_auto_refresh()
    print("=" * 60)
    print("✅ Token manager ready!")
    print("=" * 60)
except Exception as e:
    print("=" * 60)
    print(f"❌ CRITICAL: Token manager failed to initialize!")
    print(f"   Error: {e}")
    print("   Check your .env file for:")
    print("   - WOLVESVILLE_EMAIL")
    print("   - WOLVESVILLE_PASSWORD")
    print("   - TWOCAPTCHA_API_KEY")
    print("=" * 60)
    print("   - Server will start but registering won't be available.")

# Replace the old functions:
def search_wolvesville_player(username):
    """Search for player using managed tokens"""
    return wolvesville_api.search_player(username)

def get_wolvesville_player_profile(player_id):
    """Get player profile using managed tokens"""
    return wolvesville_api.get_player_profile(player_id)

shop_data_fetcher.start_scheduler()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)