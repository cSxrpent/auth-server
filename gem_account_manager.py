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

        # If some accounts currently have the RXZBOT nickname but don't have
        # enough gems for this purchase, randomize their nickname so the
        # RXZBOT name can be claimed by an account that does have enough gems.
        for acc in accounts:
            try:
                if acc.get('current_nickname') and acc.get('current_nickname').lower() == self.RXZBOT_NAME.lower() and acc.get('gems_remaining', 0) < required_gems:
                    print(f"♻️ Account #{acc['account_number']} lacks {required_gems} gems — randomizing nickname")
                    # Best-effort: change nickname to randomized prefix
                    try:
                        self.change_account_nickname(acc['email'], acc['password'], self._random_nickname(acc['email']))
                    except Exception as e:
                        print(f"❌ Failed to randomize nickname for {acc['email']}: {e}")
            except Exception:
                continue

        return viable_accounts[0]

    def _random_nickname(self, email):
        """Generate nickname: prefix of email + 6 random digits"""
        import secrets
        prefix = email.split('@')[0]
        rand = str(secrets.randbelow(10**6)).zfill(6)
        return f"{prefix}{rand}"
    
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
    
    def send_gift_with_auto_switch(self, recipient_player_id, product, message=""):
        """Send gift with automatic account switching.

        recipient_player_id: already-validated Wolvesville player ID (UUID)
        """
        try:
            gem_cost = product.get('cost', 0)

            print(f"🎁 Preparing to send {product['name']} ({gem_cost} gems) to player {recipient_player_id}")

            # Load all accounts and identify which currently holds RXZBOT
            accounts = self.get_all_gem_accounts()
            rxz_account = None
            for a in accounts:
                if a.get('current_nickname') and a.get('current_nickname').lower() == self.RXZBOT_NAME.lower():
                    rxz_account = a
                    break

            # Build candidate list in order: prefer existing RXZBOT (if enough gems),
            # otherwise viable accounts sorted by last_used
            candidates = []
            if rxz_account and rxz_account.get('gems_remaining', 0) >= gem_cost:
                candidates.append(rxz_account)
            else:
                # If RXZBOT exists but lacks gems, randomize it to free the name
                if rxz_account:
                    print(f"♻️ Current RXZBOT account #{rxz_account['account_number']} lacks {gem_cost} gems — randomizing its nickname")
                    try:
                        self.change_account_nickname(rxz_account['email'], rxz_account['password'], self._random_nickname(rxz_account['email']))
                    except Exception as e:
                        print(f"❌ Failed to randomize current RXZBOT account: {e}")
                    try:
                        with db_helper.get_db() as db:
                            from init_database import GemAccount
                            acc_row = db.query(GemAccount).filter_by(id=rxz_account['id']).first()
                            if acc_row:
                                acc_row.current_nickname = self._random_nickname(rxz_account['email'])
                                db.commit()
                    except Exception:
                        pass

                viable = [a for a in accounts if a['is_active'] and a.get('gems_remaining', 0) >= gem_cost]
                if not viable:
                    raise Exception(f"❌ No accounts with {gem_cost} gems available!")
                viable.sort(key=lambda x: x['last_used'] or '1970-01-01')
                candidates.extend(viable)

            # Attempt sending using candidates sequentially; on failure, randomize nickname and continue
            last_error = None
            for candidate in candidates:
                try:
                    # If candidate is not already RXZBOT, switch it to RXZBOT
                    if not (candidate.get('current_nickname') and candidate.get('current_nickname').lower() == self.RXZBOT_NAME.lower()):
                        print(f"💎 Switching account #{candidate['account_number']} to RXZBOT")
                        if not self.switch_to_account(candidate['id']):
                            raise Exception("Failed to switch to candidate account")

                    # Allow nickname propagation
                    time.sleep(2)

                    # Prepare gift request body
                    gift_type = product.get('type')
                    gift_message = message or "Gift from Wolvesville Shop!"

                    body = {
                        'type': gift_type,
                        'giftRecipientId': recipient_player_id,
                        'giftMessage': gift_message
                    }
                    if gift_type == 'CALENDAR':
                        calendar_id = product.get('id')
                        if calendar_id:
                            body['calendarId'] = calendar_id

                    # Get tokens for this specific gem account
                    tokens = token_manager.get_tokens_for_account(candidate['email'], candidate['password'])
                    print(f"🔑 Using tokens for account: {candidate['email']}")

                    headers = {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'Authorization': f"Bearer {tokens['bearer']}",
                        'Cf-JWT': tokens['cfJwt'],
                        'ids': '1'
                    }

                    print(f"📦 Sending POST to Wolvesville API with body: {body} and headers: [Authorization: Bearer {tokens['bearer'][:8]}..., Cf-JWT: {tokens['cfJwt'][:8]}...]")
                    response = requests.post('https://core.api-wolvesville.com/gemOffers/purchases', json=body, headers=headers, timeout=10)
                    print(f"🔄 Wolvesville API response: {response.status_code} {response.text}")

                    try:
                        resp_json = response.json()
                    except Exception:
                        resp_json = None

                    # Sync gemCount if provided
                    if resp_json and isinstance(resp_json, dict):
                        gem_count = None
                        if 'gemCount' in resp_json:
                            gem_count = resp_json.get('gemCount')
                        elif 'gems' in resp_json:
                            gem_count = resp_json.get('gems')
                        try:
                            if gem_count is not None:
                                real_gems = int(gem_count)
                                print(f"🔄 Wolvesville returned gemCount: {real_gems} — syncing local account #{candidate['account_number']}")
                                self.recharge_account(candidate['id'], real_gems)
                                candidate['gems_remaining'] = real_gems
                        except Exception:
                            pass

                    if response.status_code == 200:
                        if not (resp_json and ('gemCount' in resp_json or 'gems' in resp_json)):
                            self.deduct_gems(candidate['id'], gem_cost)
                        print("✅ Gift sent successfully!")
                        return resp_json or {'status': 'ok'}

                    # Non-200 -> randomize candidate nickname and try next
                    try:
                        self.change_account_nickname(candidate['email'], candidate['password'], self._random_nickname(candidate['email']))
                    except Exception:
                        pass

                    last_error = Exception(f"API error {response.status_code}: {response.text}")
                    print(f"❌ Candidate account failed, trying next if available: {last_error}")
                    continue

                except Exception as e:
                    print(f"❌ Attempt with account #{candidate.get('account_number')} failed: {e}")
                    last_error = e
                    try:
                        self.change_account_nickname(candidate['email'], candidate['password'], self._random_nickname(candidate['email']))
                    except Exception:
                        pass
                    continue

            # If we get here, all attempts failed
            raise last_error or Exception("All candidate accounts failed to send gift")

        except Exception as e:
            print(f"❌ send_gift_with_auto_switch error: {e}")
            raise

# Global instance
gem_account_manager = GemAccountManager()