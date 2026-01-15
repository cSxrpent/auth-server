import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from init_database import User, Key, Testimonial, UserCredential, UserXP, Stats, LastConnected, Log, RecentConnection
from sqlalchemy.exc import OperationalError

# Database connection with PROPER pool configuration
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,        # Check connection health before use
    pool_size=10,              # Base pool (10 connections)
    max_overflow=15,           # Allow 15 extra connections under load
    pool_timeout=30,           # Wait max 30s for connection
    pool_recycle=1800,         # Recycle connections after 30min
    echo_pool=False            # Set to True for debugging
)

# ✅ Use plain sessionmaker (NOT scoped_session)
SessionLocal = sessionmaker(bind=engine)

# Ensure unique index on user_credentials.email exists (idempotent)
from sqlalchemy import text
try:
    with engine.connect() as conn:
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_credentials_email ON user_credentials (email);"))
        conn.commit()
except Exception:
    pass

@contextmanager
def get_db():
    """Context manager for database sessions - PROPERLY releases connections"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()  # ✅ Now this actually returns connection to pool

# ==================== USER FUNCTIONS ====================

def load_users():
    """Load all users from database"""
    try:
        with get_db() as db:
            users = db.query(User).all()
            return [
                {
                    "username": u.username,
                    "player_id": getattr(u, 'player_id', None),
                    "expires": u.expires,
                    "paused": u.paused,
                    "paused_at": u.paused_at,
                    "remaining_days": u.remaining_days,
                    "last_nickname": getattr(u, 'last_nickname', None),
                    "first_connection_date": getattr(u, 'first_connection_date', None)
                } 
                for u in users
            ]
    except Exception as e:
        print(f"⚠️ Error loading users: {e}")
        return []

def save_users(users_list):
    """Save/update multiple users"""
    try:
        with get_db() as db:
            for user_data in users_list:
                user = db.query(User).filter_by(username=user_data['username']).first()
                if user:
                    user.expires = user_data['expires']
                    user.paused = user_data.get('paused', False)
                    user.paused_at = user_data.get('paused_at')
                    user.remaining_days = user_data.get('remaining_days')
                    if 'player_id' in user_data:
                        user.player_id = user_data['player_id']
                    if 'last_nickname' in user_data:
                        user.last_nickname = user_data['last_nickname']
                    if 'first_connection_date' in user_data:
                        user.first_connection_date = user_data['first_connection_date']
                else:
                    new_user = User(
                        username=user_data['username'],
                        player_id=user_data.get('player_id'),
                        expires=user_data['expires'],
                        paused=user_data.get('paused', False),
                        paused_at=user_data.get('paused_at'),
                        remaining_days=user_data.get('remaining_days'),
                        last_nickname=user_data.get('last_nickname'),
                        first_connection_date=user_data.get('first_connection_date')
                    )
                    db.add(new_user)
            return {"saved_local": True, "storage": {"ok": True, "detail": "saved to database"}}
    except Exception as e:
        print(f"⚠️ Error saving users: {e}")
        return {"saved_local": False, "storage": {"ok": False, "detail": str(e)}}

def find_user(users, username):
    """Find user by username (case-insensitive)"""
    for u in users:
        if u["username"].lower() == username.lower():
            return u
    return None

# ==================== KEY FUNCTIONS ====================

def load_keys():
    """Load all activation keys"""
    try:
        with get_db() as db:
            keys = db.query(Key).all()
            return [
                {
                    "code": k.code,
                    "duration": k.duration,
                    "created": k.created,
                    "used": k.used,
                    "used_by": k.used_by,
                    "used_at": k.used_at
                }
                for k in keys
            ]
    except Exception as e:
        print(f"⚠️ Error loading keys: {e}")
        return []

def save_keys(keys_list):
    """Save/update multiple keys"""
    try:
        with get_db() as db:
            for key_data in keys_list:
                key = db.query(Key).filter_by(code=key_data['code']).first()
                if key:
                    key.duration = key_data['duration']
                    key.used = key_data.get('used', False)
                    key.used_by = key_data.get('used_by')
                    key.used_at = key_data.get('used_at')
                else:
                    new_key = Key(
                        code=key_data['code'],
                        duration=key_data['duration'],
                        created=key_data['created'],
                        used=key_data.get('used', False),
                        used_by=key_data.get('used_by'),
                        used_at=key_data.get('used_at')
                    )
                    db.add(new_key)
            return {"saved_local": True, "storage": {"ok": True, "detail": "saved to database"}}
    except Exception as e:
        print(f"⚠️ Error saving keys: {e}")
        return {"saved_local": False, "storage": {"ok": False, "detail": str(e)}}

def find_key(keys, key_code):
    """Find key by code"""
    for k in keys:
        if k["code"] == key_code:
            return k
    return None

# ==================== TESTIMONIAL FUNCTIONS ====================

def load_testimonials():
    """Load all testimonials"""
    try:
        with get_db() as db:
            testimonials = db.query(Testimonial).all()
            return [
                {
                    "id": t.id,
                    "username": t.username,
                    "rating": t.rating,
                    "comment": t.comment,
                    "anonymous": t.anonymous,
                    "date": t.date,
                    "approved": t.approved
                }
                for t in testimonials
            ]
    except Exception as e:
        print(f"⚠️ Error loading testimonials: {e}")
        return []

def save_testimonials(testimonials_list):
    """Save/update multiple testimonials"""
    try:
        with get_db() as db:
            for test_data in testimonials_list:
                testimonial = db.query(Testimonial).filter_by(id=test_data['id']).first()
                if testimonial:
                    testimonial.username = test_data['username']
                    testimonial.rating = test_data['rating']
                    testimonial.comment = test_data['comment']
                    testimonial.anonymous = test_data.get('anonymous', False)
                    testimonial.date = test_data['date']
                    testimonial.approved = test_data.get('approved', False)
                else:
                    new_testimonial = Testimonial(
                        id=test_data['id'],
                        username=test_data['username'],
                        rating=test_data['rating'],
                        comment=test_data['comment'],
                        anonymous=test_data.get('anonymous', False),
                        date=test_data['date'],
                        approved=test_data.get('approved', False)
                    )
                    db.add(new_testimonial)
            return {"saved_local": True, "storage": {"ok": True, "detail": "saved to database"}}
    except Exception as e:
        print(f"⚠️ Error saving testimonials: {e}")
        return {"saved_local": False, "storage": {"ok": False, "detail": str(e)}}

# ==================== STORAGE FUNCTIONS ====================

def read_storage_impl(filename):
    """Read user credentials or XP data from storage (DB-backed)."""
    try:
        with get_db() as db:
            if filename == 'user-credentials.json':
                creds = db.query(UserCredential).all()
                data = {
                    c.email: {
                        "password": c.password,
                        "accounts": c.accounts or []
                    }
                    for c in creds
                }
                return data, None
            
            elif filename == 'user-XP.json':
                xp_records = db.query(UserXP).all()
                data = {
                    x.username: {
                        "daily": x.daily or {},
                        "weekly": x.weekly or {},
                        "monthly": x.monthly or {}
                    }
                    for x in xp_records
                }
                return data, None
            
            elif filename == 'users.json':
                return load_users(), None
    except Exception as e:
        print(f"⚠️ Error reading storage {filename}: {e}")
    
    return {}, None

def write_storage_impl(filename, data, sha=None):
    """Write user credentials or XP data to storage (DB-backed)."""
    try:
        with get_db() as db:
            if filename == 'user-credentials.json':
                for email, cred_data in data.items():
                    cred = db.query(UserCredential).filter_by(email=email).first()
                    if cred:
                        cred.password = cred_data['password']
                        cred.accounts = cred_data.get('accounts', [])
                    else:
                        new_cred = UserCredential(
                            email=email,
                            password=cred_data['password'],
                            accounts=cred_data.get('accounts', [])
                        )
                        db.add(new_cred)
                return True

            elif filename == 'user-XP.json':
                for username, xp_data in data.items():
                    xp = db.query(UserXP).filter_by(username=username).first()
                    if xp:
                        xp.daily = xp_data.get('daily', {})
                        xp.weekly = xp_data.get('weekly', {})
                        xp.monthly = xp_data.get('monthly', {})
                    else:
                        new_xp = UserXP(
                            username=username,
                            daily=xp_data.get('daily', {}),
                            weekly=xp_data.get('weekly', {}),
                            monthly=xp_data.get('monthly', {})
                        )
                        db.add(new_xp)
                return True

            elif filename == 'users.json':
                save_users(data)
                return True
    except Exception as e:
        print(f"⚠️ Error writing storage {filename}: {e}")
        return False

    return False

# Aliases for storage access
def read_storage(filename):
    """Alias for reading from storage (DB-backed)."""
    return read_storage_impl(filename)

def write_storage(filename, data, sha=None):
    """Alias for writing to storage (DB-backed)."""
    return write_storage_impl(filename, data, sha=sha)

# ==================== USER CREDENTIALS FUNCTIONS ====================

def get_user_by_email(email: str):
    """Return user credential row for given email or None."""
    try:
        with get_db() as db:
            user = db.query(UserCredential).filter(UserCredential.email == email).first()
            if not user:
                return None
            return {"email": user.email, "password": user.password, "accounts": user.accounts or []}
    except OperationalError as e:
        print(f"⚠️ DB connection error in get_user_by_email: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in get_user_by_email: {e}")
        return None

def create_user(email: str, password_hash: str):
    """Create a new user credential with empty accounts. Returns True on success, False if exists."""
    try:
        with get_db() as db:
            existing = db.query(UserCredential).filter(UserCredential.email == email).first()
            if existing:
                return False
            new = UserCredential(email=email, password=password_hash, accounts=[])
            db.add(new)
            return True
    except OperationalError as e:
        print(f"⚠️ DB connection error in create_user: {e}")
        return False
    except Exception as e:
        print(f"⚠️ Unexpected error in create_user: {e}")
        return False

def verify_user_password(email: str, password_plain: str):
    """Verify password; returns tuple (ok, email) where ok is bool."""
    import bcrypt as _bcrypt
    try:
        with get_db() as db:
            row = db.query(UserCredential.email, UserCredential.password).filter(UserCredential.email == email).first()
            if not row:
                return False, None
            stored = row.password
            try:
                ok = _bcrypt.checkpw(password_plain.encode('utf-8'), stored.encode('utf-8'))
            except Exception:
                return False, None
            return ok, row.email
    except OperationalError as e:
        print(f"⚠️ DB connection error in verify_user_password: {e}")
        return False, None
    except Exception as e:
        print(f"⚠️ Unexpected error in verify_user_password: {e}")
        return False, None

def get_user_accounts(user_identifier):
    """Return list of accounts for the given user identifier (email)."""
    try:
        with get_db() as db:
            row = db.query(UserCredential).filter(UserCredential.email == user_identifier).first()
            if not row:
                return []
            return row.accounts or []
    except OperationalError as e:
        print(f"⚠️ DB connection error in get_user_accounts: {e}")
        return []
    except Exception as e:
        print(f"⚠️ Unexpected error in get_user_accounts: {e}")
        return []

def add_account_to_user(email: str, username: str):
    """Add account to user's account list"""
    try:
        with get_db() as db:
            from sqlalchemy.orm.attributes import flag_modified
            
            row = db.query(UserCredential).filter(UserCredential.email == email).first()
            if not row:
                print(f"❌ User not found: {email}")
                return False
            
            accounts = row.accounts or []
            
            if username in accounts:
                print(f"⚠️ Account '{username}' already linked to {email}")
                return True
            
            accounts.append(username)
            row.accounts = accounts
            
            # Tell SQLAlchemy this column was modified
            flag_modified(row, 'accounts')
            
            db.flush()
            
            print(f"✅ Added account '{username}' to user {email}")
            print(f"📋 New accounts list: {row.accounts}")
            
            return True
            
    except OperationalError as e:
        print(f"❌ DB connection error in add_account_to_user: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in add_account_to_user: {e}")
        import traceback
        traceback.print_exc()
        return False

