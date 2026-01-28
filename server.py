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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
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
    get_latest_bot_version, set_latest_bot_version, update_user_bot_version,
    create_purchase, get_purchase, get_all_purchases_for_admin, update_purchase_status, update_purchase_with_key, get_pending_purchases,
    create_paypal_purchase, get_all_paypal_purchases
)
from werkzeug.middleware.proxy_fix import ProxyFix

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
CORS(app, 
     resources={
         r"/*": {
             "origins": "*",
             "methods": ["GET", "POST", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization"],
             "expose_headers": ["Content-Type"],
             "supports_credentials": False
         }
     })

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_prefix=1
)
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

# Configure Flask for proper URL generation behind proxy
# app.config['SERVER_NAME'] = os.getenv('SERVER_NAME', 'rxzbot.com')
app.config['PREFERRED_URL_SCHEME'] = os.getenv('PREFERRED_URL_SCHEME', 'https')

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

# New strict decorators
def admin_required(f):
    """Decorator for admin-only routes.
    - Redirects to admin login for HTML requests
    - Returns JSON 403 for API requests
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            is_api = request.path.startswith('/api/') or request.is_json or 'application/json' in request.headers.get('Accept', '')
            if is_api:
                return jsonify({"error": "admin_required"}), 403
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def user_required(f):
    """Decorator for logged-in user routes.
    - Redirects to user login for HTML requests
    - Returns JSON 401 for API requests
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            is_api = request.path.startswith('/api/') or request.is_json or 'application/json' in request.headers.get('Accept', '')
            if is_api:
                return jsonify({"error": "not_authenticated"}), 401
            return redirect(url_for("loginuser"))
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
    log_event(f"Player search initiated for username: '{username}'", level="info")
    try:
        result = wolvesville_api.search_player(username)
        if result:
            log_event(f"Player search successful for '{username}': ID={result.get('id')}, username={result.get('username')}", level="info")
        else:
            log_event(f"Player search failed for '{username}': No result returned", level="warn")
        return result
    except Exception as e:
        log_event(f"Player search error for '{username}': {str(e)}", level="error")
        raise

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
@admin_required
def api_get_keys():
    """Get all activation keys"""
    keys = load_keys()
    return jsonify(keys)

@app.route("/api/keys/generate", methods=["POST"])
@admin_required
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
@admin_required
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
        
        # Track PayPal purchase
        prices = {
            "test": {"amount": "0.05", "description": "Test Purchase"},
            "1month": {"amount": "2.00", "description": "1 Month Subscription"},
            "2months": {"amount": "4.00", "description": "2 Months Subscription"},
            "3months": {"amount": "5.00", "description": "3 Months Subscription"},
            "1year": {"amount": "10.00", "description": "1 Year Subscription"},
            "lifetime": {"amount": "20.00", "description": "Lifetime bot with updates"},
            "custombot": {"amount": "25.00", "description": "Custom Bot"}
        }
        price = prices.get(item, {}).get("amount", "0.00")
        
        # Get payer email from PayPal
        payer_email = payment.payer.payer_info.email if hasattr(payment, 'payer') and hasattr(payment.payer, 'payer_info') else "unknown@paypal.com"
        
        # Create purchase record
        create_paypal_purchase(
            username=username,
            email=payer_email,
            item=item,
            amount=price,
            currency="USD"
        )

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
@admin_required
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

