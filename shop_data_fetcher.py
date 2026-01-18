"""
Shop Data Fetcher - Syncs Wolvesville shop data daily at 1:10 AM CET
Uses the existing token manager to avoid 2captcha costs
"""

import requests
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import db_helper
from token_manager import token_manager

class ShopDataFetcher:
    def __init__(self):
        self.base_url = "https://core.api-wolvesville.com"
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone('CET'))
        
    def get_headers(self):
        """Get headers with fresh token from token_manager"""
        tokens = token_manager.get_valid_tokens()
        if not tokens or not tokens.get('bearer'):
            raise Exception("No valid token available")
            
        return {
            "accept": "application/json",
            "authorization": f"Bearer {tokens['bearer']}",
            "cf-jwt": tokens['cfJwt'],
            "content-type": "application/json",
            "origin": "https://www.wolvesville.com",
            "referer": "https://www.wolvesville.com/"
        }
    
    def fetch_bundles(self):
        """Fetch BUNDLE_* items from gemOffers"""
        try:
            headers = self.get_headers()
            response = requests.get(
                f"{self.base_url}/purchasableItems/gemOffers",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            all_items = response.json()
            
            # Filter BUNDLE_* items only
            bundles = []
            for item in all_items:
                item_type = item.get('type', '')
                if item_type.startswith('BUNDLE_'):
                    cost = item.get('costInGems')
                    
                    # Price mapping
                    if cost == 450:
                        price = 2.99
                    elif cost == 790:
                        price = 4.99
                    else:
                        continue  # Skip items without valid price
                    
                    bundles.append({
                        'type': item_type,
                        'cost': cost,
                        'price': price,
                        'name': self._format_bundle_name(item_type),
                        'image': self._get_bundle_image(item_type)
                    })
            
            print(f"✅ Fetched {len(bundles)} bundles")
            return bundles
            
        except Exception as e:
            print(f"❌ Error fetching bundles: {e}")
            return []
    
    def fetch_rotating_offers(self):
        """Fetch skin sets and daily skins"""
        try:
            headers = self.get_headers()
            response = requests.get(
                f"{self.base_url}/billing/rotatingLimitedOffers/v2",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            offers = data.get('offers', [])
            
            skin_sets = []
            daily_skins = []
            
            for offer in offers:
                offer_type = offer.get('type', '')
                
                # Skin sets: *_OUTFITS (380 gems = €2.49)
                if offer_type.endswith('_OUTFITS'):
                    skin_sets.append({
                        'type': offer_type,
                        'cost': 380,
                        'price': 2.49,  # ✅ €2.49 for skin sets
                        'name': self._format_outfit_name(offer_type),
                        'expireDate': offer.get('expireDate'),
                        'itemSets': offer.get('itemSets', [])
                    })
                
                # Daily skins: AVATAR_ITEMS_SET (380 gems = €2.49)
                elif offer_type == 'AVATAR_ITEMS_SET':
                    item_sets = offer.get('itemSets', [])
                    for item_set in item_sets:
                        daily_skins.append({
                            'type': offer_type,
                            'cost': 380,
                            'price': 2.49,  # ✅ €2.49 for daily skins
                            'name': item_set.get('imageName', 'Daily Skin'),
                            'imageName': item_set.get('imageName'),
                            'imageColor': item_set.get('imagePrimaryColor'),
                            'expireDate': offer.get('expireDate'),
                            'avatarItemIds': item_set.get('avatarItemIds', [])
                        })
            
            print(f"✅ Fetched {len(skin_sets)} skin sets, {len(daily_skins)} daily skins")
            return skin_sets, daily_skins
            
        except Exception as e:
            print(f"❌ Error fetching rotating offers: {e}")
            return [], []
    
    def fetch_calendars(self):
        """Fetch all available calendars"""
        try:
            headers = self.get_headers()
            response = requests.get(
                f"{self.base_url}/calendars/purchasable",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            all_calendars = data.get('calendars', [])
            
            calendars = []
            for cal in all_calendars:
                calendars.append({
                    'id': cal.get('calendarId'),
                    'title': cal.get('title'),
                    'cost': 600,  # CALENDAR_LEGACY cost from gemOffers
                    'price': 3.99,
                    'description': cal.get('description'),
                    'imageName': cal.get('imageBaseName'),
                    'iconName': cal.get('iconImageName'),
                    'durationInDays': cal.get('durationInDays'),
                    'owned': cal.get('owned', False)
                })
            
            print(f"✅ Fetched {len(calendars)} calendars")
            return calendars
            
        except Exception as e:
            print(f"❌ Error fetching calendars: {e}")
            return []
    
    def detect_new_items(self, current_bundles):
        """Compare with previous day and mark new items - OPTIMIZED"""
        try:
            # Load previous bundles using the new optimized function
            previous_bundles = db_helper.get_shop_bundles_only()
            previous_types = {b['type'] for b in previous_bundles}
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Mark new items
            for bundle in current_bundles:
                if bundle['type'] not in previous_types:
                    bundle['isNew'] = True
                    bundle['newSince'] = today
                    print(f"🆕 New bundle detected: {bundle['name']}")
                else:
                    # Check if it was marked as new
                    for prev in previous_bundles:
                        if prev['type'] == bundle['type'] and prev.get('isNew'):
                            # Calculate days since marked new
                            new_since = datetime.strptime(prev['newSince'], '%Y-%m-%d')
                            days_new = (datetime.now() - new_since).days
                            
                            if days_new < 7:
                                bundle['isNew'] = True
                                bundle['newSince'] = prev['newSince']
                            else:
                                bundle['isNew'] = False
                        elif prev['type'] == bundle['type']:
                            bundle['isNew'] = False
            
            return current_bundles
            
        except Exception as e:
            print(f"⚠️ Error detecting new items: {e}")
            # Mark all as not new on error
            for bundle in current_bundles:
                bundle['isNew'] = False
            return current_bundles
    
    def sync_shop_data(self):
        """Main sync function - OPTIMIZED to use single transaction"""
        print("\n" + "="*60)
        print(f"🔄 Starting shop data sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        try:
            # Fetch all data from API
            print("📡 Fetching data from Wolvesville API...")
            bundles = self.fetch_bundles()
            skin_sets, daily_skins = self.fetch_rotating_offers()
            calendars = self.fetch_calendars()
            
            # Detect new bundles
            print("🔍 Detecting new items...")
            bundles = self.detect_new_items(bundles)
            
            # ✅ SINGLE DATABASE SAVE - All in one transaction!
            print("💾 Saving to database (single transaction)...")
            success = db_helper.save_all_shop_data(
                bundles=bundles,
                skin_sets=skin_sets,
                daily_skins=daily_skins,
                calendars=calendars
            )
            
            if success:
                print("="*60)
                print("✅ Shop data sync completed successfully!")
                print(f"   - Bundles: {len(bundles)} ({len([b for b in bundles if b.get('isNew')])} new)")
                print(f"   - Skin sets: {len(skin_sets)}")
                print(f"   - Daily skins: {len(daily_skins)}")
                print(f"   - Calendars: {len(calendars)}")
                print("="*60 + "\n")
            else:
                print("❌ Failed to save shop data to database")
                
        except Exception as e:
            print(f"❌ Shop sync failed: {e}")
            import traceback
            traceback.print_exc()
    
    def start_scheduler(self):
        """Start the daily sync scheduler"""
        # Schedule for 1:10 AM CET daily
        self.scheduler.add_job(
            self.sync_shop_data,
            CronTrigger(hour=1, minute=10, timezone='CET'),
            id='shop_sync',
            name='Daily Shop Data Sync',
            replace_existing=True
        )
        
        self.scheduler.start()
        print("📅 Shop sync scheduler started (Daily at 1:10 AM CET)")
        
        # Run once on startup
        print("🚀 Running initial shop sync...")
        self.sync_shop_data()
    
    def _format_bundle_name(self, bundle_type):
        """Convert BUNDLE_XXX to readable name"""
        name = bundle_type.replace('BUNDLE_', '').replace('_', ' ').title()
        return f"{name} Bundle"
    
    def _format_outfit_name(self, outfit_type):
        """Convert XXX_OUTFITS to readable name"""
        name = outfit_type.replace('_OUTFITS', '').replace('_', ' ').title()
        return f"{name} Outfits"
    
    def _get_bundle_image(self, bundle_type):
        """Get CDN image path for bundle"""
        image_name = bundle_type.replace('BUNDLE_', '').lower()
        return f"bundle-{image_name}"


# Global instance
shop_data_fetcher = ShopDataFetcher()