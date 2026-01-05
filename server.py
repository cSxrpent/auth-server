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
TESTIMONIALS_FILE = "testimonials.json"  # testimonials storage
GITHUB_TESTIMONIALS_PATH = "testimonials.json"  # GitHub path

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
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = "cSxrpent"
GITHUB_REPO = "auth-users"
GITHUB_BRANCH = "main"
GITHUB_PATH = "users.json"
GITHUB_KEYS_PATH = "keys.json"  # Add keys file path

# GitHub raw URL (public access, no token needed if repo is public)
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_PATH}"

USERS_FILE = "users.json"  # local fallback file
KEYS_FILE = "keys.json"  # activation keys storage
STATS_FILE = "stats.json"  # track user connection counts
LAST_CONNECTED_FILE = "last_connected.json"  # track last connection per user

CET_OFFSET = timedelta(hours=1)  # CET = UTC+1 in winter

# -----------------------
# Keys management helpers
# -----------------------
def load_keys_from_github():
    """Fetch keys.json from GitHub API (no cache). Returns list of keys or None on failure."""
    try:
        # Use GitHub API instead of raw URL to avoid cache
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_KEYS_PATH}"
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
            keys = json.loads(decoded)
            print(f"✓ Loaded {len(keys)} keys from GitHub API")
            return keys
        else:
            print(f"✗ GitHub API fetch failed for keys: {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Error fetching keys from GitHub API: {e}")
        return None

def _github_get_keys_file():
    """Return (ok, info). If ok True: info={'content': <python obj list>, 'sha': <sha>}"""
    if not GITHUB_TOKEN:
        return False, {"error": "no_github_token"}
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_KEYS_PATH}"
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
        elif r.status_code == 404:
            # File doesn't exist yet, that's ok
            return True, {"content": [], "sha": None}
        else:
            return False, {"error": f"gh_get_status_{r.status_code}", "detail": r.text}
    except Exception as e:
        return False, {"error": f"gh_get_exception:{e}"}

