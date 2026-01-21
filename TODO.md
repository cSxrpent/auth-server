# Proxy Integration Task

## Steps to Complete
- [x] Add proxy configuration to token_manager.py
- [x] Add proxy configuration to shop_data_fetcher.py
- [x] Test proxy integration

## Information Gathered
- token_manager.py: Makes multiple requests to Wolvesville APIs (auth.api-wolvesville.com, core.api-wolvesville.com) using the requests library.
- shop_data_fetcher.py: Makes requests to core.api-wolvesville.com using requests.
- static/shop.js: Client-side JavaScript making fetch requests to local server endpoints (/api/shop/*) and loading images from CDN - no proxy needed.

## Plan Details
- Add proxy configuration to token_manager.py: Define the proxy dict and pass it to all requests.get/post calls.
- Add proxy configuration to shop_data_fetcher.py: Define the proxy dict and pass it to all requests.get/post calls.
- No changes to shop.js as it handles local API calls and image loads.

## Dependent Files
- token_manager.py
- shop_data_fetcher.py

## Followup Steps
- Test the proxy integration to ensure requests work through the proxy.
