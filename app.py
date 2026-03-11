import streamlit as st
import requests
import time
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Mobile optimization: centered layout, collapsed sidebar
st.set_page_config(page_title="Gilded Set-Master", layout="centered", initial_sidebar_state="collapsed")

# Custom CSS for large touch targets
st.markdown("""
<style>
    .stButton>button {
        height: 60px;
        font-size: 20px;
        font-weight: bold;
        border-radius: 12px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 26px;
    }
</style>
""", unsafe_allow_html=True)

# Authentication logic (Streamlit >= 1.40 Google Auth)
owner_email = st.secrets.get("OWNER_EMAIL", "local_user")

# Determine current user
current_user = "local_user"
if hasattr(st, "experimental_user") and getattr(st.experimental_user, "is_logged_in", False):
    current_user = st.experimental_user.email

# Restrict Access
if owner_email != "local_user" and current_user != owner_email:
    st.warning("Authentication required to use this application.")
    
    # Temporary debug flag to see what Streamlit thinks our email is:
    if hasattr(st, "experimental_user"):
        st.info(f"Debug Info: Streamlit sees your email as: '{current_user}'")
        
    try:
        if hasattr(st, "login"):
            st.login()
    except Exception:
        pass
    st.error("Unauthorized: Access restricted to the application owner.")
    st.stop()

# --- DB Initialization / Fetching ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_all = conn.read(worksheet="Sheet1")
    df_all = df_all.dropna(how="all")
    if "user_email" not in df_all.columns:
        df_all = pd.DataFrame(columns=["user_email", "item_id", "item_name", "price", "quantity", "status", "timestamp"])
except Exception as e:
    # Fallback to empty DataFrame if sheet doesn't exist or is completely empty
    df_all = pd.DataFrame(columns=["user_email", "item_id", "item_name", "price", "quantity", "status", "timestamp"])

# Sanitize formatting from fresh gsheets reads
df_all["item_id"] = pd.to_numeric(df_all["item_id"], errors='coerce').fillna(0).astype(int)
df_all["price"] = pd.to_numeric(df_all["price"], errors='coerce').fillna(0).astype(int)
df_all["quantity"] = pd.to_numeric(df_all["quantity"], errors='coerce').fillna(0).astype(int)

# Filter for current user securely
df = df_all[df_all["user_email"] == current_user]

ITEMS = {
    3481: "Gilded platebody",
    3483: "Gilded platelegs",
    3486: "Gilded full helm",
    3488: "Gilded kiteshield",
    13036: "Gilded armour set (lg)"
}
COMPONENTS = [3481, 3483, 3486, 3488]
SET_ID = 13036

# --- Top Refresh Button ---
if st.button("🔄 Refresh Data", use_container_width=True):
    pass # Inherent rerun on click

# --- Data Fetching ---
@st.cache_data(ttl=15)
def fetch_prices():
    try:
        user_agent = st.secrets["USER_AGENT"]
    except Exception:
        user_agent = "Gilded Set-Master Local" 
        
    headers = {"User-Agent": user_agent}
    url = "https://prices.runescape.wiki/api/v1/osrs/latest"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json().get("data", {})
        
        # Attach our own timestamp to know when WE last checked
        return {"fetched_at": time.time(), "items": data}
    except Exception as e:
        st.error(f"Failed to fetch prices: {e}")
        return {"fetched_at": 0, "items": {}}

api_data = fetch_prices()
prices_data = api_data.get("items", {})
fetch_time = api_data.get("fetched_at", 0)
current_time = time.time()

def get_item_data(item_id):
    return prices_data.get(str(item_id), {"low": 0, "high": 0})

def is_stale():
    # Stale if we haven't successfully fetched in over 120 seconds
    return (current_time - fetch_time) > 120

# --- Penny-Pincher Engine ---
st.header("The Penny-Pincher Engine")

sum_target_buys = 0
components_data = []

# If the API cache itself is older than 120s, everything is stale
data_is_stale = is_stale()

for cid in COMPONENTS:
    d = get_item_data(cid)
    raw_low = d.get("low", 0)
    target_buy = raw_low + 1 if raw_low > 0 else 0
    
    components_data.append({
        "id": cid,
        "name": ITEMS[cid],
        "target_buy": target_buy,
        "stale": data_is_stale,
        "raw_low": raw_low
    })
    sum_target_buys += target_buy

set_data = get_item_data(SET_ID)
raw_high = set_data.get("high", 0)
target_sell = raw_high - 1 if raw_high > 0 else 0
set_stale = data_is_stale

# Net Profit = (Target_Sell * 0.98) - Sum(Target_Buy_Prices)
net_profit = (target_sell * 0.98) - sum_target_buys
break_even = sum_target_buys / 0.98 if sum_target_buys > 0 else 0

col1, col2 = st.columns(2)
with col1:
    st.metric("Total Bid (Sum)", f"{sum_target_buys:,.0f} GP")
with col2:
    st.metric("Target Ask (Set)", f"{target_sell:,.0f} GP")

profit_color = "green" if net_profit > 0 else "red"
st.markdown(f"<h3 style='text-align: center'>Net Profit: <span style='color:{profit_color}'>{net_profit:,.0f} GP</span></h3>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center'><b>Break-even Set Ask:</b> {break_even:,.0f} GP</p>", unsafe_allow_html=True)

if set_stale:
    st.error("⚠️ Set Sell Price is STALE (> 120s old)")

st.divider()

st.subheader("Component Target Bids")
for c in components_data:
    stale_text = " ⚠️ **STALE**" if c["stale"] else ""
    st.write(f"- **{c['name']}**: {c['target_buy']:,.0f} GP{stale_text}")

st.divider()

