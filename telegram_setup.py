#!/usr/bin/env python3
"""
DataHunt — Telegram One-Time Setup
====================================
Run this script ONCE locally to authenticate with Telegram and get your
session string. Then paste the three env vars into Railway.

Prerequisites:
  1. pip install telethon
  2. Go to https://my.telegram.org → "API development tools"
  3. Create an app → note your API ID and API Hash
  4. Make sure you have joined the Secret Jobs channel:
     https://t.me/+ttg3AvOjEjNhMWU0

Usage:
  python telegram_setup.py
"""

def main():
    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("ERROR: telethon is not installed. Run:  pip install telethon")
        return

    print("=" * 55)
    print("  DataHunt — Telegram Setup")
    print("=" * 55)
    print("Get your credentials from: https://my.telegram.org")
    print()

    api_id   = input("Telegram API ID   : ").strip()
    api_hash = input("Telegram API Hash : ").strip()

    if not api_id.isdigit():
        print("ERROR: API ID must be a number.")
        return

    print("\nConnecting — Telegram will send you a code via SMS or the app...")
    try:
        with TelegramClient(StringSession(), int(api_id), api_hash) as client:
            session_str = client.session.save()
            me = client.get_me()
            print(f"\nAuthenticated as: {me.first_name} (@{me.username})")
            print("\n" + "=" * 55)
            print("  Add these to Railway → Service → Variables:")
            print("=" * 55)
            print(f"TELEGRAM_API_ID={api_id}")
            print(f"TELEGRAM_API_HASH={api_hash}")
            print(f"TELEGRAM_SESSION={session_str}")
            print("=" * 55)
            print("\nAlso set DATA_DIR to your persistent volume path if not already done.")
    except Exception as e:
        print(f"\nERROR: {e}")


if __name__ == "__main__":
    main()
