import os
import time
import json
import base64
import requests
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class TokenManager:
    def __init__(self):
        self.tokens = {
            'idToken': None,
            'refreshToken': None,
            'cfJwt': None
        }
        self.email = os.getenv('WOLVESVILLE_EMAIL')
        self.password = os.getenv('WOLVESVILLE_PASSWORD')
        self.twocaptcha_key = os.getenv('TWOCAPTCHA_API_KEY')
        
        # CRITICAL: Validate environment variables
        if not self.email or not self.password:
            raise ValueError("❌ WOLVESVILLE_EMAIL and WOLVESVILLE_PASSWORD must be set in .env")
        if not self.twocaptcha_key:
            raise ValueError("❌ TWOCAPTCHA_API_KEY must be set in .env")
        
        self.lock = threading.Lock()
        self.last_refresh = None
        print(f"✅ TokenManager initialized for {self.email}")
        
    def decode_jwt(self, token):
        """Decode JWT token to check expiration - FIXED"""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return None
            
            # Add proper padding for base64 decoding
            payload_part = parts[1]
            padding = 4 - (len(payload_part) % 4)
            if padding != 4:
                payload_part += '=' * padding
            
            payload = json.loads(base64.urlsafe_b64decode(payload_part).decode('utf-8'))
            return payload
        except Exception as e:
            print(f"⚠️ Error decoding JWT: {e}")
            return None
    
    def is_token_expired(self, token):
        """Check if token expires in less than 5 minutes"""
        if not token:
            return True
        
        payload = self.decode_jwt(token)
        if not payload or 'exp' not in payload:
            return True
        
        expiry_time = payload['exp'] * 1000  # Convert to milliseconds
        time_remaining = expiry_time - (time.time() * 1000)
        
        # Token is "expired" if less than 5 minutes remaining
        is_expired = time_remaining < (5 * 60 * 1000)
        
        if is_expired:
            print(f"⚠️ Token expiring in {int(time_remaining / 1000)} seconds")
        
        return is_expired
    
    def solve_turnstile_captcha(self):
        """Solve Cloudflare Turnstile captcha using 2Captcha"""
        print("🔐 Solving Turnstile captcha with 2Captcha...")
        
        # Step 1: Submit captcha task
        create_task_url = "https://2captcha.com/in.php"
        params = {
            'key': self.twocaptcha_key,
            'method': 'turnstile',
            'sitekey': '0x4AAAAAAATLZS5RyqlMGxsL',
            'pageurl': 'https://www.wolvesville.com',
            'json': 1
        }
        
        try:
            response = requests.post(create_task_url, data=params, timeout=30)
            result = response.json()
            
            if result.get('status') != 1:
                raise Exception(f"2Captcha task creation failed: {result}")
            
            task_id = result.get('request')
            print(f"📋 Captcha task created: {task_id}")
            
            # Step 2: Wait and retrieve solution
            get_result_url = "https://2captcha.com/res.php"
            max_attempts = 60  # 5 minutes max
            
            for attempt in range(max_attempts):
                time.sleep(5)  # Wait 5 seconds between checks
                
                result_params = {
                    'key': self.twocaptcha_key,
                    'action': 'get',
                    'id': task_id,
                    'json': 1
                }
                
                result_response = requests.get(get_result_url, params=result_params, timeout=30)
                result_data = result_response.json()
                
                if result_data.get('status') == 1:
                    token = result_data.get('request')
                    print("✅ Captcha solved successfully!")
                    return token
                elif result_data.get('request') == 'CAPCHA_NOT_READY':
                    if attempt % 6 == 0:  # Print every 30 seconds
                        print(f"⏳ Waiting for captcha solution... ({attempt * 5}s elapsed)")
                    continue
                else:
                    raise Exception(f"2Captcha error: {result_data}")
            
            raise Exception("Captcha solving timeout (5 minutes)")
            
        except Exception as e:
            print(f"❌ Error solving captcha: {e}")
            raise
    
    def refresh_cf_jwt(self):
        """Refresh Cloudflare JWT using Turnstile captcha"""
        print("🔄 Refreshing Cloudflare JWT...")
        
        try:
            # Solve captcha
            turnstile_token = self.solve_turnstile_captcha()
            
            # Verify captcha to get new cf-jwt
            verify_url = "https://auth.api-wolvesville.com/cloudflareTurnstile/verify"
            payload = {
                'token': turnstile_token,
                'siteKey': '0x4AAAAAAATLZS5RyqlMGxsL'
            }
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            response = requests.post(verify_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.tokens['cfJwt'] = data.get('jwt')
                print("✅ Cloudflare JWT refreshed successfully")
                return True
            else:
                print(f"❌ Failed to verify captcha: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error refreshing CF JWT: {e}")
            return False
    
    def sign_in_with_email_password(self):
        """Complete authentication with email and password"""
        print(f"🔑 Signing in as {self.email}...")
        
        try:
            # Ensure we have a valid CF JWT first
            if not self.tokens.get('cfJwt'):
                print("🔐 No CF JWT found, obtaining one...")
                if not self.refresh_cf_jwt():
                    raise Exception("Failed to get CF JWT")
            
            # Sign in
            signin_url = "https://auth.api-wolvesville.com/players/signInWithEmailAndPassword"
            payload = {
                'email': self.email,
                'password': self.password
            }
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Cf-JWT': self.tokens['cfJwt']
            }
            
            response = requests.post(signin_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.tokens['idToken'] = data.get('idToken')
                self.tokens['refreshToken'] = data.get('refreshToken')
                self.last_refresh = datetime.now()
                print("✅ Sign in successful!")
                
                # Log token expiry
                payload = self.decode_jwt(self.tokens['idToken'])
                if payload and 'exp' in payload:
                    expiry = datetime.fromtimestamp(payload['exp'])
                    print(f"🕒 Token valid until: {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
                
                return True
            elif response.status_code == 403:
                # CF JWT expired, try refreshing it
                print("⚠️ CF JWT rejected (403), refreshing...")
                if self.refresh_cf_jwt():
                    print("🔄 Retrying sign in with new CF JWT...")
                    return self.sign_in_with_email_password()  # Retry
                return False
            else:
                print(f"❌ Sign in failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error during sign in: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def ensure_authenticated(self):
        """Ensure we have valid tokens, authenticate if we don't"""
        if not self.tokens.get('idToken'):
            print("🔑 No tokens found, performing initial authentication...")
            return self.sign_in_with_email_password()
        return self.refresh_tokens()
    
    def refresh_tokens(self):
        """Main token refresh method"""
        with self.lock:
            print("🔄 Checking token status...")
            
            # Check if token is still valid
            if not self.is_token_expired(self.tokens.get('idToken')):
                print("✅ Token still valid, no refresh needed")
                return True
            
            print("⚠️ Token expired or expiring soon, refreshing...")
            return self.sign_in_with_email_password()
    
    def get_valid_tokens(self):
        """Get valid tokens, refreshing if necessary"""
        self.ensure_authenticated()
        return {
            'bearer': self.tokens['idToken'],
            'cfJwt': self.tokens['cfJwt']
        }

    def get_tokens_for_account(self, email, password):
        """Get valid tokens for a specific account (used for gem accounts)"""
        print(f"🔑 Getting tokens for account: {email}")

        # Create a lightweight temporary TokenManager-like object WITHOUT
        # running __init__ (which validates environment vars and prints).
        # This avoids re-validating global env and reduces duplicated logs
        # and captcha requests when authenticating multiple accounts.
        temp_manager = object.__new__(TokenManager)

        # Minimal attributes required by authentication methods
        temp_manager.tokens = {'idToken': None, 'refreshToken': None, 'cfJwt': None}
        temp_manager.email = email
        temp_manager.password = password
        temp_manager.twocaptcha_key = self.twocaptcha_key
        temp_manager.lock = threading.Lock()
        temp_manager.last_refresh = None

        # Authenticate with this account's credentials
        if not temp_manager.ensure_authenticated():
            raise Exception(f"Failed to authenticate with account {email}")

        return {
            'bearer': temp_manager.tokens['idToken'],
            'cfJwt': temp_manager.tokens['cfJwt']
        }
    
    def start_auto_refresh(self):
        """Start automatic token refresh - FIXED to authenticate immediately"""
        # Authenticate IMMEDIATELY on startup
        print("🚀 Starting token manager...")
        try:
            if not self.ensure_authenticated():
                print("⚠️ Warning: Initial authentication failed!")
                print("   Will retry on first API call")
        except Exception as e:
            print(f"⚠️ Warning: Initial authentication error: {e}")
            print("   Will retry on first API call")
        
        def periodic_refresh():
            while True:
                time.sleep(50 * 60)  # Every 50 minutes
                print("⏰ Periodic token refresh check...")
                try:
                    self.refresh_tokens()
                except Exception as e:
                    print(f"⚠️ Periodic refresh error: {e}")
        
        # Start periodic refresh thread
        refresh_thread = threading.Thread(target=periodic_refresh, daemon=True)
        refresh_thread.start()
        print("✅ Automatic token refresh started (every 50 minutes)")

# Global token manager instance
token_manager = TokenManager()