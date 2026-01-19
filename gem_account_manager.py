# gem_account_manager.py
import os
import json
import requests
import time
from datetime import datetime
from wolvesville_api import wolvesville_api
from token_manager import token_manager
import db_helper

class GemAccountManager:
    """Manages multiple Wolvesville accounts for gift sending with automatic switching"""
    
    def __init__(self):
        self.current_account_index = 0
        self.INITIAL_GEMS = 5000
        self.RXZBOT_NAME = "micheal163512"
    
    def get_all_gem_accounts(self):
        """Get all gem accounts from database"""
        try:
            with db_helper.get_db() as db:
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
            print(f"❌ Error getting gem accounts: {e}")
            return []
    
    def add_gem_account(self, account_number, email, password):
        """Add a new gem account to the database"""
        try:
            with db_helper.get_db() as db:
                from init_database import GemAccount
                
                # Check if account already exists
                existing = db.query(GemAccount).filter_by(email=email).first()
                if existing:
                    print(f"⚠️ Account {email} already exists")
                    return False
                
                new_account = GemAccount(
                    account_number=account_number,
                    email=email,
                    password=password,
                    current_nickname=f"bugsbot{account_number}",
                    gems_remaining=self.INITIAL_GEMS,
                    is_active=True,
                    last_used=None
                )
                
                db.add(new_account)
                db.commit()
                
                print(f"✅ Added gem account #{account_number}: {email}")
                return True
                
        except Exception as e:
            print(f"❌ Error adding gem account: {e}")
            return False
    
    def get_active_account_with_gems(self, required_gems):
        """Find an active account with enough gems"""
        accounts = self.get_all_gem_accounts()
        
        # Filter active accounts with enough gems
        viable_accounts = [
            acc for acc in accounts 
            if acc['is_active'] and acc['gems_remaining'] >= required_gems
        ]
        
        if not viable_accounts:
            raise Exception(f"❌ No accounts with {required_gems} gems available!")
        
        # Sort by last used (least recently used first)
        viable_accounts.sort(key=lambda x: x['last_used'] or '1970-01-01')
        
        return viable_accounts[0]
    
    def deduct_gems(self, account_id, gems_spent):
        """Deduct gems from an account"""
        try:
            with db_helper.get_db() as db:
                from init_database import GemAccount
                
                account = db.query(GemAccount).filter_by(id=account_id).first()
                if not account:
                    return False
                
                account.gems_remaining -= gems_spent
                account.last_used = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                
                db.commit()
                
                print(f"💎 Account #{account.account_number} now has {account.gems_remaining} gems")
                return True
                
        except Exception as e:
            print(f"❌ Error deducting gems: {e}")
            return False
    
    def recharge_account(self, account_id, gems_amount=None):
        """Recharge an account's gems"""
        try:
            with db_helper.get_db() as db:
                from init_database import GemAccount
                
                account = db.query(GemAccount).filter_by(id=account_id).first()
                if not account:
                    return False
                
                if gems_amount is None:
                    gems_amount = self.INITIAL_GEMS
                
                account.gems_remaining = gems_amount
                
                db.commit()
                
                print(f"♻️ Recharged account #{account.account_number} to {gems_amount} gems")
                return True
                
        except Exception as e:
            print(f"❌ Error recharging account: {e}")
            return False
    
    def change_account_nickname(self, email, password, new_nickname):
        """Change account nickname using Wolvesville API"""
        try:
            print(f"🔄 Changing nickname to: {new_nickname}")

            # Get tokens for this specific account
            tokens = token_manager.get_tokens_for_account(email, password)

            url = "https://core.api-wolvesville.com/players/self"
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {tokens['bearer']}",
                'Cf-JWT': tokens['cfJwt'],
                'ids': '1',
                'Origin': 'https://www.wolvesville.com',
                'Referer': 'https://www.wolvesville.com/',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            payload = {'username': new_nickname}

            response = requests.put(url, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                print(f"✅ Nickname changed to: {new_nickname}")
                return True
            else:
                print(f"❌ Failed to change nickname: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ Error changing nickname: {e}")
            return False
    
    def switch_to_account(self, account_id):
        """Switch to a specific account and change its nickname to RXZBOT"""
        try:
            with db_helper.get_db() as db:
                from init_database import GemAccount
                
                # Get the account
                account = db.query(GemAccount).filter_by(id=account_id).first()
                if not account:
                    return False
                
                # Change nickname to RXZBOT
                if self.change_account_nickname(account.email, account.password, self.RXZBOT_NAME):
                    # Update in database
                    account.current_nickname = self.RXZBOT_NAME
                    db.commit()
                    
                    print(f"✅ Switched to account #{account.account_number} (now RXZBOT)")
                    return True
                
                return False
                
        except Exception as e:
            print(f"❌ Error switching account: {e}")
            return False
    
    def restore_account_nickname(self, account_id):
        """Restore account's original nickname (bugsbot{N})"""
        try:
            with db_helper.get_db() as db:
                from init_database import GemAccount
                
                account = db.query(GemAccount).filter_by(id=account_id).first()
                if not account:
                    return False
                
                original_nickname = f"bugsbot{account.account_number}"
                
                if self.change_account_nickname(account.email, account.password, original_nickname):
                    account.current_nickname = original_nickname
                    db.commit()
                    
                    print(f"♻️ Restored account #{account.account_number} to {original_nickname}")
                    return True
                
                return False
                
        except Exception as e:
            print(f"❌ Error restoring nickname: {e}")
            return False
    
    def send_gift_with_auto_switch(self, recipient_username, product, message=""):
        """Send gift with automatic account switching"""
        try:
            gem_cost = product.get('cost', 0)

            print(f"🎁 Preparing to send {product['name']} ({gem_cost} gems) to {recipient_username}")

            # Find account with enough gems
            account = self.get_active_account_with_gems(gem_cost)
            print(f"💎 Selected account #{account['account_number']} | Email: {account['email']} | Gems remaining: {account['gems_remaining']} | Required: {gem_cost}")

            # Switch to this account (changes nickname to RXZBOT)
            if not self.switch_to_account(account['id']):
                raise Exception("Failed to switch to account")

            # Search for recipient (uses managed/global tokens)
            player = wolvesville_api.search_player(recipient_username)
            if not player:
                # Restore nickname before failing
                self.restore_account_nickname(account['id'])
                raise Exception(f"Player '{recipient_username}' not found")

            player_id = player.get('id')

            # Prepare gift request
            gift_type = product.get('type')
            gift_message = message or "Gift from Wolvesville Shop!"

            body = {
                'type': gift_type,
                'giftRecipientId': player_id,
                'giftMessage': gift_message
            }

            # Add calendar ID if it's a calendar
            if gift_type == 'CALENDAR':
                calendar_id = product.get('id')
                if calendar_id:
                    body['calendarId'] = calendar_id

            # Get tokens for this specific gem account
            tokens = token_manager.get_tokens_for_account(account['email'], account['password'])
            print(f"🔑 Using tokens for account: {account['email']}")

            # Send gift using account-specific tokens
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {tokens['bearer']}",
                'Cf-JWT': tokens['cfJwt'],
                'ids': '1'
            }

            print(f"📦 Sending POST to Wolvesville API with body: {body} and headers: [Authorization: Bearer {tokens['bearer'][:8]}..., Cf-JWT: {tokens['cfJwt'][:8]}...]")

            response = requests.post(
                'https://core.api-wolvesville.com/gemOffers/purchases',
                json=body,
                headers=headers,
                timeout=10
            )

            print(f"🔄 Wolvesville API response: {response.status_code} {response.text}")

            # Try to parse gemCount from the response body (available after purchase attempt)
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None

            # If response contains gemCount, sync local DB
            if resp_json and isinstance(resp_json, dict):
                gem_count = None
                if 'gemCount' in resp_json:
                    gem_count = resp_json.get('gemCount')
                elif 'gems' in resp_json:
                    gem_count = resp_json.get('gems')

                try:
                    if gem_count is not None:
                        real_gems = int(gem_count)
                        print(f"🔄 Wolvesville returned gemCount: {real_gems} — syncing local account #{account['account_number']}")
                        self.recharge_account(account['id'], real_gems)
                        account['gems_remaining'] = real_gems
                except Exception:
                    pass

            if response.status_code == 200:
                # Success! Deduct gems locally if response didn't provide exact count
                if not (resp_json and ('gemCount' in resp_json or 'gems' in resp_json)):
                    self.deduct_gems(account['id'], gem_cost)

                # Restore original nickname
                self.restore_account_nickname(account['id'])

                print(f"✅ Gift sent successfully!")
                return resp_json or {'status': 'ok'}
            else:
                # If we have new gemCount info, we've already synced above
                # Failed - restore nickname
                self.restore_account_nickname(account['id'])

                error_msg = f"API error {response.status_code}: {response.text}"
                print(f"❌ {error_msg}")
                raise Exception(error_msg)

        except Exception as e:
            print(f"❌ send_gift_with_auto_switch error: {e}")
            raise

# Global instance
gem_account_manager = GemAccountManager()