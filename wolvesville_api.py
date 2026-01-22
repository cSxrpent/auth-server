import requests
import logging
import time
from token_manager import token_manager

# Set up logger for Wolvesville API
logger = logging.getLogger('wolvesville_api')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

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
        start_time = time.time()
        logger.info(f"🔍 Starting player search for username: '{username}'")

        try:
            url = f"{self.BASE_URL}/players/search?username={username}"
            headers = self._get_headers()

            logger.debug(f"Player search URL: {url}")
            logger.debug(f"Request headers: accept={headers.get('accept')}, authorization=Bearer ***, cf-jwt=***")

            response = requests.get(url, headers=headers, proxies=self.token_manager.proxies, timeout=10)
            duration = time.time() - start_time

            logger.info(f"Player search response: status={response.status_code}, duration={duration:.2f}s")

            if response.status_code == 200:
                data = response.json()
                result_count = len(data) if data else 0
                logger.info(f"Player search successful: found {result_count} results")

                if data:
                    player = data[0]
                    player_id = player.get('id')
                    player_username = player.get('username')
                    logger.info(f"Player found: ID={player_id}, username='{player_username}'")
                    return player
                else:
                    logger.warning(f"No players found for username: '{username}'")
                    return None

            elif response.status_code == 403:
                logger.warning(f"403 Forbidden on player search - token might be expired")
                logger.info("Attempting token refresh and retry...")

                # Token might be expired, try refreshing
                refresh_start = time.time()
                self.token_manager.refresh_tokens()
                refresh_duration = time.time() - refresh_start
                logger.info(f"Token refresh completed in {refresh_duration:.2f}s")

                # Retry once
                headers = self._get_headers()
                retry_response = requests.get(url, headers=headers, proxies=self.token_manager.proxies, timeout=10)
                retry_duration = time.time() - start_time

                logger.info(f"Retry search response: status={retry_response.status_code}, total_duration={retry_duration:.2f}s")

                if retry_response.status_code == 200:
                    data = retry_response.json()
                    result_count = len(data) if data else 0
                    logger.info(f"Retry successful: found {result_count} results")

                    if data:
                        player = data[0]
                        player_id = player.get('id')
                        player_username = player.get('username')
                        logger.info(f"Player found on retry: ID={player_id}, username='{player_username}'")
                        return player
                    else:
                        logger.warning(f"No players found on retry for username: '{username}'")
                        return None
                else:
                    logger.error(f"Retry failed: status={retry_response.status_code}, response='{retry_response.text[:200]}...'")
                    return None

            elif response.status_code == 404:
                logger.warning(f"Player not found (404): '{username}'")
                return None
            elif response.status_code == 429:
                logger.error(f"Rate limited (429) on player search for '{username}'")
                return None
            else:
                logger.error(f"Player search failed: status={response.status_code}, response='{response.text[:200]}...'")
                return None

        except requests.exceptions.Timeout:
            duration = time.time() - start_time
            logger.error(f"Player search timeout after {duration:.2f}s for username: '{username}'")
            return None
        except requests.exceptions.ConnectionError as e:
            duration = time.time() - start_time
            logger.error(f"Player search connection error after {duration:.2f}s for username '{username}': {e}")
            return None
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Unexpected error in player search after {duration:.2f}s for username '{username}': {e}", exc_info=True)
            return None
    
    def get_player_profile(self, player_id):
        """Get full player profile by ID"""
        start_time = time.time()
        logger.info(f"🔍 Starting profile fetch for player ID: {player_id}")

        try:
            url = f"{self.BASE_URL}/players/{player_id}"
            headers = self._get_headers()

            logger.debug(f"Profile fetch URL: {url}")
            logger.debug(f"Request headers: accept={headers.get('accept')}, authorization=Bearer ***, cf-jwt=***")

            response = requests.get(url, headers=headers, timeout=10)
            duration = time.time() - start_time

            logger.info(f"Profile fetch response: status={response.status_code}, duration={duration:.2f}s")

            if response.status_code == 200:
                profile_data = response.json()
                logger.info(f"Profile fetch successful for player ID: {player_id}")
                return profile_data
            elif response.status_code == 403:
                logger.warning(f"403 Forbidden on profile fetch - token might be expired")
                logger.info("Attempting token refresh and retry...")

                # Token might be expired, try refreshing
                refresh_start = time.time()
                self.token_manager.refresh_tokens()
                refresh_duration = time.time() - refresh_start
                logger.info(f"Token refresh completed in {refresh_duration:.2f}s")

                # Retry once
                headers = self._get_headers()
                retry_response = requests.get(url, headers=headers, proxies=self.token_manager.proxies, timeout=10)
                retry_duration = time.time() - start_time

                logger.info(f"Retry profile fetch response: status={retry_response.status_code}, total_duration={retry_duration:.2f}s")

                if retry_response.status_code == 200:
                    profile_data = retry_response.json()
                    logger.info(f"Retry successful for profile fetch: player ID {player_id}")
                    return profile_data
                else:
                    logger.error(f"Retry failed: status={retry_response.status_code}, response='{retry_response.text[:200]}...'")
                    return None

            elif response.status_code == 404:
                logger.warning(f"Player profile not found (404): ID {player_id}")
                return None
            elif response.status_code == 429:
                logger.error(f"Rate limited (429) on profile fetch for ID {player_id}")
                return None
            else:
                logger.error(f"Profile fetch failed: status={response.status_code}, response='{response.text[:200]}...'")
                return None

        except requests.exceptions.Timeout:
            duration = time.time() - start_time
            logger.error(f"Profile fetch timeout after {duration:.2f}s for player ID: {player_id}")
            return None
        except requests.exceptions.ConnectionError as e:
            duration = time.time() - start_time
            logger.error(f"Profile fetch connection error after {duration:.2f}s for player ID {player_id}: {e}")
            return None
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Unexpected error in profile fetch after {duration:.2f}s for player ID {player_id}: {e}", exc_info=True)
            return None

# Global API instance
wolvesville_api = WolvesvilleAPI()