def _github_put_keys_file(new_keys, sha=None):
    """Create/Update keys.json on GitHub. Return (ok, detail)."""
    if not GITHUB_TOKEN:
        return False, {"error": "no_github_token"}
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_KEYS_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    content_b64 = base64.b64encode(json.dumps(new_keys, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"Update keys.json via server at {(datetime.utcnow() + CET_OFFSET).isoformat()}Z",
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

def load_keys():
    """Try GitHub first, then fallback to local keys.json. Overwrite local if different from GitHub."""
    print("🔍 Loading keys...")
    
    # Try GitHub API first
    keys = load_keys_from_github()
    if keys is not None:
        print(f"✅ Loaded keys from GitHub: {len(keys)} keys")
        
        # Check if local file exists and differs
        try:
            with open(KEYS_FILE, "r", encoding="utf-8") as f:
                local_keys = json.load(f)
            
            # Normalize for comparison (sort by code)
            def normalize(k_list):
                return sorted(k_list, key=lambda x: x.get('code', '').lower())
            
            github_normalized = normalize(keys)
            local_normalized = normalize(local_keys)
            
            if github_normalized != local_normalized:
                print("🔄 Local keys file differs from GitHub, overwriting local with GitHub data")
                with open(KEYS_FILE, "w", encoding="utf-8") as f:
                    json.dump(keys, f, indent=2, ensure_ascii=False)
                log_event("Overwrote local keys.json with GitHub data")
            else:
                print("✅ Local keys file matches GitHub")
        
        except FileNotFoundError:
            print("📝 Local keys.json not found, creating it with GitHub data")
            with open(KEYS_FILE, "w", encoding="utf-8") as f:
                json.dump(keys, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error checking/comparing local keys file: {e}")
        
        return keys
    
    # Fallback to local file
    print("⚠️ GitHub failed for keys, falling back to local file")
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            local_keys = json.load(f)
            print(f"✅ Loaded keys from local: {len(local_keys)} keys")
            return local_keys
    except FileNotFoundError:
        print("⚠ Local keys.json not found")
        return []
    except Exception as e:
        print(f"⚠ Error loading local keys.json: {e}")
        return []

def save_keys(keys):
    """
    Write local file then try to push to GitHub if token is present.
    Returns dict describing results.
    """
    result = {"saved_local": False, "github": None}
    # write local
    try:
        with open(KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2, ensure_ascii=False)
        result["saved_local"] = True
    except Exception as e:
        result["saved_local"] = False
        result["local_error"] = str(e)
    
    # try pushing to GitHub
    if GITHUB_TOKEN:
        ok, info = _github_get_keys_file()
        sha = info.get("sha") if ok else None
        ok2, put_res = _github_put_keys_file(keys, sha=sha)
        result["github"] = {"ok": ok2, "detail": put_res}
    else:
        result["github"] = {"ok": False, "detail": "no_github_token"}
    
    return result

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

def read_github_file(filename):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    params = {"ref": GITHUB_BRANCH}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        import base64
        content = base64.b64decode(response.json()['content']).decode('utf-8')
        return json.loads(content), response.json()['sha']
    return {}, None

def write_github_file(filename, data, sha=None):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    import base64
    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    payload = {"message": f"Update {filename}", "content": content, "branch": GITHUB_BRANCH}
    if sha:
        payload["sha"] = sha
    response = requests.put(url, headers=headers, json=payload)
    return response.status_code in [200, 201]

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

def search_wolvesville_player(username):
    """Search for player using managed tokens"""
    return wolvesville_api.search_player(username)

def get_wolvesville_player_profile(player_id):
    """Get player profile using managed tokens"""
    return wolvesville_api.get_player_profile(player_id)

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

def load_testimonials_from_github():
    """Fetch testimonials.json from GitHub API (no cache). Returns list or None on failure."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_TESTIMONIALS_PATH}"
        headers = {"Accept": "application/vnd.github.v3+json"}
        
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
        params = {"ref": GITHUB_BRANCH, "t": int(time.time())}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            content_b64 = data.get("content", "")
            decoded = base64.b64decode(content_b64.encode()).decode("utf-8")
            testimonials = json.loads(decoded)
            print(f"✓ Loaded {len(testimonials)} testimonials from GitHub API")
            return testimonials
        elif response.status_code == 404:
            print("ℹ️ testimonials.json not found on GitHub, will create on first save")
            return []
        else:
            print(f"✗ GitHub API fetch failed for testimonials: {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Error fetching testimonials from GitHub API: {e}")
        return None

def _github_get_testimonials_file():
    """Return (ok, info). If ok True: info={'content': <python obj list>, 'sha': <sha>}"""
    if not GITHUB_TOKEN:
        return False, {"error": "no_github_token"}
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_TESTIMONIALS_PATH}"
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
        elif r.status_code == 404:
            return True, {"content": [], "sha": None}
        else:
            return False, {"error": f"gh_get_status_{r.status_code}", "detail": r.text}
    except Exception as e:
        return False, {"error": f"gh_get_exception:{e}"}

def _github_put_testimonials_file(new_testimonials, sha=None):
    """Create/Update testimonials.json on GitHub. Return (ok, detail)."""
    if not GITHUB_TOKEN:
        return False, {"error": "no_github_token"}
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_TESTIMONIALS_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    content_b64 = base64.b64encode(json.dumps(new_testimonials, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"Update testimonials.json via server at {(datetime.utcnow() + CET_OFFSET).isoformat()}Z",
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

def load_testimonials():
    """Try GitHub first, then fallback to local testimonials.json. Overwrite local if different from GitHub."""
    print("🔍 Loading testimonials...")
    
    # Try GitHub API first
    testimonials = load_testimonials_from_github()
    if testimonials is not None:
        print(f"✅ Loaded testimonials from GitHub: {len(testimonials)} testimonials")
        
        # Check if local file exists and differs
        try:
            with open(TESTIMONIALS_FILE, "r", encoding="utf-8") as f:
                local_testimonials = json.load(f)
            
            # Normalize for comparison (sort by id)
            def normalize(t_list):
                return sorted(t_list, key=lambda x: x.get('id', '').lower())
            
            github_normalized = normalize(testimonials)
            local_normalized = normalize(local_testimonials)
            
            if github_normalized != local_normalized:
                print("🔄 Local testimonials file differs from GitHub, overwriting local with GitHub data")
                with open(TESTIMONIALS_FILE, "w", encoding="utf-8") as f:
                    json.dump(testimonials, f, indent=2, ensure_ascii=False)
                log_event("Overwrote local testimonials.json with GitHub data")
            else:
                print("✅ Local testimonials file matches GitHub")
        
        except FileNotFoundError:
            print("📝 Local testimonials.json not found, creating it with GitHub data")
            with open(TESTIMONIALS_FILE, "w", encoding="utf-8") as f:
                json.dump(testimonials, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error checking/comparing local testimonials file: {e}")
        
        return testimonials
    
    # Fallback to local file
    print("⚠️ GitHub failed for testimonials, falling back to local file")
    try:
        with open(TESTIMONIALS_FILE, "r", encoding="utf-8") as f:
            local_testimonials = json.load(f)
            print(f"✅ Loaded testimonials from local: {len(local_testimonials)} testimonials")
            return local_testimonials
    except FileNotFoundError:
        print("⚠ Local testimonials.json not found")
        return []
    except Exception as e:
        print(f"⚠ Error loading local testimonials.json: {e}")
        return []

def save_testimonials(testimonials):
    """
    Write local file then try to push to GitHub if token is present.
    Returns dict describing results.
    """
    result = {"saved_local": False, "github": None}
    # write local
    try:
        with open(TESTIMONIALS_FILE, "w", encoding="utf-8") as f:
            json.dump(testimonials, f, indent=2, ensure_ascii=False)
        result["saved_local"] = True
        print(f"✅ Saved {len(testimonials)} testimonials to local file")
    except Exception as e:
        result["saved_local"] = False
        result["local_error"] = str(e)
        print(f"❌ Error saving local testimonials: {e}")
    
    # try pushing to GitHub
    if GITHUB_TOKEN:
        ok, info = _github_get_testimonials_file()
        sha = info.get("sha") if ok else None
        ok2, put_res = _github_put_testimonials_file(testimonials, sha=sha)
        result["github"] = {"ok": ok2, "detail": put_res}
        if ok2:
            print(f"✅ Pushed {len(testimonials)} testimonials to GitHub")
        else:
            print(f"❌ Failed to push testimonials to GitHub: {put_res}")
    else:
        result["github"] = {"ok": False, "detail": "no_github_token"}
        print("⚠️ No GitHub token, testimonials only saved locally")
    
    return result
        
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
        "test": {"amount": "0.05", "description": "Test Purchase", "days": 1},
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
        "test": {"amount": "0.05", "description": "Test Purchase"},
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
    info = {
        "env_file_exists": os.path.exists('.env'),
#        "paypal_client_id_set": bool(PAYPAL_CLIENT_ID),
#        "paypal_client_id_prefix": PAYPAL_CLIENT_ID[:10] if PAYPAL_CLIENT_ID else None,
#        "paypal_client_secret_set": bool(PAYPAL_CLIENT_SECRET),
        "paypal_mode": PAYPAL_MODE,
#        "secret_key_set": bool(app.secret_key),
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
        
        # Load user credentials
        credentials, sha = read_github_file('user-credentials.json')
        
        # Check if email already exists
        if email in credentials:
            return render_template('register.html', error="Email already exists")
        
        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Add new user
        credentials[email] = {
            "password": hashed_password,
            "accounts": []
        }
        
        # Save to GitHub
        if write_github_file('user-credentials.json', credentials, sha):
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
        
        # Load user credentials
        credentials, _ = read_github_file('user-credentials.json')
        
        # Check if user exists
        if email not in credentials:
            return render_template('loginuser.html', error="Invalid email or password")
        
        # Verify password
        stored_password = credentials[email]['password']
        if bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
            session['user_email'] = email
            return redirect(url_for('dashboard'))
        else:
            return render_template('loginuser.html', error="Invalid email or password")
    
    return render_template('loginuser.html')

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('loginuser'))
    
    email = session['user_email']
    credentials, _ = read_github_file('user-credentials.json')
    user_accounts = credentials.get(email, {}).get('accounts', [])
    
    # Get selected account or default to first
    selected_account = request.args.get('account')
    if not selected_account and user_accounts:
        selected_account = user_accounts[0]
    
    account_data = None
    account_xp = None
    license_data = None
    total_bot_xp = 0
    levels_gained = 0
    
    if selected_account:
        # FRESH API calls - NO CACHING for account switch
        player = search_wolvesville_player(selected_account)
        
        if player:
            account_data = get_wolvesville_player_profile(player['id'])
        
        # Get XP data (fresh, not cached)
        xp_data, _ = read_github_file('user-XP.json')
        account_xp = xp_data.get(selected_account, {})
        
        # Calculate total bot XP and levels gained
        if account_xp:
            # Sum all daily XP
            total_bot_xp = sum(account_xp.get('daily', {}).values())
            
            # Calculate levels gained (2000 XP per level)
            levels_gained = total_bot_xp // 2000
        
        # Get license data (fresh, not cached)
        users_data, _ = read_github_file('users.json')
        license_data = next((u for u in users_data if u['username'] == selected_account), None)
    
    # Get current date info for XP display
    from datetime import datetime
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_week = datetime.now().strftime('%Y-W%U')
    current_month = datetime.now().strftime('%Y-%m')
    
    return render_template('dashboard.html', 
                         email=email, 
                         accounts=user_accounts,
                         selected_account=selected_account,
                         account_data=account_data,
                         account_xp=account_xp,
                         license_data=license_data,
                         current_date=current_date,
                         current_week=current_week,
                         current_month=current_month,
                         total_bot_xp=total_bot_xp,
                         levels_gained=levels_gained)

@app.route('/api/license/pause', methods=['POST'])
def pause_license():
    """Pause license for an account"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'error': 'Username required'}), 400
    
    # Verify this user owns this account
    email = session['user_email']
    credentials, _ = read_github_file('user-credentials.json')
    user_accounts = credentials.get(email, {}).get('accounts', [])
    
    if username not in user_accounts:
        return jsonify({'success': False, 'error': 'Account not found'}), 403
    
    # Load users data
    users_data, sha = read_github_file('users.json')
    user = next((u for u in users_data if u['username'] == username), None)
    
    if not user:
        return jsonify({'success': False, 'error': 'License not found'}), 404
    
    # Store current expiry date and mark as paused
    if 'paused' not in user or not user['paused']:
        user['paused'] = True
        user['paused_at'] = datetime.now().strftime('%Y-%m-%d')
        user['remaining_days'] = (datetime.strptime(user['expires'], '%Y-%m-%d') - datetime.now()).days
        
        # Write back to GitHub
        if write_github_file('users.json', users_data, sha):
            log_event(f"License paused: {username} ({user['remaining_days']} days remaining)")
            return jsonify({'success': True, 'message': 'License paused'})
    
    return jsonify({'success': False, 'error': 'License already paused'}), 400

@app.route('/api/license/resume', methods=['POST'])
def resume_license():
    """Resume paused license"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'error': 'Username required'}), 400
    
    # Verify this user owns this account
    email = session['user_email']
    credentials, _ = read_github_file('user-credentials.json')
    user_accounts = credentials.get(email, {}).get('accounts', [])
    
    if username not in user_accounts:
        return jsonify({'success': False, 'error': 'Account not found'}), 403
    
    # Load users data
    users_data, sha = read_github_file('users.json')
    user = next((u for u in users_data if u['username'] == username), None)
    
    if not user:
        return jsonify({'success': False, 'error': 'License not found'}), 404
    
    # Resume license
    if user.get('paused', False):
        remaining_days = user.get('remaining_days', 0)
        new_expiry = (datetime.now() + timedelta(days=remaining_days)).strftime('%Y-%m-%d')
        
        user['expires'] = new_expiry
        user['paused'] = False
        user.pop('paused_at', None)
        user.pop('remaining_days', None)
        
        # Write back to GitHub
        if write_github_file('users.json', users_data, sha):
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
    
@app.route('/add_account', methods=['GET', 'POST'])
def add_account():
    if 'user_email' not in session:
        return redirect(url_for('loginuser'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        
        # Search for player
        player = search_wolvesville_player(username)
        if not player:
            return render_template('add_account.html', error="Player not found")
        
        # Generate verification code
        code = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
        session['verification_code'] = code
        session['verification_username'] = username
        session['verification_player_id'] = player['id']
        
        return render_template('add_account.html', 
                             verification_code=code, 
                             username=username,
                             step='verify')
    
    return render_template('add_account.html', step='username')

@app.route('/verify_account', methods=['POST'])
def verify_account():
    if 'user_email' not in session:
        return redirect(url_for('loginuser'))
    
    stored_code = session.get('verification_code')
    username = session.get('verification_username')
    player_id = session.get('verification_player_id')
    
    # Get player profile
    profile = get_wolvesville_player_profile(player_id)
    if not profile:
        return jsonify({'success': False, 'error': 'Could not fetch player profile'})
    
    # Check if code is in biography
    biography = profile.get('personalMsg', '')
    if stored_code not in biography:
        return jsonify({'success': False, 'error': 'Verification code not found in biography'})
    
    # Add account to user
    email = session['user_email']
    credentials, sha = read_github_file('user-credentials.json')
    
    if username not in credentials[email]['accounts']:
        credentials[email]['accounts'].append(username)
        write_github_file('user-credentials.json', credentials, sha)
    
    # Add to users.json with default expiry
    users_data, users_sha = read_github_file('users.json')
    if not any(u['username'] == username for u in users_data):
        users_data.append({
            "username": username,
            "expires": (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        })
        write_github_file('users.json', users_data, users_sha)
    
    # Clear session verification data
    session.pop('verification_code', None)
    session.pop('verification_username', None)
    session.pop('verification_player_id', None)
    
    return jsonify({'success': True})

@app.route('/xp/add', methods=['POST'])
def add_xp():
    data = request.json
    player_id = data.get('player_id')
    xp_amount = data.get('xp_amount')
    username = data.get('username')
    
    if not all([player_id, xp_amount, username]):
        return jsonify({'success': False, 'error': 'Missing parameters'})
    
    # Load XP data
    xp_data, sha = read_github_file('user-XP.json')
    
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
    
    # Save to GitHub
    if write_github_file('user-XP.json', xp_data, sha):
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Failed to save XP data'})

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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Starting server on port {port}")
    print(f"📁 GitHub repo: {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"📄 GitHub users file: {GITHUB_PATH}")
    print(f"🎁 GitHub keys file: {GITHUB_KEYS_PATH}")
    app.run(host="0.0.0.0", port=port, debug=True)