@app.route("/administrateur", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            session["logged_in"] = True
            # After successful login, stay on /administrateur which now shows the dashboard
            return redirect(url_for("login"))
        else:
            error = "Incorrect password."
    # If admin already logged in, show the dashboard on /administrateur
    if session.get("logged_in"):
        return render_template("admin.html")
    return render_template("login.html", error=error)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/test")
def test_page():
    return render_template("index.html", show_test=True)

@app.route("/admin/add", methods=["POST"])
@admin_required
def admin_add():
    username = request.form.get("username", "").strip()
    expires = request.form.get("expires", "").strip()
    duration = request.form.get("duration", "").strip()

    if not username:
        return redirect(url_for("login"))

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
    return redirect(url_for("login"))

@app.route("/admin/delete/<username>", methods=["GET"])
@admin_required
def admin_delete(username):
    users = load_users()
    users = [u for u in users if u["username"].lower() != username.lower()]
    save_res = save_users(users)
    log_event(f"web delete: {username}")
    return redirect(url_for("login"))

@app.route("/api/users", methods=["GET"])
@admin_required
def api_get_users():
    users = load_users()
    last_conn = load_last_connected()
    for u in users:
        u["last_connected"] = last_conn.get(u["username"])
    return jsonify(users)

@app.route("/api/add", methods=["POST"])
@admin_required
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
@admin_required
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
@admin_required
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

# In-memory logs
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

@app.route("/api/logs", methods=["GET"])
@admin_required
def api_logs():
    """Get recent logs from database"""
    try:
        logs = db_helper.get_recent_logs(limit=500)
        return jsonify(logs)
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return jsonify([])

@app.route("/debug/logs", methods=["GET"])
@admin_required
def debug_logs():
    """Admin-only debug logs view"""
    try:
        logs = db_helper.get_recent_logs(limit=10000)  # Large limit to get most logs
        return render_template("debug_logs.html", logs=logs)
    except Exception as e:
        return f"Error fetching logs: {e}", 500

@app.route("/api/recent", methods=["GET"])
@admin_required
def api_recent():
    """Recent connection attempts from database"""
    try:
        connections = db_helper.get_recent_connections(limit=300)
        return jsonify(connections)
    except Exception as e:
        print(f"Error fetching recent connections: {e}")
        return jsonify([])

@app.route("/api/stats", methods=["GET"])
@admin_required
def api_stats():
    """Return user connection stats"""
    stats = load_stats()
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    return jsonify(sorted_stats)

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

@app.route("/api/testimonials/add", methods=["POST"])
@admin_required
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
        "approved": True
    }
    
    testimonials.append(new_testimonial)
    save_testimonials(testimonials)
    
    log_event(f"testimonial added: {username} ({rating}★)")
    
    return jsonify({"message": "ok", "testimonial": new_testimonial}), 200

@app.route("/api/testimonials/delete", methods=["POST"])
@admin_required
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

@app.route("/api/testimonials/approve", methods=["POST"])
@admin_required
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


# ==================== PURCHASE ROUTES (Roses/Gems) ====================

