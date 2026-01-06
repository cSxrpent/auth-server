import os
import json
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv
from init_database import init_database, User, Key, Testimonial, UserCredential, UserXP
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# GitHub configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = "cSxrpent"
GITHUB_REPO = "auth-users"
GITHUB_BRANCH = "main"

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

def fetch_github_file(filename):
    """Fetch a file from GitHub"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{filename}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    params = {"ref": GITHUB_BRANCH}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            content_b64 = data.get("content", "")
            decoded = base64.b64decode(content_b64.encode()).decode("utf-8")
            return json.loads(decoded)
        elif response.status_code == 404:
            print(f"   ⚠️  {filename} not found on GitHub (this is OK if it's a new file)")
            return None
        else:
            print(f"   ❌ Failed to fetch {filename}: {response.status_code}")
            return None
    except Exception as e:
        print(f"   ❌ Error fetching {filename}: {e}")
        return None

def migrate_data():
    """Migrate all data from GitHub JSON files to Supabase"""
    
    print("=" * 60)
    print("🚀 GITHUB TO SUPABASE MIGRATION")
    print("=" * 60)
    
    # Step 1: Initialize database
    print("\n📋 Step 1: Initializing database tables...")
    if not init_database():
        print("❌ Failed to initialize database")
        return False
    
    # Step 2: Connect to database
    print("\n🔗 Step 2: Connecting to database...")
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        print("   ✅ Connected successfully")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False
    
    # Step 3: Migrate users.json
    print("\n👥 Step 3: Migrating users.json...")
    users_data = fetch_github_file("users.json")
    if users_data:
        count = 0
        for user_data in users_data:
            try:
                user = User(
                    username=user_data['username'],
                    expires=user_data['expires'],
                    paused=user_data.get('paused', False),
                    paused_at=user_data.get('paused_at'),
                    remaining_days=user_data.get('remaining_days')
                )
                session.merge(user)  # merge instead of add to handle duplicates
                count += 1
            except Exception as e:
                print(f"   ⚠️  Error migrating user {user_data.get('username')}: {e}")
        
        session.commit()
        print(f"   ✅ Migrated {count} users")
    else:
        print("   ⚠️  No users data found")
    
    # Step 4: Migrate keys.json
    print("\n🔑 Step 4: Migrating keys.json...")
    keys_data = fetch_github_file("keys.json")
    if keys_data:
        count = 0
        for key_data in keys_data:
            try:
                key = Key(
                    code=key_data['code'],
                    duration=key_data['duration'],
                    created=key_data['created'],
                    used=key_data.get('used', False),
                    used_by=key_data.get('used_by'),
                    used_at=key_data.get('used_at')
                )
                session.merge(key)
                count += 1
            except Exception as e:
                print(f"   ⚠️  Error migrating key {key_data.get('code')}: {e}")
        
        session.commit()
        print(f"   ✅ Migrated {count} keys")
    else:
        print("   ⚠️  No keys data found")
    
    # Step 5: Migrate testimonials.json
    print("\n💬 Step 5: Migrating testimonials.json...")
    testimonials_data = fetch_github_file("testimonials.json")
    if testimonials_data:
        count = 0
        for test_data in testimonials_data:
            try:
                testimonial = Testimonial(
                    id=test_data['id'],
                    username=test_data['username'],
                    rating=test_data['rating'],
                    comment=test_data['comment'],
                    anonymous=test_data.get('anonymous', False),
                    date=test_data['date'],
                    approved=test_data.get('approved', False)
                )
                session.merge(testimonial)
                count += 1
            except Exception as e:
                print(f"   ⚠️  Error migrating testimonial {test_data.get('id')}: {e}")
        
        session.commit()
        print(f"   ✅ Migrated {count} testimonials")
    else:
        print("   ⚠️  No testimonials data found")
    
    # Step 6: Migrate user-credentials.json
    print("\n🔐 Step 6: Migrating user-credentials.json...")
    credentials_data = fetch_github_file("user-credentials.json")
    if credentials_data:
        count = 0
        for email, cred_data in credentials_data.items():
            try:
                credential = UserCredential(
                    email=email,
                    password=cred_data['password'],
                    accounts=cred_data.get('accounts', [])
                )
                session.merge(credential)
                count += 1
            except Exception as e:
                print(f"   ⚠️  Error migrating credential {email}: {e}")
        
        session.commit()
        print(f"   ✅ Migrated {count} user credentials")
    else:
        print("   ⚠️  No user credentials data found")
    
    # Step 7: Migrate user-XP.json
    print("\n📊 Step 7: Migrating user-XP.json...")
    xp_data = fetch_github_file("user-XP.json")
    if xp_data:
        count = 0
        for username, xp_info in xp_data.items():
            try:
                user_xp = UserXP(
                    username=username,
                    daily=xp_info.get('daily', {}),
                    weekly=xp_info.get('weekly', {}),
                    monthly=xp_info.get('monthly', {})
                )
                session.merge(user_xp)
                count += 1
            except Exception as e:
                print(f"   ⚠️  Error migrating XP for {username}: {e}")
        
        session.commit()
        print(f"   ✅ Migrated {count} XP records")
    else:
        print("   ⚠️  No XP data found")
    
    # Close session
    session.close()
    
    print("\n" + "=" * 60)
    print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("\n📝 Next steps:")
    print("   1. Verify data in Supabase dashboard")
    print("   2. Update app.py to use db_helper functions")
    print("   3. Deploy to Render")
    print("   4. Test all functionality")
    print("\n⚠️  IMPORTANT: Keep GitHub files as backup until you verify")
    print("   everything works correctly with Supabase!")
    print("=" * 60)
    
    return True

def verify_migration():
    """Verify the migration by showing counts"""
    print("\n" + "=" * 60)
    print("🔍 VERIFICATION")
    print("=" * 60)
    
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        from sqlalchemy import func
        
        tables = [
            ("Users", User),
            ("Keys", Key),
            ("Testimonials", Testimonial),
            ("User Credentials", UserCredential),
            ("User XP", UserXP)
        ]
        
        print("\n📊 Records in database:")
        for name, model in tables:
            count = session.query(func.count(model)).scalar()
            print(f"   {name}: {count} records")
        
        session.close()
        print("\n✅ Verification complete")
        
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")

if __name__ == "__main__":
    success = migrate_data()
    if success:
        verify_migration()
