import json
import time
import requests
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# Load secrets directly bypassing streamlit app context since this runs headless
try:
    with open(".streamlit/secrets.toml", "r") as f:
        # Extremely basic TOML parsing to extract secrets for the headless script
        secrets_text = f.read()
except FileNotFoundError:
    print("No local secrets found. Assuming GitHub Secrets environment.")
    secrets_text = ""

# Since this script runs on GitHub Actions, it will use st.secrets which GitHub Actions
# can inject via a .streamlit/secrets.toml file we generate in the workflow.
owner_email = st.secrets.get("OWNER_EMAIL", "")
webhook_url = st.secrets.get("DISCORD_WEBHOOK", "")
user_agent = st.secrets.get("USER_AGENT", "Gilded Set-Master GitHub Actions")

if not webhook_url:
    print("No Discord Webhook configured. Exiting.")
    exit(0)

# Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)
df_all = conn.read(worksheet="Sheet1", ttl=0)
df_all = df_all.dropna(how="all")

if "user_email" not in df_all.columns:
    print("Database is empty or missing columns.")
    exit(0)

# Get current user's "Buying" orders
df = df_all[df_all["user_email"] == owner_email]
buying_df = df[df["status"] == "Buying"]

if buying_df.empty:
    print("No active orders found. Exiting.")
    exit(0)

# Fetch current live prices
headers = {"User-Agent": user_agent}
url = "https://prices.runescape.wiki/api/v1/osrs/latest"
try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    prices_data = response.json().get("data", {})
except Exception as e:
    print(f"Failed to fetch prices from OSRS Wiki: {e}")
    exit(1)

alerts_to_send = []

for idx, row in buying_df.iterrows():
    item_id = str(row["item_id"])
    item_name = row["item_name"]
    order_price = int(row["price"])
    qty = int(row["quantity"])
    
    live_data = prices_data.get(item_id, {})
    current_low = live_data.get("low", 0)
    
    # If the current low in the market is higher than our bid, we are buried!
    # (Because the target buy is current_low + 1)
    if current_low > 0 and current_low > order_price:
        diff = current_low - order_price
        alerts_to_send.append(
            f"⚠️ **{item_name}** ({qty}x)\n"
            f"> Your Bid: `{order_price:,} GP`\n"
            f"> Current Low: `{current_low:,} GP`\n"
            f"> *You are underbid by {diff:,} GP!*"
        )

# Send Discord Webhook
if alerts_to_send:
    print(f"Sending {len(alerts_to_send)} alerts to Discord...")
    payload = {
        "content": "🔔 **Penny-Pincher Alert**\n" + "\n\n".join(alerts_to_send)
    }
    push_resp = requests.post(webhook_url, json=payload)
    if push_resp.status_code == 204:
        print("Webhook sent successfully.")
    else:
        print(f"Failed to send webhook: {push_resp.status_code} {push_resp.text}")
else:
    print("All orders are currently competitive. No alerts sent.")