@app.route("/api/create-purchase", methods=["POST"])
def api_create_purchase():
    """Create a new Roses/Gems purchase"""
    try:
        body = request.get_json() or {}
        
        username = (body.get("username") or "").strip()
        email = (body.get("email") or "").strip()
        platform = (body.get("platform") or "").strip()
        item = (body.get("item") or "").strip()
        currency = (body.get("currency") or "").strip()
        price = (body.get("price") or "").strip()
        
        if not all([username, email, platform, item, currency, price]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        if platform not in ["Instagram", "Discord"]:
            return jsonify({"success": False, "error": "Invalid platform"}), 400
        
        if currency not in ["roses", "gems"]:
            return jsonify({"success": False, "error": "Invalid currency"}), 400
        
        result = create_purchase(username, email, platform, item, currency, price)
        
        if result["success"]:
            log_event(f"Purchase created: {username} - {item} ({currency}) via {platform}", level="info")
            return jsonify({"success": True, "purchase_id": result["purchase_id"]}), 201
        else:
            return jsonify({"success": False, "error": result.get("error", "Failed to create purchase")}), 500
            
    except Exception as e:
        print(f"❌ Error creating purchase: {e}")
        log_event(f"Error creating purchase: {e}", level="error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/purchases", methods=["GET"])
@admin_required
def api_get_purchases():
    """Get all purchases for admin panel"""
    try:
        purchases = get_all_purchases_for_admin()
        return jsonify({"success": True, "purchases": purchases}), 200
    except Exception as e:
        print(f"❌ Error fetching purchases: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/paypal-purchases", methods=["GET"])
@admin_required
def api_get_paypal_purchases():
    """Get all PayPal purchases for admin panel"""
    try:
        paypal_purchases = get_all_paypal_purchases()
        return jsonify({"success": True, "purchases": paypal_purchases}), 200
    except Exception as e:
        print(f"❌ Error fetching PayPal purchases: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/purchase/<int:purchase_id>/status", methods=["PUT"])
@admin_required
def api_update_purchase_status(purchase_id):
    """Update purchase status"""
    try:
        body = request.get_json() or {}
        new_status = (body.get("status") or "").strip()
        
        if new_status not in ["Awaiting user contact", "Awaiting transaction", "Completed"]:
            return jsonify({"success": False, "error": "Invalid status"}), 400
        
        result = update_purchase_status(purchase_id, new_status)
        
        if result["success"]:
            log_event(f"Purchase {purchase_id} status updated to: {new_status}", level="info")
            return jsonify(result), 200
        else:
            return jsonify(result), 404
            
    except Exception as e:
        print(f"❌ Error updating purchase: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/purchase/<int:purchase_id>/approve", methods=["POST"])
@admin_required
def api_approve_purchase(purchase_id):
    """Approve purchase and send key via email"""
    try:
        body = request.get_json() or {}
        access_key = (body.get("access_key") or "").strip()
        
        if not access_key:
            return jsonify({"success": False, "error": "Access key is required"}), 400
        
        purchase = get_purchase(purchase_id)
        if not purchase:
            return jsonify({"success": False, "error": "Purchase not found"}), 404
        
        # Send email with key
        email_sent = send_purchase_key_email(
            email=purchase["email"],
            username=purchase["username"],
            item=purchase["item"],
            access_key=access_key
        )
        
        if not email_sent:
            return jsonify({"success": False, "error": "Failed to send email"}), 500
        
        # Update purchase with key and mark as completed
        result = update_purchase_with_key(purchase_id, access_key)
        
        if result["success"]:
            log_event(f"Purchase {purchase_id} approved - Key: {access_key} sent to {purchase['email']}", level="info")
            return jsonify({"success": True, "message": "Purchase approved and key sent via email"}), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Error approving purchase: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# Start background ping if configured
# Start background ping if configured


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

# User login (now available at /login)
@app.route('/login', methods=['GET', 'POST'])
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
@user_required
def dashboard():
    # Minimal, fast dashboard render. Heavy data is lazy-loaded via API endpoints.
    return render_template('dashboard.html', email=session.get('user_email'))

@app.route('/api/license/pause', methods=['POST'])
@user_required
def pause_license():
    """Pause license for an account"""
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
@user_required
def resume_license():
    """Resume paused license"""
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
@user_required
def extend_license_user():
    """Extend license - redirects to payment page"""
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'error': 'Username required'}), 400
    
    # Store username in session for payment flow
    session['payment_username'] = username
    
    return jsonify({'success': True, 'redirect': '/buy/1month'})

@app.route('/add_account', methods=['GET', 'POST'])
@user_required
def add_account():
    """Route to add a Wolvesville account to user's dashboard"""
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
@user_required
def verify_account():
    """Verify account ownership by checking bio"""
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
@user_required
def api_dashboard_accounts():
    """Return accounts owned by the authenticated user (DB only)."""
    email = session['user_id']
    accounts = db_helper.get_user_accounts(email)
    return jsonify(accounts)

@app.route('/api/dashboard/unlink', methods=['POST'])
@user_required
def api_dashboard_unlink():
    """Unlink account from user's dashboard"""
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
@user_required
def api_dashboard_license(username):
    email = session['user_id']
    accounts = db_helper.get_user_accounts(email)
    if username not in accounts:
        return jsonify({'error': 'Account not found'}), 403
    lic = db_helper.get_license(username)
    if not lic:
        return jsonify({'error': 'License not found'}), 404
    return jsonify(lic)

