# Auth Server - RXZBot

A Flask-based authentication server for RXZBot with PayPal payment integration.

## Setup

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your actual values and run:
   ```bash
   python server.py
   ```

### Deploy to Render.com

1. Push your code to GitHub
2. Create a new Web Service on Render.com
3. Connect your GitHub repo
4. Set environment variables in Render dashboard (Environment section):
   - `PAYPAL_CLIENT_ID`
   - `PAYPAL_CLIENT_SECRET`
   - `PAYPAL_MODE` (sandbox or live)
   - `EMAIL_USER`
   - `EMAIL_PASS`
   - `EMAIL_SMTP` (default: smtp.gmail.com)
   - `EMAIL_PORT` (default: 587)
   - `SECRET_KEY`
   - `ADMIN_PASSWORD`
   - `GITHUB_TOKEN` (optional)

5. Deploy!

## Features

- User authentication for RXZBot
- PayPal payment integration with automatic license activation
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