# --- Ledger & Inventory Management ---
st.header("Ledger & Inventory")

with st.expander("Log Transaction", expanded=False):
    with st.form("log_tx"):
        tx_item = st.selectbox("Item", list(ITEMS.values()))
        tx_price = st.number_input("Actual Price (GP)", min_value=0, step=1000)
        tx_quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
        tx_status = st.selectbox("Status", ["Buying", "Owned", "Sold"])
        
        if st.form_submit_button("Log Entry", use_container_width=True):
            item_id = [k for k, v in ITEMS.items() if v == tx_item][0]
            new_row = {
                "user_email": current_user,
                "item_id": int(item_id),
                "item_name": tx_item,
                "price": int(tx_price),
                "quantity": int(tx_quantity),
                "status": tx_status,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }
            new_df = pd.DataFrame([new_row])
            updated_df = pd.concat([df_all, new_df], ignore_index=True)
            conn.update(worksheet="Sheet1", data=updated_df)
            st.cache_data.clear()
            st.success("Transaction Logged!")
            time.sleep(1)
            st.rerun()

st.subheader("Inventory Work-in-Progress")
if not df.empty:
    # We consider "Owned" or "Buying" as incoming inventory logic
    incoming_df = df[df["status"].isin(["Owned", "Buying"])]
    incoming_counts = incoming_df.groupby("item_id")["quantity"].sum().to_dict()
    
    sold_df = df[df["status"] == "Sold"]
    sold_counts = sold_df.groupby("item_id")["quantity"].sum().to_dict()
    
    # Selling a set implicitly consumes 1 of each component in our ledger logic
    sold_sets = sold_counts.get(SET_ID, 0)
    
    current_inventory = {}
    for cid in COMPONENTS + [SET_ID]:
        # Owned/Buying minus sold individual components minus sold sets (for components)
        baseline = incoming_counts.get(cid, 0) - sold_counts.get(cid, 0)
        if cid in COMPONENTS:
            current_inventory[cid] = baseline - sold_sets
        else:
            current_inventory[cid] = baseline
        
    missing = [cid for cid in COMPONENTS if current_inventory[cid] < 1]
    
    if 0 < len(missing) < 4:
        st.write("You own some pieces, but are missing:")
        for m_id in missing:
            c_name = ITEMS[m_id]
            live_low = next((c['raw_low'] for c in components_data if c['id'] == m_id), 0)
            st.write(f"- 🔴 **{c_name}** (Current Low: {live_low:,.0f} GP)")
    elif len(missing) == 0:
        if any(current_inventory[cid] >= 1 for cid in COMPONENTS):
            st.success("✅ Set is fully assembled and ready to sell!")
        else:
             st.info("No pieces owned currently.")
    else:
        st.info("No pieces owned currently.")
else:
    st.info("No pieces owned currently.")

st.divider()

st.subheader("History & Profit Metrics")
if not df.empty:
    # --- Realized Profit Calculation ---
    # To find strict realized profit, we pair each sold set/component with its purchase cost. 
    # For simplicity, we calculate total revenue from "Sold" and subtract the exact cost basis of those sold items.
    # Total Revenue (post 2% tax)
    total_revenue = (df[df["status"] == "Sold"]["price"] * df[df["status"] == "Sold"]["quantity"] * 0.98).sum()
    
    # Calculate average cost basis of all items purchased to subtract from total_revenue
    # (A more complex FIFO method could be used, but average cost is simpler for a mobile view).
    buy_df = df[df["status"].isin(["Owned", "Buying"])]
    avg_costs = {}
    for item_id, group in buy_df.groupby("item_id"):
        avg_costs[item_id] = (group["price"] * group["quantity"]).sum() / group["quantity"].sum()
        
    total_cogs = 0 # Cost of Goods Sold
    for index, row in df[df["status"] == "Sold"].iterrows():
        sid = row["item_id"]
        sqty = row["quantity"]
        if sid == SET_ID:
            # Reconstruct cost basis of the set from its components
            set_cogs = sum([avg_costs.get(cid, 0) for cid in COMPONENTS]) * sqty
            total_cogs += set_cogs
        else:
            # Standalone component sale
            total_cogs += avg_costs.get(sid, 0) * sqty
            
    realized_profit = total_revenue - total_cogs
    
    # --- Unrealized Value Calculation ---
    # The user wants "Unrealized" to mean the total Capital Deployed (Cost Basis) for the current inventory.
    inventory_cost = 0
    
    for cid in COMPONENTS + [SET_ID]:
        inv_qty = current_inventory.get(cid, 0)
        if inv_qty > 0:
            # What we paid (Capital Tied Up)
            cost_basis = avg_costs.get(cid, 0) * inv_qty
            inventory_cost += cost_basis

    colA, colB = st.columns(2)
    with colA:
        r_color = "green" if realized_profit >= 0 else "red"
        st.markdown(f"**Realized Profit:**<br><span style='color:{r_color}; font-size:20px'>{realized_profit:,.0f} GP</span>", unsafe_allow_html=True)
    with colB:
        # Since it is just cost, we can make it blue or standard text instead of red/green.
        st.markdown(f"**Inventory (At Cost):**<br><span style='color:inherit; font-size:20px'>{inventory_cost:,.0f} GP</span>", unsafe_allow_html=True)
    
    st.write("") # spacing
    with st.expander("View Ledger Logs", expanded=False):
        for i, row in df.sort_values(by="timestamp", ascending=False).head(20).iterrows():
            st.write(f"`{row['timestamp'][:16]}` | **{row['item_name']}** | {row['quantity']}x @ {row['price']:,.0f} GP [{row['status']}]")
else:
    st.write("No transaction history available.")