@app.route('/api/dashboard/xp/<username>', methods=['GET'])
@user_required
def api_dashboard_xp(username):
    email = session['user_id']
    accounts = db_helper.get_user_accounts(email)
    if username not in accounts:
        return jsonify({'error': 'Account not found'}), 403
    xp = db_helper.get_user_xp(username)
    return jsonify(xp)

@app.route('/api/dashboard/profile/<username>', methods=['GET'])
@user_required
def api_dashboard_profile(username):
    # This endpoint is the only one allowed to call Wolvesville API
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
@admin_required
def api_custom_message_get():
    """Get the global custom message"""
    msg = db_helper.get_custom_message()
    return jsonify({"message": msg}), 200

@app.route("/api/custom-message/set", methods=["POST"])
@admin_required
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
@admin_required
def api_custom_message_clear():
    """Clear the global custom message"""
    if db_helper.set_custom_message(""):
        log_event(f"Custom message cleared")
        return jsonify({"message": "ok"}), 200
    else:
        log_event(f"Failed to clear custom message", level="error")
        return jsonify({"error": "Failed to clear message"}), 500

@app.route("/api/bot-version", methods=["GET"])
@admin_required
def api_bot_version_get():
    """Get the latest bot version"""
    version = db_helper.get_latest_bot_version()
    return jsonify({"latest_version": version}), 200

@app.route("/api/bot-version/set", methods=["POST"])
@admin_required
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
@admin_required
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

# -----------------------
# Shutdown Handler
# -----------------------
import atexit
import signal

def cleanup_on_exit():
    """Clean up resources on server shutdown"""
    try:
        print("\n🛑 Server shutting down...")
        token_manager.stop_auto_refresh()
        print("✅ Cleanup complete")
    except Exception as e:
        print(f"⚠️ Error during cleanup: {e}")

# Register cleanup on exit
atexit.register(cleanup_on_exit)

# Also handle SIGINT and SIGTERM for graceful shutdown
def signal_handler(sig, frame):
    cleanup_on_exit()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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


# ========== FORGOT PASSWORD ROUTES ==========

def init_brevo_client():
    """Initialize Brevo (Sendinblue) API client"""
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        print("❌ BREVO_API_KEY not set in environment!")
        return None
    
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = api_key
    api_client = sib_api_v3_sdk.ApiClient(configuration)
    return sib_api_v3_sdk.TransactionalEmailsApi(api_client)

