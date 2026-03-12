import json
import time
import requests
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# Load secrets directly bypassing streamlit app context since this runs headless
try:
    with open(".streamlit/secrets.toml", "r") as f:
        secrets_text = f.read()
except FileNotFoundError:
    print("No local secrets found. Assuming GitHub Secrets environment.")
    secrets_text = ""

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

# Ensure required columns exist (handles older sheets missing new columns)
for col in ["last_alert_price", "last_known_high", "cooldown"]:
    if col not in df_all.columns:
        df_all[col] = ""

# Sanitize numeric columns
df_all["item_id"] = pd.to_numeric(df_all["item_id"], errors='coerce').fillna(0).astype(int)
df_all["price"] = pd.to_numeric(df_all["price"], errors='coerce').fillna(0).astype(int)
df_all["quantity"] = pd.to_numeric(df_all["quantity"], errors='coerce').fillna(0).astype(int)

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

SQUEEZE_THRESHOLD_PCT = 0.01   # 1% spike = cooldown trigger
SPREAD_MIN_GP = 5000           # Spread must reopen by at least 5k GP to exit cooldown

alerts_to_send = []
df_updated = False

for idx, row in active_df.iterrows():
    item_id = str(row["item_id"])
    item_name = row["item_name"]
    order_price = int(row["price"])
    qty = int(row["quantity"])
    status = row["status"]

    # Parse last_alert_price safely
    last_alert_raw = row.get("last_alert_price")
    last_alert = 0
    if not pd.isna(last_alert_raw) and str(last_alert_raw).strip() != "":
        try:
            last_alert = int(float(last_alert_raw))
        except (ValueError, TypeError):
            last_alert = 0

    # Parse last_known_high safely
    last_known_high_raw = row.get("last_known_high")
    last_known_high = 0
    if not pd.isna(last_known_high_raw) and str(last_known_high_raw).strip() != "":
        try:
            last_known_high = int(float(last_known_high_raw))
        except (ValueError, TypeError):
            last_known_high = 0

    # Parse cooldown flag safely
    cooldown_raw = row.get("cooldown")
    is_cooldown = str(cooldown_raw).strip().lower() == "true" if not pd.isna(cooldown_raw) else False

    live_data = prices_data.get(item_id, {})
    current_low = int(live_data.get("low", 0))
    current_high = int(live_data.get("high", 0))

    # --- Cooldown / Squeeze Detection (Buy orders only) ---
    if status == "Buying" and current_high > 0 and current_low > 0:
        spread = current_high - current_low

        if not is_cooldown:
            # Check ENTER condition: high spiked >1% AND spread collapsed
            if last_known_high > 0:
                pct_change = (current_high - last_known_high) / last_known_high
                if pct_change > SQUEEZE_THRESHOLD_PCT and spread < SPREAD_MIN_GP:
                    is_cooldown = True
                    df_all.at[idx, "cooldown"] = "true"
                    df_updated = True
                    # Silently enter cooldown state to suppress outbid alerts
        else:
            # Check EXIT condition: spread reopened
            if spread >= SPREAD_MIN_GP:
                is_cooldown = False
                df_all.at[idx, "cooldown"] = ""
                df_updated = True
                # Silently exit cooldown state

        # Always update last_known_high
        if current_high != last_known_high:
            df_all.at[idx, "last_known_high"] = current_high
            df_updated = True

    # --- Price Alert Logic (skip if in cooldown) ---
    if is_cooldown:
        continue

    msg = None
    market_price = 0

    if status == "Buying":
        if current_low > 0:
            if current_low > order_price:
                # Outbid
                market_price = current_low
                if market_price != last_alert:
                    diff = current_low - order_price
                    msg = (f"⚠️ **[OUTBID] {item_name}** ({qty}x)\n"
                           f"> Your Bid: `{order_price:,} GP`\n"
                           f"> Current Low: `{current_low:,} GP`\n"
                           f"> *You are outbid by {diff:,} GP!*")
            elif current_low <= order_price:
                # Likely filled
                market_price = current_low
                if market_price != last_alert:
                    if last_alert == 0:
                        # First run for this order, seed the state silently
                        df_all.at[idx, "last_alert_price"] = market_price
                        df_updated = True
                    else:
                        msg = (f"✅ **[LIKELY FILLED] {item_name}** ({qty}x)\n"
                               f"> Your Bid: `{order_price:,} GP`\n"
                               f"> Current Low: `{current_low:,} GP`\n"
                               f"> *The price hit {current_low:,} GP. Your order is likely filled!*")

    elif status == "Selling":
        if current_high > 0:
            if current_high < order_price:
                # Undercut
                market_price = current_high
                if market_price != last_alert:
                    diff = order_price - current_high
                    msg = (f"⚠️ **[UNDERCUT] {item_name}** ({qty}x)\n"
                           f"> Your Ask: `{order_price:,} GP`\n"
                           f"> Current High: `{current_high:,} GP`\n"
                           f"> *You are undercut by {diff:,} GP!*")
            elif current_high >= order_price:
                # Likely sold
                market_price = current_high
                if market_price != last_alert:
                    if last_alert == 0:
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
