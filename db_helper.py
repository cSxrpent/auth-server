import os
from contextlib import contextmanager
from time import time
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, scoped_session

from init_database import (
    User,
    Key,
    Testimonial,
    UserCredential,
    UserXP,
    Stats,
    LastConnected,
    Log,
    RecentConnection,
)

# =========================================================
# DATABASE ENGINE (OPTIMIZED FOR SUPABASE + RENDER FREE)
# =========================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # Supabase-safe
)

SessionLocal = scoped_session(
    sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# =========================================================
# SIMPLE IN-MEMORY CACHE (FAST DASHBOARD)
# =========================================================

_CACHE = {}
_CACHE_TTL = 10  # seconds

def _cached(key, loader):
    now = time()
    if key in _CACHE:
        ts, value = _CACHE[key]
        if now - ts < _CACHE_TTL:
            return value
    value = loader()
    _CACHE[key] = (now, value)
    return value

# =========================================================
# USERS
# =========================================================

def load_users():
    with get_db() as db:
        rows = db.query(
            User.username,
            User.expires,
            User.paused,
            User.paused_at,
            User.remaining_days,
        ).all()

        return [
            {
                "username": r.username,
                "expires": r.expires,
                "paused": r.paused,
                "paused_at": r.paused_at,
                "remaining_days": r.remaining_days,
            }
            for r in rows
        ]

def load_users_cached():
    return _cached("users", load_users)

def save_users(users):
    with get_db() as db:
        for u in users:
            db.merge(User(**u))

# =========================================================
# KEYS
# =========================================================

def load_keys():
    with get_db() as db:
        rows = db.query(Key).all()
        return [
            {
                "code": k.code,
                "duration": k.duration,
                "created": k.created,
                "used": k.used,
                "used_by": k.used_by,
                "used_at": k.used_at,
            }
            for k in rows
        ]

def save_keys(keys):
    with get_db() as db:
        for k in keys:
            db.merge(Key(**k))

# =========================================================
# TESTIMONIALS
# =========================================================

def load_testimonials():
    with get_db() as db:
        rows = db.query(Testimonial).all()
        return [
            {
                "id": t.id,
                "username": t.username,
                "rating": t.rating,
                "comment": t.comment,
                "anonymous": t.anonymous,
                "date": t.date,
                "approved": t.approved,
            }
            for t in rows
        ]

def save_testimonials(tests):
    with get_db() as db:
        for t in tests:
            db.merge(Testimonial(**t))

# =========================================================
# USER CREDENTIALS
# =========================================================

def load_credentials():
    with get_db() as db:
        rows = db.query(UserCredential).all()
        return {
            r.email: {
                "password": r.password,
                "accounts": r.accounts or [],
            }
            for r in rows
        }

def save_credentials(data):
    with get_db() as db:
        for email, info in data.items():
            db.merge(
                UserCredential(
                    email=email,
                    password=info["password"],
                    accounts=info.get("accounts", []),
                )
            )

# =========================================================
# USER XP
# =========================================================

def load_xp():
    with get_db() as db:
        rows = db.query(UserXP).all()
        return {
            r.username: {
                "daily": r.daily or {},
                "weekly": r.weekly or {},
                "monthly": r.monthly or {},
            }
            for r in rows
        }

def save_xp(data):
    with get_db() as db:
        for username, xp in data.items():
            db.merge(
                UserXP(
                    username=username,
                    daily=xp.get("daily", {}),
                    weekly=xp.get("weekly", {}),
                    monthly=xp.get("monthly", {}),
                )
            )

# =========================================================
# STATS
# =========================================================

def load_stats():
    with get_db() as db:
        return {
            r.username: r.connection_count
            for r in db.query(Stats).all()
        }

def save_stats(stats):
    with get_db() as db:
        for user, count in stats.items():
            db.merge(Stats(username=user, connection_count=count))

# =========================================================
# CONNECTION TRACKING
# =========================================================

def save_last_connected(username, ts):
    with get_db() as db:
        db.merge(LastConnected(username=username, last_connected=ts))

def load_last_connected():
    with get_db() as db:
        return {
            r.username: r.last_connected
            for r in db.query(LastConnected).all()
        }

# =========================================================
# LOGGING
# =========================================================

def save_log(timestamp, message, level="info"):
    with get_db() as db:
        db.add(Log(timestamp=timestamp, message=message, level=level))

def get_recent_logs(limit=200):
    with get_db() as db:
        rows = (
            db.query(Log)
            .order_by(Log.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {"ts": r.timestamp, "msg": r.message, "level": r.level}
            for r in rows
        ]

# =========================================================
# RECENT CONNECTIONS
# =========================================================

def save_recent_connection(timestamp, username, ip, status):
    with get_db() as db:
        db.add(
            RecentConnection(
                timestamp=timestamp,
                username=username,
                ip=ip,
                status=status,
            )
        )

def get_recent_connections(limit=200):
    with get_db() as db:
        rows = (
            db.query(RecentConnection)
            .order_by(RecentConnection.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "ts": r.timestamp,
                "username": r.username,
                "ip": r.ip,
                "status": r.status,
            }
            for r in rows
        ]

# =========================================================
# DASHBOARD SUMMARY (FAST)
# =========================================================

def get_stats_summary():
    with get_db() as db:
        return {
            "total_users": db.query(func.count(User.username)).scalar(),
            "total_keys": db.query(func.count(Key.code)).scalar(),
            "used_keys": db.query(func.count(Key.code)).filter(Key.used.is_(True)).scalar(),
            "total_testimonials": db.query(func.count(Testimonial.id)).scalar(),
            "approved_testimonials": db.query(func.count(Testimonial.id)).filter(
                Testimonial.approved.is_(True)
            ).scalar(),
        }
