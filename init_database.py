import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, JSON, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Load .env file FIRST
load_dotenv()

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    username = Column(String(255), primary_key=True)
    player_id = Column(String(255), nullable=True, index=True)
    expires = Column(String(10), nullable=False)  # YYYY-MM-DD format
    paused = Column(Boolean, default=False)
    paused_at = Column(String(10), nullable=True)
    remaining_days = Column(Integer, nullable=True)
    last_nickname = Column(String(255), nullable=True)
    first_connection_date = Column(String(30), nullable=True)
    last_bot_version = Column(String(20), nullable=True)
class Key(Base):
    __tablename__ = 'keys'
    
    code = Column(String(6), primary_key=True)
    duration = Column(Integer, nullable=False)
    created = Column(String(30), nullable=False)
    used = Column(Boolean, default=False)
    used_by = Column(String(255), nullable=True)
    used_at = Column(String(30), nullable=True)

class Testimonial(Base):
    __tablename__ = 'testimonials'
    
    id = Column(String(8), primary_key=True)
    username = Column(String(255), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=False)
    anonymous = Column(Boolean, default=False)
    date = Column(String(10), nullable=False)
    approved = Column(Boolean, default=False)

class UserCredential(Base):
    __tablename__ = 'user_credentials'
    
    email = Column(String(255), primary_key=True)
    password = Column(String(255), nullable=False)
    accounts = Column(JSON, default=list)

class UserXP(Base):
    __tablename__ = 'user_xp'
    
    username = Column(String(255), primary_key=True)
    daily = Column(JSON, default=dict)
    weekly = Column(JSON, default=dict)
    monthly = Column(JSON, default=dict)

class Stats(Base):
    __tablename__ = 'stats'
    
    username = Column(String(255), primary_key=True)
    connection_count = Column(Integer, default=0)

class LastConnected(Base):
    __tablename__ = 'last_connected'
    
    username = Column(String(255), primary_key=True)
    last_connected = Column(String(30), nullable=False)

class Log(Base):
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(30), nullable=False)
    message = Column(Text, nullable=False)
    level = Column(String(10), default='info')

class RecentConnection(Base):
    __tablename__ = 'recent_connections'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(30), nullable=False)
    username = Column(String(255), nullable=False)
    ip = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)

class CustomMessage(Base):
    __tablename__ = 'custom_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message = Column(Text, nullable=True)

class GemAccount(Base):
    __tablename__ = 'gem_accounts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_number = Column(Integer, unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    current_nickname = Column(String(255), nullable=False)  # Current username (RXZBOT or bugsbot{N})
    gems_remaining = Column(Integer, default=5000)
    is_active = Column(Boolean, default=True)
    last_used = Column(String(30), nullable=True)  # Last time this account was used
    created_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

class BotSettings(Base):
    __tablename__ = 'bot_settings'
    
    id = Column(Integer, primary_key=True, default=1)
    latest_bot_version = Column(String(20), nullable=False, default='0.6.9')
    updated_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

class ShopBundle(Base):
    __tablename__ = 'shop_bundles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(100), unique=True, nullable=False, index=True)
    cost = Column(Integer, nullable=False)
    price = Column(String(10), nullable=False)  # Store as string to preserve decimal
    name = Column(String(255), nullable=False)
    image = Column(String(255))
    is_new = Column(Boolean, default=False)
    new_since = Column(String(10))  # YYYY-MM-DD format
    created_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

class ShopSkinSet(Base):
    __tablename__ = 'shop_skin_sets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(100), nullable=False)
    cost = Column(Integer, nullable=False)
    price = Column(String(10), nullable=False)
    name = Column(String(255), nullable=False)
    expire_date = Column(String(50))
    item_sets = Column(JSON)
    created_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

class ShopDailySkin(Base):
    __tablename__ = 'shop_daily_skins'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(100), nullable=False)
    cost = Column(Integer, nullable=False)
    price = Column(String(10), nullable=False)
    name = Column(String(255), nullable=False)
    image_name = Column(String(255))
    image_color = Column(String(50))
    expire_date = Column(String(50))
    avatar_item_ids = Column(JSON)
    created_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

class ShopCalendar(Base):
    __tablename__ = 'shop_calendars'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    calendar_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    cost = Column(Integer, nullable=False)
    price = Column(String(10), nullable=False)
    description = Column(Text)
    image_name = Column(String(255))
    icon_name = Column(String(255))
    duration_in_days = Column(Integer)
    owned = Column(Boolean, default=False)
    created_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

class ShopMetadata(Base):
    __tablename__ = 'shop_metadata'
    
    id = Column(Integer, primary_key=True, default=1)
    last_updated = Column(String(30), nullable=False)
    
def init_database():
    """Initialize database with all tables"""
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment")
        return False
    
    print("🔗 Connecting to Supabase database...")
    print(f"   URL: {DATABASE_URL[:30]}...")
    
    try:
        engine = create_engine(DATABASE_URL)
        
        print("📋 Creating tables...")
        Base.metadata.create_all(engine)
        
        print("✅ Database initialized successfully!")
        print(f"   Tables created:")
        for table in Base.metadata.sorted_tables:
            print(f"   - {table.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    init_database()