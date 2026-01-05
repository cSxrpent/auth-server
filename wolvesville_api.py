import requests
from token_manager import token_manager

class WolvesvilleAPI:
    BASE_URL = "https://core.api-wolvesville.com"
    
    def __init__(self):
        self.token_manager = token_manager
    
    def _get_headers(self):
        """Get headers with valid tokens"""
        tokens = self.token_manager.get_valid_tokens()
        return {
            'accept': 'application/json',
            'authorization': f'Bearer {tokens["bearer"]}',
            'cf-jwt': tokens['cfJwt'],
            'content-type': 'application/json'
        }
    
    def search_player(self, username):
        """Search for a player by username"""
        try:
            url = f"{self.BASE_URL}/players/search?username={username}"
            headers = self._get_headers()
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data[0] if data else None
            elif response.status_code == 403:
                # Token might be expired, try refreshing
                print("⚠️ 403 error, refreshing tokens...")
                self.token_manager.refresh_tokens()
                # Retry once
                headers = self._get_headers()
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return data[0] if data else None
            
            print(f"❌ Player search failed: {response.status_code}")
            return None
            
        except Exception as e:
            print(f"❌ Error searching player: {e}")
            return None
    
    def get_player_profile(self, player_id):
        """Get full player profile by ID"""
        try:
            url = f"{self.BASE_URL}/players/{player_id}"
            headers = self._get_headers()
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                # Token might be expired, try refreshing
                print("⚠️ 403 error, refreshing tokens...")
                self.token_manager.refresh_tokens()
                # Retry once
                headers = self._get_headers()
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    return response.json()
            
            print(f"❌ Get profile failed: {response.status_code}")
            return None
            
        except Exception as e:
            print(f"❌ Error getting profile: {e}")
            return None

# Global API instance
wolvesville_api = WolvesvilleAPI()