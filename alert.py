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

# Get current user's active orders
df = df_all[df_all["user_email"] == owner_email]
active_df = df[df["status"].isin(["Buying", "Selling"])]

if active_df.empty:
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
df_updated = False

for idx, row in active_df.iterrows():
    item_id = str(row["item_id"])
    item_name = row["item_name"]
    order_price = int(row["price"])
    qty = int(row["quantity"])
    status = row["status"]
    last_alert = row.get("last_alert_price")
    
    # Handle NaNs from sheets
    if pd.isna(last_alert):
        last_alert = 0
    else:
        last_alert = int(last_alert)
    
    live_data = prices_data.get(item_id, {})
    current_low = int(live_data.get("low", 0))
    current_high = int(live_data.get("high", 0))
    
    msg = None
    market_price = 0
    
    if status == "Buying":
        if current_low > 0:
            # If the current low in the market is higher than our bid, we are buried!
            if current_low > order_price:
                market_price = current_low
                if market_price != last_alert:
                    diff = current_low - order_price
                    msg = (f"⚠️ **[OUTBID] {item_name}** ({qty}x)\n"
                           f"> Your Bid: `{order_price:,} GP`\n"
                           f"> Current Low: `{current_low:,} GP`\n"
                           f"> *You are outbid by {diff:,} GP!*")
            # If the current low hits our bid or goes under, a trade happened at or below our price
            elif current_low <= order_price:
                market_price = current_low
                if market_price != last_alert:
                    # Suppress false positives on brand new orders where the old trade was lower
                    if last_alert == 0 and current_low < order_price:
                        df_all.at[idx, "last_alert_price"] = market_price
                        df_updated = True
                    else:
                        msg = (f"✅ **[LIKELY FILLED] {item_name}** ({qty}x)\n"
                               f"> Your Bid: `{order_price:,} GP`\n"
                               f"> Current Low: `{current_low:,} GP`\n"
                               f"> *The price hit {current_low:,} GP. Your order is likely filled!*")

    elif status == "Selling":
        if current_high > 0:
            # If the current high in the market is lower than our ask, we are undercut!
            if current_high < order_price:
                market_price = current_high
                if market_price != last_alert:
                    diff = order_price - current_high
                    msg = (f"⚠️ **[UNDERCUT] {item_name}** ({qty}x)\n"
                           f"> Your Ask: `{order_price:,} GP`\n"
                           f"> Current High: `{current_high:,} GP`\n"
                           f"> *You are undercut by {diff:,} GP!*")
            # If the current high hits our ask or goes over, a trade happened at or above our price
            elif current_high >= order_price:
                market_price = current_high
                if market_price != last_alert:
                    # Suppress false positives on brand new orders where the old trade was higher
                    if last_alert == 0 and current_high > order_price:
                        df_all.at[idx, "last_alert_price"] = market_price
                        df_updated = True
                    else:
                        msg = (f"✅ **[LIKELY SOLD] {item_name}** ({qty}x)\n"
                               f"> Your Ask: `{order_price:,} GP`\n"
                               f"> Current High: `{current_high:,} GP`\n"
                               f"> *The price hit {current_high:,} GP. Your set is likely sold!*")

    if msg:
        alerts_to_send.append(msg)
        df_all.at[idx, "last_alert_price"] = market_price
        df_updated = True

# Send Discord Webhook
if alerts_to_send:
    print(f"Sending {len(alerts_to_send)} alerts to Discord...")
    payload = {
        "content": "🔔 **GE Flips Alert**\n" + "\n\n".join(alerts_to_send)
    }
    push_resp = requests.post(webhook_url, json=payload)
    if push_resp.status_code == 204:
        print("Webhook sent successfully.")
    else:
        print(f"Failed to send webhook: {push_resp.status_code} {push_resp.text}")

# Only update the sheet if we actually changed the alert state
if df_updated:
    print("Updating alert state in Google Sheets...")
    conn.update(worksheet="Sheet1", data=df_all)
else:
    print("No new alerts. Sheet remains unchanged.")