def remove_account_from_user(email: str, username: str):
    """Remove account from user's account list"""
    try:
        with get_db() as db:
            from sqlalchemy.orm.attributes import flag_modified
            
            row = db.query(UserCredential).filter(UserCredential.email == email).first()
            if not row:
                print(f"❌ User not found: {email}")
                return False
            
            accounts = row.accounts or []
            
            if username not in accounts:
                print(f"⚠️ Account '{username}' not found in {email}'s accounts")
                return False
            
            accounts.remove(username)
            row.accounts = accounts
            
            # Tell SQLAlchemy this column was modified
            flag_modified(row, 'accounts')
            
            db.flush()
            
            print(f"✅ Removed account '{username}' from user {email}")
            print(f"📋 New accounts list: {row.accounts}")
            
            return True
            
    except OperationalError as e:
        print(f"❌ DB connection error in remove_account_from_user: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in remove_account_from_user: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==================== LICENSE FUNCTIONS ====================

def get_license(username: str):
    """Return license row for username from users table or None"""
    try:
        with get_db() as db:
            u = db.query(User).filter(User.username == username).first()
            if not u:
                return None
            return {
                "username": u.username,
                "player_id": getattr(u, 'player_id', None),
                "expires": u.expires,
                "paused": u.paused,
                "paused_at": u.paused_at,
                "remaining_days": u.remaining_days,
                "last_nickname": getattr(u, 'last_nickname', None),
                "first_connection_date": getattr(u, 'first_connection_date', None)
            }
    except OperationalError as e:
        print(f"⚠️ DB connection error in get_license: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in get_license: {e}")
        return None

def pause_license(username: str):
    try:
        with get_db() as db:
            u = db.query(User).filter(User.username == username).first()
            if not u:
                return False
            if getattr(u, 'paused', False):
                return False
            # compute remaining days safely
            try:
                from datetime import datetime
                expires_dt = datetime.strptime(u.expires, '%Y-%m-%d')
                remaining = (expires_dt - datetime.now()).days
            except Exception:
                remaining = None
            u.paused = True
            u.paused_at = datetime.now().strftime('%Y-%m-%d') if hasattr(__import__('datetime'), 'datetime') else None
            u.remaining_days = remaining
            return True
    except OperationalError as e:
        print(f"⚠️ DB connection error in pause_license: {e}")
        return False
    except Exception as e:
        print(f"⚠️ Unexpected error in pause_license: {e}")
        return False

def resume_license(username: str):
    try:
        with get_db() as db:
            u = db.query(User).filter(User.username == username).first()
            if not u:
                return False
            if not getattr(u, 'paused', False):
                return False
            remaining = u.remaining_days or 0
            try:
                from datetime import datetime, timedelta
                new_expiry = (datetime.now() + timedelta(days=remaining)).strftime('%Y-%m-%d')
            except Exception:
                new_expiry = u.expires
            u.expires = new_expiry
            u.paused = False
            u.paused_at = None
            u.remaining_days = None
            return True
    except OperationalError as e:
        print(f"⚠️ DB connection error in resume_license: {e}")
        return False
    except Exception as e:
        print(f"⚠️ Unexpected error in resume_license: {e}")
        return False

def get_user_xp(username: str):
    try:
        with get_db() as db:
            xp = db.query(UserXP).filter(UserXP.username == username).first()
            if not xp:
                return {"daily": {}, "weekly": {}, "monthly": {}}
            return {"daily": xp.daily or {}, "weekly": xp.weekly or {}, "monthly": xp.monthly or {}}
    except OperationalError as e:
        print(f"⚠️ DB connection error in get_user_xp: {e}")
        return {"daily": {}, "weekly": {}, "monthly": {}}
    except Exception as e:
        print(f"⚠️ Unexpected error in get_user_xp: {e}")
        return {"daily": {}, "weekly": {}, "monthly": {}}

# ==================== STATS FUNCTIONS ====================

def load_stats():
    """Load connection stats"""
    try:
        with get_db() as db:
            stats = db.query(Stats).all()
            return {s.username: s.connection_count for s in stats}
    except Exception as e:
        print(f"⚠️ Error loading stats: {e}")
        return {}

def save_stats(stats_dict):
    """Save connection stats"""
    try:
        with get_db() as db:
            for username, count in stats_dict.items():
                stat = db.query(Stats).filter_by(username=username).first()
                if stat:
                    stat.connection_count = count
                else:
                    new_stat = Stats(username=username, connection_count=count)
                    db.add(new_stat)
    except Exception as e:
        print(f"⚠️ Error saving stats: {e}")

def load_last_connected():
    """Load last connected times"""
    try:
        with get_db() as db:
            records = db.query(LastConnected).all()
            return {r.username: r.last_connected for r in records}
    except Exception as e:
        print(f"⚠️ Error loading last_connected: {e}")
        return {}

def save_last_connected(last_conn_dict):
    """Save last connected times"""
    try:
        with get_db() as db:
            for username, timestamp in last_conn_dict.items():
                record = db.query(LastConnected).filter_by(username=username).first()
                if record:
                    record.last_connected = timestamp
                else:
                    new_record = LastConnected(username=username, last_connected=timestamp)
                    db.add(new_record)
    except Exception as e:
        print(f"⚠️ Error saving last_connected: {e}")

# ==================== LOGGING FUNCTIONS ====================

def save_log(timestamp, message, level='info'):
    """Save a log entry to database"""
    try:
        with get_db() as db:
            log = Log(timestamp=timestamp, message=message, level=level)
            db.add(log)
    except Exception as e:
        print(f"⚠️ Error saving log: {e}")

def get_recent_logs(limit=500):
    """Get recent logs"""
    try:
        with get_db() as db:
            logs = db.query(Log).order_by(Log.id.desc()).limit(limit).all()
            return [
                {"ts": log.timestamp, "msg": log.message, "level": log.level}
                for log in logs
            ]
    except Exception as e:
        print(f"⚠️ Error fetching logs: {e}")
        return []

def save_recent_connection(timestamp, username, ip, status):
    """Save a recent connection to database"""
    try:
        with get_db() as db:
            conn = RecentConnection(
                timestamp=timestamp,
                username=username,
                ip=ip,
                status=status
            )
            db.add(conn)
    except Exception as e:
        print(f"⚠️ Error saving recent connection: {e}")

def get_recent_connections(limit=300):
    """Get recent connections"""
    try:
        with get_db() as db:
            conns = db.query(RecentConnection).order_by(RecentConnection.id.desc()).limit(limit).all()
            return [
                {
                    "ts": c.timestamp,
                    "username": c.username,
                    "ip": c.ip,
                    "status": c.status
                }
                for c in conns
            ]
    except Exception as e:
        print(f"⚠️ Error fetching recent connections: {e}")
        return []

# ==================== PLAYER ID & NICKNAME TRACKING ====================

def get_user_by_player_id(player_id: str):
    """Get user by player_id"""
    try:
        with get_db() as db:
            user = db.query(User).filter(User.player_id == player_id).first()
            if not user:
                return None
            return {
                "username": user.username,
                "player_id": user.player_id,
                "expires": user.expires,
                "paused": user.paused,
                "paused_at": user.paused_at,
                "remaining_days": user.remaining_days,
                "last_nickname": user.last_nickname,
                "first_connection_date": user.first_connection_date
            }
    except OperationalError as e:
        print(f"⚠️ DB connection error in get_user_by_player_id: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in get_user_by_player_id: {e}")
        return None

def update_user_player_id(username: str, player_id: str):
    """Update user's player_id on first connection"""
    try:
        with get_db() as db:
            from datetime import datetime
            user = db.query(User).filter(User.username == username).first()
            if not user:
                return False
            user.player_id = player_id
            if not user.first_connection_date:
                user.first_connection_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            return True
    except OperationalError as e:
        print(f"⚠️ DB connection error in update_user_player_id: {e}")
        return False
    except Exception as e:
        print(f"⚠️ Unexpected error in update_user_player_id: {e}")
        return False

def update_user_nickname(player_id: str, new_nickname: str, old_nickname: str):
    """Update user's nickname when it changes"""
    try:
        with get_db() as db:
            user = db.query(User).filter(User.player_id == player_id).first()
            if not user:
                return False
            user.last_nickname = old_nickname
            user.username = new_nickname
            return True
    except OperationalError as e:
        print(f"⚠️ DB connection error in update_user_nickname: {e}")
        return False
    except Exception as e:
        print(f"⚠️ Unexpected error in update_user_nickname: {e}")
        return False

# ==================== CUSTOM MESSAGE FUNCTIONS ====================

def get_custom_message():
    """Get the global custom message"""
    try:
        with get_db() as db:
            from init_database import CustomMessage
            msg = db.query(CustomMessage).first()
            if not msg:
                return ""
            return msg.message or ""
    except Exception as e:
        print(f"⚠️ Error in get_custom_message: {e}")
        return ""

def set_custom_message(message: str):
    """Set the global custom message"""
    try:
        with get_db() as db:
            from init_database import CustomMessage
            msg = db.query(CustomMessage).first()
            if msg:
                msg.message = message
            else:
                new_msg = CustomMessage(message=message)
                db.add(new_msg)
            return True
    except Exception as e:
        print(f"⚠️ Error in set_custom_message: {e}")
        return False

# ==================== GEM ACCOUNT FUNCTIONS ====================

def get_all_gem_accounts():
    """Get all gem accounts"""
    try:
        with get_db() as db:
            from init_database import GemAccount
            accounts = db.query(GemAccount).order_by(GemAccount.account_number).all()
            return [
                {
                    'id': acc.id,
                    'account_number': acc.account_number,
                    'email': acc.email,
                    'password': acc.password,
                    'current_nickname': acc.current_nickname,
                    'gems_remaining': acc.gems_remaining,
                    'is_active': acc.is_active,
                    'last_used': acc.last_used
                }
                for acc in accounts
            ]
    except Exception as e:
        print(f"⚠️ Error getting gem accounts: {e}")
        return []

def add_gem_account(account_number, email, password):
    """Add a new gem account"""
    try:
        with get_db() as db:
            from init_database import GemAccount
            
            existing = db.query(GemAccount).filter_by(email=email).first()
            if existing:
                return False
            
            new_account = GemAccount(
                account_number=account_number,
                email=email,
                password=password,
                current_nickname=f"bugsbot{account_number}",
                gems_remaining=5000,
                is_active=True
            )
            
            db.add(new_account)
            return True
    except Exception as e:
        print(f"⚠️ Error adding gem account: {e}")
        return False

def update_gem_account_nickname(account_id, new_nickname):
    """Update account's current nickname"""
    try:
        with get_db() as db:
            from init_database import GemAccount
            
            account = db.query(GemAccount).filter_by(id=account_id).first()
            if not account:
                return False
            
            account.current_nickname = new_nickname
            return True
    except Exception as e:
        print(f"⚠️ Error updating nickname: {e}")
        return False

def deduct_account_gems(account_id, gems_spent):
    """Deduct gems from account"""
    try:
        with get_db() as db:
            from init_database import GemAccount
            from datetime import datetime

            account = db.query(GemAccount).filter_by(id=account_id).first()
            if not account:
                return False

            if account.gems_remaining < gems_spent:
                return False

            account.gems_remaining -= gems_spent
            account.last_used = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            return True
    except Exception as e:
        print(f"⚠️ Error deducting gems: {e}")
        return False


def recharge_account_gems(account_id, gems_amount=5000):
    """Recharge account gems"""
    try:
        with get_db() as db:
            from init_database import GemAccount
            
            account = db.query(GemAccount).filter_by(id=account_id).first()
            if not account:
                return False
            
            account.gems_remaining = gems_amount
            return True
    except Exception as e:
        print(f"⚠️ Error recharging gems: {e}")
        return False

# ==================== STATS SUMMARY ====================

def get_stats_summary():
    """Get summary of all stats for dashboard"""
    try:
        with get_db() as db:
            from sqlalchemy import func
            
            total_users = db.query(func.count(User.username)).scalar()
            total_keys = db.query(func.count(Key.code)).scalar()
            used_keys = db.query(func.count(Key.code)).filter(Key.used == True).scalar()
            total_testimonials = db.query(func.count(Testimonial.id)).scalar()
            approved_testimonials = db.query(func.count(Testimonial.id)).filter(Testimonial.approved == True).scalar()
            
            return {
                "total_users": total_users,
                "total_keys": total_keys,
                "used_keys": used_keys,
                "total_testimonials": total_testimonials,
                "approved_testimonials": approved_testimonials
            }
    except Exception as e:
        print(f"⚠️ Error getting stats summary: {e}")
        return {
            "total_users": 0,
            "total_keys": 0,
            "used_keys": 0,
            "total_testimonials": 0,
            "approved_testimonials": 0
        }

# ==================== POOL MONITORING ====================

def get_pool_stats():
    """Get connection pool statistics for monitoring"""
    try:
        return {
            "pool_size": engine.pool.size(),
            "checked_out": engine.pool.checkedout(),
            "overflow": engine.pool.overflow(),
            "checked_in": engine.pool.checkedin()
        }
    except Exception as e:
        print(f"⚠️ Error getting pool stats: {e}")
        return {
            "pool_size": 0,
            "checked_out": 0,
            "overflow": 0,
            "checked_in": 0
        }

# ==================== BOT VERSION FUNCTIONS ====================

def get_latest_bot_version():
    """Get the latest bot version from settings"""
    try:
        with get_db() as db:
            from init_database import BotSettings
            settings = db.query(BotSettings).first()
            if not settings:
                return "0.6.9"  # Default version
            return settings.latest_bot_version
    except Exception as e:
        print(f"⚠️ Error getting latest bot version: {e}")
        return "0.6.9"

def set_latest_bot_version(version: str):
    """Set the latest bot version"""
    try:
        with get_db() as db:
            from init_database import BotSettings
            from datetime import datetime
            
            settings = db.query(BotSettings).first()
            if settings:
                settings.latest_bot_version = version
                settings.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            else:
                new_settings = BotSettings(
                    id=1,
                    latest_bot_version=version
                )
                db.add(new_settings)
            return True
    except Exception as e:
        print(f"⚠️ Error setting latest bot version: {e}")
        return False

def update_user_bot_version(username: str, bot_version: str):
    """Update user's last connected bot version"""
    try:
        with get_db() as db:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                return False
            user.last_bot_version = bot_version
            return True
    except Exception as e:
        print(f"⚠️ Error updating user bot version: {e}")
        return False

# ==================== EXPORTS ====================

__all__ = [
    'load_users',
    'save_users',
    'find_user',
    'load_keys',
    'save_keys',
    'find_key',
    'load_testimonials',
    'save_testimonials',
    'read_storage_impl',
    'read_storage',
    'write_storage_impl',
    'write_storage',
    'get_user_by_email',
    'create_user',
    'verify_user_password',
    'get_user_accounts',
    'add_account_to_user',
    'remove_account_from_user',
    'get_license',
    'pause_license',
    'resume_license',
    'get_user_xp',
    'load_stats',
    'save_stats',
    'load_last_connected',
    'save_last_connected',
    'save_log',
    'get_recent_logs',
    'save_recent_connection',
    'get_recent_connections',
    'get_stats_summary',
    'get_user_by_player_id',
    'update_user_player_id',
    'update_user_nickname',
    'get_custom_message',
    'set_custom_message',
    'get_all_gem_accounts',
    'add_gem_account',
    'update_gem_account_nickname',
    'deduct_account_gems',
    'recharge_account_gems',
    'get_pool_stats',
    'get_latest_bot_version',  # ✅ NOUVEAU
    'set_latest_bot_version',  # ✅ NOUVEAU
    'update_user_bot_version'  # ✅ NOUVEAU
]