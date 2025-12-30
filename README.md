# Auth Server - RXZBot

A Flask-based authentication server for RXZBot with PayPal payment integration.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your actual values:
   - Get PayPal Client ID and Secret from [PayPal Developer](https://developer.paypal.com/)
   - For email, use Gmail app password (enable 2FA first)
   - Generate a random SECRET_KEY

4. Run the server:
   ```bash
   python server.py
   ```

## Features

- User authentication for RXZBot
- PayPal payment integration
- Automatic license activation
- Email notifications with download links
- Admin panel for user management

## PayPal Setup

1. Create a PayPal Business account
2. Go to [PayPal Developer Dashboard](https://developer.paypal.com/)
3. Create an app and get Client ID/Secret
4. Use sandbox mode for testing, live for production

## Email Setup (Gmail)

1. Enable 2FA on your Gmail account
2. Generate an App Password: https://support.google.com/accounts/answer/185833
3. Use your Gmail address as EMAIL_USER and the app password as EMAIL_PASS

## File Downloads

Place your bot files in the `static/` directory. The system will send download links via email after successful payment.