def generate_reset_code():
    """Generate a random 6-digit code"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def generate_reset_token():
    """Generate a secure token for email verification"""
    return secrets.token_urlsafe(32)

def send_password_reset_email(email, reset_code):
    """Send password reset email with 6-digit code using Brevo"""
    try:
        api_instance = init_brevo_client()
        if not api_instance:
            log_event(f"Failed to initialize Brevo client for {email}", level="error")
            return False
        
        sender_name = os.getenv("BREVO_SENDER_NAME", "RXZBot")
        sender_email = os.getenv("BREVO_SENDER_EMAIL", "noreply@rxzbot.com")
        
        email_obj = sib_api_v3_sdk.SendSmtpEmail(
            sender={"name": sender_name, "email": sender_email},
            to=[{"email": email}],
            subject="RXZBot password reset request",
            html_content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: 'Segoe UI', Arial, sans-serif;
                        margin: 0;
                        padding: 0;
                        background-color: #0a0e1a;
                    }}
                    .container {{
                        background: linear-gradient(135deg, #0a0e1a, #0d1526, #1a1f35);
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        padding: 20px;
                    }}
                    .card {{
                        background: linear-gradient(135deg, #0f1724 0%, #0d1520 100%);
                        border: 1px solid rgba(0, 212, 255, 0.12);
                        border-radius: 16px;
                        padding: 40px;
                        max-width: 520px;
                        width: 100%;
                                               color: #eaf1ff;
                        box-shadow: 0 0 40px rgba(0,  212, 255, 0.06);
                    }}
                    h1 {{
                        color: #00d4ff;
                        margin: 0 0 8px 0;
                        font-size: 26px;
                    }}
                    .subtitle {{
                        color: #9aa4b2;
                        font-size: 14px;
                        margin-bottom: 28px;
                    }}
                    .info {{
                        color: #d0d8e8;
                        font-size: 14px;
                        line-height: 1.6;
                        margin: 18px 0;
                    }}
                    .code-box {{
                        background: linear-gradient(
                            135deg,
                            rgba(0,212,255,0.12),
                            rgba(0,212,255,0.05)
                        );
                        border: 2px solid rgba(0,212,255,0.35);
                        border-radius: 12px;
                        padding: 28px;
                        text-align: center;
                        margin: 28px 0;
                    }}
                    .code {{
                        font-size: 34px;
                        font-weight: 700;
                        color: #00d4ff;
                        letter-spacing: 8px;
                        margin: 0;
                    }}
                    .timer {{
                        color: #ffa502;
                        font-weight: 600;
                        margin-top: 14px;
                        font-size: 13px;
                    }}
                    .security {{
                        margin: 28px 0;
                    }}
                    .security-item {{
                        display: flex;
                        align-items: center;
                        margin-bottom: 10px;
                        color: #b5bcc8;
                        font-size: 13px;
                    }}
                    .security-icon {{
                        color: #00d4ff;
                        margin-right: 10px;
                        font-weight: bold;
                    }}
                    .warning {{
                        background: rgba(255,71,87,0.08);
                        border-left: 4px solid #ff4757;
                        padding: 14px;
                        border-radius: 6px;
                        margin: 22px 0;
                        color: #ffb3b3;
                        font-size: 12px;
                    }}
                    .footer {{
                        text-align: center;
                        color: #7a8294;
                        font-size: 12px;
                        margin-top: 32px;
                        border-top: 1px solid rgba(255,255,255,0.06);
                        padding-top: 18px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="card">
                        <h1>Password Reset Request</h1>
                        <p class="subtitle">Secure account recovery for RXZBot</p>

                        <p class="info">Hello,</p>

                        <p class="info">
                            We received a request to reset the password associated with your RXZBot account.
                            Please use the verification code below to continue.
                        </p>

                        <div class="code-box">
                            <p class="code">{reset_code}</p>
                            <div class="timer">This code expires in 5 minutes</div>
                        </div>

                        <div class="security">
                            <div class="security-item">
                                <span class="security-icon">✓</span>
                                <span>This code can only be used once</span>
                            </div>
                            <div class="security-item">
                                <span class="security-icon">✓</span>
                                <span>Automatically expires after 5 minutes</span>
                            </div>
                            <div class="security-item">
                                <span class="security-icon">✓</span>
                                <span>No changes are made without this code</span>
                            </div>
                        </div>

                        <div class="warning">
                            <strong>Didn’t request this?</strong><br>
                            If you did not initiate a password reset, you can safely ignore this email.
                            Your account will remain unchanged.
                        </div>

                        <p class="info">
                            Enter this code on the RXZBot password reset page to choose a new password.
                        </p>

                        <div class="footer">
                            <p>© 2026 RXZBot. All rights reserved.</p>
                            <p>This is an automated security message. Please do not reply.</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
        )
        
        response = api_instance.send_transac_email(email_obj)
        log_event(f"Password reset email sent to {email}", level="info")
        return True
        
    except ApiException as e:
        log_event(f"Brevo API error sending reset email to {email}: {e}", level="error")
        return False
    except Exception as e:
        log_event(f"Error sending reset email to {email}: {str(e)}", level="error")
        return False


def send_purchase_key_email(email, username, item, access_key):
    """Send access key email after purchase approval"""
    try:
        api_instance = init_brevo_client()
        if not api_instance:
            log_event(f"Failed to initialize Brevo client for {email}", level="error")
            return False
        
        sender_name = os.getenv("BREVO_SENDER_NAME", "RXZBot")
        sender_email = os.getenv("BREVO_SENDER_EMAIL", "noreply@rxzbot.com")
        
        email_obj = sib_api_v3_sdk.SendSmtpEmail(
            sender={"name": sender_name, "email": sender_email},
            to=[{"email": email}],
            subject="Your RXZBot Access Key",
            html_content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: 'Segoe UI', Arial, sans-serif;
                        margin: 0;
                        padding: 0;
                        background-color: #0a0e1a;
                    }}
                    .container {{
                        background: linear-gradient(135deg, #0a0e1a, #0d1526, #1a1f35);
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        padding: 20px;
                    }}
                    .card {{
                        background: linear-gradient(135deg, #0f1724 0%, #0d1520 100%);
                        border: 1px solid rgba(0, 212, 255, 0.12);
                        border-radius: 16px;
                        padding: 40px;
                        max-width: 520px;
                        width: 100%;
                        color: #eaf1ff;
                        box-shadow: 0 0 40px rgba(0, 212, 255, 0.06);
                    }}
                    h1 {{
                        color: #00d4ff;
                        margin: 0 0 8px 0;
                        font-size: 28px;
                    }}
                    .subtitle {{
                        color: #9aa4b2;
                        font-size: 14px;
                        margin-bottom: 28px;
                    }}
                    .info {{
                        color: #d0d8e8;
                        font-size: 14px;
                        line-height: 1.8;
                        margin: 18px 0;
                    }}
                    .key-box {{
                        background: linear-gradient(
                            135deg,
                            rgba(0,212,255,0.12),
                            rgba(0,212,255,0.05)
                        );
                        border: 2px solid rgba(0,212,255,0.35);
                        border-radius: 12px;
                        padding: 28px;
                        text-align: center;
                        margin: 28px 0;
                    }}
                    .access-key {{
                        font-family: 'Courier New', monospace;
                        font-size: 32px;
                        font-weight: 700;
                        color: #00d4ff;
                        letter-spacing: 4px;
                        margin: 0;
                        word-break: break-all;
                    }}
                    .key-label {{
                        color: #9aa4b2;
                        font-weight: 600;
                        margin-top: 14px;
                        font-size: 12px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                    }}
                    .item-info {{
                        background: rgba(0,212,255,0.08);
                        border-left: 4px solid #00d4ff;
                        padding: 16px;
                        border-radius: 6px;
                        margin: 22px 0;
                        color: #d0d8e8;
                        font-size: 13px;
                    }}
                    .item-info strong {{
                        color: #00d4ff;
                        display: block;
                        margin-bottom: 6px;
                    }}
                    .steps {{
                        margin: 28px 0;
                    }}
                    .step {{
                        display: flex;
                        margin-bottom: 14px;
                        color: #d0d8e8;
                        font-size: 13px;
                    }}
                    .step-number {{
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        width: 28px;
                        height: 28px;
                        background: #00d4ff;
                        color: #0a0e1a;
                        border-radius: 50%;
                        font-weight: 700;
                        margin-right: 12px;
                        flex-shrink: 0;
                    }}
                    .support {{
                        background: rgba(46,213,115,0.08);
                        border-left: 4px solid #2ed573;
                        padding: 14px;
                        border-radius: 6px;
                        margin: 22px 0;
                        color: #b5bcc8;
                        font-size: 12px;
                    }}
                    .support strong {{
                        color: #2ed573;
                    }}
                    .footer {{
                        text-align: center;
                        color: #7a8294;
                        font-size: 12px;
                        margin-top: 32px;
                        border-top: 1px solid rgba(255,255,255,0.06);
                        padding-top: 18px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="card">
                        <h1>🎉 Your Access Key</h1>
                        <p class="subtitle">Welcome to RXZBot, {username}!</p>

                        <p class="info">Thank you for your purchase! Your payment has been approved and your access key is ready to use.</p>

                        <div class="key-box">
                            <p class="access-key">{access_key}</p>
                            <p class="key-label">Your Activation Key</p>
                        </div>

                        <div class="item-info">
                            <strong>📦 Purchased Item:</strong>
                            {item}
                        </div>

                        <div class="steps">
                            <div class="step">
                                <span class="step-number">1</span>
                                <span>Copy your access key from above</span>
                            </div>
                            <div class="step">
                                <span class="step-number">2</span>
                                <span>Visit <strong>rxzbot.com/redeem</strong> to activate</span>
                            </div>
                            <div class="step">
                                <span class="step-number">3</span>
                                <span>Paste your key and click Redeem</span>
                            </div>
                            <div class="step">
                                <span class="step-number">4</span>
                                <span>Your account will be activated instantly</span>
                            </div>
                        </div>

                        <div class="support">
                            <strong>💬 Need Help?</strong><br>
                            Contact us on Instagram (@rxzbotcom) or Discord (.gg/rxzbot) if you have any issues.
                        </div>

                        <p class="info" style="color: #9aa4b2; font-size: 12px;">
                            <strong>Important:</strong> Keep your access key safe and don't share it with anyone.
                        </p>

                        <div class="footer">
                            <p>© 2026 RXZBot. All rights reserved.</p>
                            <p>This is an automated message. Please do not reply to this email.</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
        )
        
        response = api_instance.send_transac_email(email_obj)
        log_event(f"Purchase key email sent to {email} for {item}", level="info")
        return True
        
    except ApiException as e:
        log_event(f"Brevo API error sending purchase key email to {email}: {e}", level="error")
        return False
    except Exception as e:
        log_event(f"Error sending purchase key email to {email}: {str(e)}", level="error")
        return False

@app.route('/forgot-password', methods=['GET'])
def forgot_password_page():
    """Display the forgot password page"""
    return render_template('forgot_password.html')

@app.route('/api/forgot-password/request', methods=['POST'])
def forgot_password_request():
    """Step 1: Request password reset - send code to email"""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        reset_token = generate_reset_token()
        
        # Check if user exists
        user = db_helper.get_user_by_email(email)
        if not user:
            # For security, don't reveal if email exists or not
            # Always return success to prevent account enumeration
            log_event(f"Password reset requested for non-existent email: {email}", level="warn")
            return jsonify({
                'message': 'If an account exists with this email, you will receive a code shortly.',
                'token': reset_token,
                'email_exists': False
            }), 200
        
        # Generate reset code
        reset_code = generate_reset_code()
        
        # Save to database with 5-minute expiry
        from init_database import PasswordReset
        expiry_time = datetime.utcnow() + timedelta(minutes=5)
        
        try:
            with db_helper.get_db() as db:
                # Delete any previous unused codes for this email
                db.query(PasswordReset).filter(
                    PasswordReset.email == email,
                    PasswordReset.used == False
                ).delete()
                
                # Create new reset record
                pwd_reset = PasswordReset(
                    email=email,
                    reset_code=reset_code,
                    expires_at=expiry_time,
                    used=False
                )
                db.add(pwd_reset)
        except Exception as e:
            log_event(f"Database error during password reset request: {str(e)}", level="error")
            return jsonify({'error': 'Database error. Please try again later.'}), 500
        
        # Send email with code
        email_sent = send_password_reset_email(email, reset_code)
        
        if email_sent:
            log_event(f"Password reset code sent to {email}", level="info")
            return jsonify({
                'message': 'If an account exists with this email, you will receive a code shortly.',
                'token': reset_token,
                'email_exists': True
            }), 200
        else:
            log_event(f"Failed to send reset code to {email}", level="error")
            return jsonify({
                'message': 'If an account exists with this email, you will receive a code shortly.',
                'token': reset_token,
                'email_exists': True
            }), 200
            
    except Exception as e:
        log_event(f"Error in password reset request: {str(e)}", level="error")
        return jsonify({'error': 'An error occurred. Please try again later.'}), 500

@app.route('/api/forgot-password/verify', methods=['POST'])
def forgot_password_verify():
    """Step 2: Verify the 6-digit code"""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        code = data.get('code', '').strip()
        token = data.get('token', '').strip()
        
        if not email or not code or not token:
            return jsonify({'error': 'Missing required fields'}), 400
        
        if not code.isdigit() or len(code) != 6:
            return jsonify({'error': 'Invalid code format'}), 400
        
        # Check if code is valid
        from init_database import PasswordReset
        try:
            with db_helper.get_db() as db:
                reset_record = db.query(PasswordReset).filter(
                    PasswordReset.email == email,
                    PasswordReset.reset_code == code,
                    PasswordReset.used == False,
                    PasswordReset.expires_at > datetime.utcnow()
                ).first()
                
                if not reset_record:
                    log_event(f"Invalid or expired reset code for {email}", level="warn")
                    return jsonify({'error': 'Invalid or expired code'}), 401
                
                # Mark as used after successful verification
                reset_record.used = True
                reset_record.used_at = datetime.utcnow()
                
                log_event(f"Password reset code verified for {email}", level="info")
                return jsonify({
                    'message': 'Code verified successfully',
                    'verified_token': generate_reset_token()
                }), 200
                
        except Exception as e:
            log_event(f"Database error during code verification: {str(e)}", level="error")
            return jsonify({'error': 'Verification error. Please try again.'}), 500
            
    except Exception as e:
        log_event(f"Error in password verification: {str(e)}", level="error")
        return jsonify({'error': 'An error occurred. Please try again later.'}), 500

@app.route('/api/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    """Step 3: Reset the password with new password"""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        new_password = data.get('password', '')
        token = data.get('token', '').strip()
        
        if not email or not new_password or not token:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Validate password strength
        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters long'}), 400
        
        if not any(c.isupper() for c in new_password):
            return jsonify({'error': 'Password must contain at least one uppercase letter'}), 400
        
        if not any(c.islower() for c in new_password):
            return jsonify({'error': 'Password must contain at least one lowercase letter'}), 400
        
        if not any(c.isdigit() for c in new_password):
            return jsonify({'error': 'Password must contain at least one number'}), 400
        
        if not any(c in '!@#$%^&*()_+-=[]{};\'"\\|,.<>/?`~' for c in new_password):
            return jsonify({'error': 'Password must contain at least one special character'}), 400
        
        # Check if user exists
        user = db_helper.get_user_by_email(email)
        if not user:
            log_event(f"Password reset attempted for non-existent email: {email}", level="warn")
            return jsonify({'error': 'User not found'}), 404
        
        # Hash new password
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Update password in database
        from init_database import UserCredential
        try:
            with db_helper.get_db() as db:
                cred = db.query(UserCredential).filter_by(email=email).first()
                if cred:
                    cred.password = password_hash
                    log_event(f"Password reset successful for {email}", level="info")
                    return jsonify({
                        'message': 'Password reset successfully',
                        'email': email
                    }), 200
                else:
                    return jsonify({'error': 'User credentials not found'}), 404
                    
        except Exception as e:
            log_event(f"Database error during password reset: {str(e)}", level="error")
            return jsonify({'error': 'Error resetting password. Please try again.'}), 500
            
    except Exception as e:
        log_event(f"Error in password reset: {str(e)}", level="error")
        return jsonify({'error': 'An error occurred. Please try again later.'}), 500


# Start Flask server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)