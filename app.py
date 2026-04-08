import streamlit as st
import requests
import time
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Mobile optimization: centered layout, collapsed sidebar
st.set_page_config(page_title="GE Flips", layout="centered", initial_sidebar_state="collapsed")

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
    a.wiki-link {
        text-decoration: none;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# Authentication logic
app_password = st.secrets.get("APP_PASSWORD", "")
owner_email = st.secrets.get("OWNER_EMAIL", "local_user")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if app_password and not st.session_state["authenticated"]:
    st.warning("🔒 Authentication Required")
    pwd_input = st.text_input("Enter Dashboard Password", type="password")
    if st.button("Unlock", use_container_width=True):
        if pwd_input == app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect Password")
    st.stop()

# If authenticated, use the owner_email for the database records
current_user = owner_email

# --- DB Initialization / Fetching ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_all = conn.read(worksheet="Sheet1", ttl=0)
    df_all = df_all.dropna(how="all")
    if "user_email" not in df_all.columns:
        df_all = pd.DataFrame(columns=["user_email", "item_id", "item_name", "price", "quantity", "status", "timestamp", "last_alert_price"])
except Exception as e:
    # Fallback to empty DataFrame if sheet doesn't exist or is completely empty
    df_all = pd.DataFrame(columns=["user_email", "item_id", "item_name", "price", "quantity", "status", "timestamp", "last_alert_price"])

# Ensure required columns exist
for col in ["last_alert_price", "last_known_high", "cooldown", "filled_notified", "last_alert_type"]:
    if col not in df_all.columns:
        df_all[col] = ""
    else:
        # Sanitize floats pandas might have magically converted from 'true' back to strings
        df_all[col] = df_all[col].astype(str).str.lower().replace(
            {"1.0": "true", "1": "true", "nan": "", "0.0": ""}
        )

# Sanitize formatting from fresh gsheets reads
df_all["item_id"] = pd.to_numeric(df_all["item_id"], errors='coerce').fillna(0).astype(int)
df_all["price"] = pd.to_numeric(df_all["price"], errors='coerce').fillna(0).astype(int)
df_all["quantity"] = pd.to_numeric(df_all["quantity"], errors='coerce').fillna(0).astype(int)

# Filter for current user securely
settings_row = df_all[(df_all["user_email"] == current_user) & (df_all["item_id"] == 0)]
available_gp = float(settings_row["price"].values[0]) if not settings_row.empty else 0.0

df = df_all[(df_all["user_email"] == current_user) & (df_all["item_id"] != 0)]

def parse_gp_input(val):
    if not val: return 0.0
    val = str(val).upper().replace(",", "").replace(" ", "")
    m = 1
    if val.endswith("M"):
        m = 1_000_000
        val = val[:-1]
    elif val.endswith("K"):
        m = 1_000
        val = val[:-1]
    elif val.endswith("B"):
        m = 1_000_000_000
        val = val[:-1]
    try:
        return float(val) * m
    except:
        return 0.0

with st.sidebar:
    st.header("⚙️ Configuration")
    new_gp_raw = st.text_input("Available GP to Flip", value=f"{available_gp:,.0f}")
    if st.button("Save Settings"):
        new_gp = parse_gp_input(new_gp_raw)
        if not settings_row.empty:
            idx = settings_row.index[0]
            df_all.at[idx, "price"] = float(new_gp)
        else:
            new_row = {"user_email": current_user, "item_id": 0, "item_name": "Bankroll", "price": float(new_gp), "quantity": 1, "status": "Settings", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}
            df_all = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
        conn.update(worksheet="Sheet1", data=df_all)
        st.cache_data.clear()
        st.rerun()

SETS_CONFIG = {
    "Gilded": {
        "set_id": 13036,
        "set_limit": 8,
        "components": [
            {"id": 3481, "name": "Gilded platebody", "limit": 8},
            {"id": 3483, "name": "Gilded platelegs", "limit": 8},
            {"id": 3486, "name": "Gilded full helm", "limit": 8},
            {"id": 3488, "name": "Gilded kiteshield", "limit": 8}
        ]
    },
    "Blood Moon": {
        "set_id": 31136,
        "set_limit": 2,
        "components": [
            {"id": 29028, "name": "Blood moon helm", "limit": 15},
            {"id": 29022, "name": "Blood moon chestplate", "limit": 15},
            {"id": 29025, "name": "Blood moon tassets", "limit": 15},
            {"id": 28997, "name": "Dual macuahuitl", "limit": 15}
        ]
    },
    "Blue Moon": {
        "set_id": 31139,
        "set_limit": 2,
        "components": [
            {"id": 29019, "name": "Blue moon helm", "limit": 15},
            {"id": 29013, "name": "Blue moon chestplate", "limit": 15},
            {"id": 29016, "name": "Blue moon tassets", "limit": 15},
            {"id": 28988, "name": "Blue moon spear", "limit": 15}
        ]
    },
    "Eclipse Moon": {
        "set_id": 31142,
        "set_limit": 2,
        "components": [
            {"id": 29010, "name": "Eclipse moon helm", "limit": 15},
            {"id": 29004, "name": "Eclipse moon chestplate", "limit": 15},
            {"id": 29007, "name": "Eclipse moon tassets", "limit": 15},
            {"id": 29000, "name": "Eclipse atlatl", "limit": 15}
        ]
    },
    "Virtus": {
        "set_id": 31148,
        "set_limit": 2,
        "components": [
            {"id": 26241, "name": "Virtus mask", "limit": 8},
            {"id": 26243, "name": "Virtus robe top", "limit": 8},
            {"id": 26245, "name": "Virtus robe bottom", "limit": 8}
        ]
    },
    "Justiciar": {
        "set_id": 22438,
        "set_limit": 5,
        "components": [
            {"id": 22326, "name": "Justiciar faceguard", "limit": 8},
            {"id": 22327, "name": "Justiciar chestguard", "limit": 8},
            {"id": 22328, "name": "Justiciar legguards", "limit": 8}
        ]
    },
    "Masori (f)": {
        "set_id": 27355,
        "set_limit": 5,
        "components": [
            {"id": 27235, "name": "Masori mask (f)", "limit": 8},
            {"id": 27238, "name": "Masori body (f)", "limit": 8},
            {"id": 27241, "name": "Masori chaps (f)", "limit": 8}
        ]
    }
}

ITEMS = {}
for key, cfg in SETS_CONFIG.items():
    ITEMS[cfg["set_id"]] = f"{key} armour set"
    for comp in cfg["components"]:
        ITEMS[comp["id"]] = comp["name"]

WIKI_LINK = "https://prices.runescape.wiki/osrs/item/"

# --- Top Refresh Button ---
if st.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()

# --- Data Fetching ---
@st.cache_data(ttl=15)
def fetch_prices():
    try:
        user_agent = st.secrets["USER_AGENT"]
    except Exception:
        user_agent = "GE Flips Local" 
        
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

@st.cache_data(ttl=300)
def fetch_timeseries(item_id):
    """Fetch 1-hour timeseries data (up to 365 points = ~15 days) for buy priority."""
    try:
        user_agent = st.secrets["USER_AGENT"]
    except Exception:
        user_agent = "GE Flips Local"
    
    headers = {"User-Agent": user_agent}
    url = f"https://prices.runescape.wiki/api/v1/osrs/timeseries?timestep=1h&id={item_id}"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception:
        return []

@st.cache_data(ttl=300)
def fetch_24h_volume():
    try:
        user_agent = st.secrets["USER_AGENT"]
    except Exception:
        user_agent = "GE Flips Local"
    
    headers = {"User-Agent": user_agent}
    url = "https://prices.runescape.wiki/api/v1/osrs/24h"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("data", {})
    except Exception:
        return {}

api_data = fetch_prices()
prices_data = api_data.get("items", {})
vol_data = fetch_24h_volume()
fetch_time = api_data.get("fetched_at", 0)
current_time = time.time()

def get_item_data(item_id):
    return prices_data.get(str(item_id), {"low": 0, "high": 0})

def is_stale():
    # Stale if we haven't successfully fetched in over 120 seconds
    return (current_time - fetch_time) > 120

# --- GE Flips Engine ---
st.header("GE Flips")

data_is_stale = is_stale()

st.subheader("📊 Most Profitable Sets")
dash_data = []

for s_name, cfg in SETS_CONFIG.items():
    s_id = cfg["set_id"]
    market_buys = sum([(get_item_data(c["id"]).get("low", 0) + 1172) if get_item_data(c["id"]).get("low", 0) > 0 else 0 for c in cfg["components"]])
    raw_high = get_item_data(s_id).get("high", 0)
    target_sell = raw_high - 1 if raw_high > 0 else 0
    profit_per_set = (target_sell * 0.98) - market_buys
    
    min_comp_limit = min([c["limit"] for c in cfg["components"]]) if cfg["components"] else 1
    ge_limit = min_comp_limit # Only bound by the components we have to BUY
    
    gp_limit = int(available_gp // market_buys) if market_buys > 0 else 0
    if available_gp <= 1:
        gp_limit = ge_limit # Unbounded by GP if not configured
        
    actual_max_sets = min(ge_limit, gp_limit)
    max_opportunity = profit_per_set * actual_max_sets
    
    volumes = []
    for c in cfg["components"]:
        vd = vol_data.get(str(c["id"]), {})
        vol = vd.get("highPriceVolume", 0) + vd.get("lowPriceVolume", 0)
        volumes.append(vol)
        
    bottleneck_vol = min(volumes) if volumes else 1
    if bottleneck_vol <= 0: bottleneck_vol = 1
    
    turnover_hz = bottleneck_vol / 24.0 # sets per hour
    mins_per_set = 60.0 / turnover_hz if turnover_hz > 0 else 999
    
    dash_data.append({
        "Set": s_name,
        "Profit/Set": profit_per_set,
        "Max Opportunity": max_opportunity,
        "Max Sets (GE+GP)": actual_max_sets,
        "Turnover": mins_per_set
    })

dash_df = pd.DataFrame(dash_data).sort_values("Max Opportunity", ascending=False).reset_index(drop=True)
dash_df.insert(0, "Rank", range(1, len(dash_df) + 1))
dash_df["Profit/Set"] = dash_df["Profit/Set"].apply(lambda x: f"{x:,.0f} GP")
dash_df["Max Opportunity"] = dash_df["Max Opportunity"].apply(lambda x: f"{x:,.0f} GP")
dash_df["Turnover"] = dash_df["Turnover"].apply(lambda x: f"~{x:,.0f} mins")

st.dataframe(dash_df, hide_index=True, use_container_width=True)
st.divider()

# --- Active Set Selection ---
all_set_names = dash_df["Set"].tolist()

def get_most_recent_set():
    if df.empty:
        return all_set_names[0]
    recent_item_id = df.sort_values("timestamp", ascending=False).iloc[0]["item_id"]
    for s_name, cfg in SETS_CONFIG.items():
        if recent_item_id == cfg["set_id"] or recent_item_id in [c["id"] for c in cfg["components"]]:
            return s_name
    return all_set_names[0]

default_set = get_most_recent_set()
default_idx = all_set_names.index(default_set) if default_set in all_set_names else 0

selected_set_name = st.selectbox("🎯 Active Trading Profile", all_set_names, index=default_idx)
ACTIVE_CONFIG = SETS_CONFIG[selected_set_name]
COMPONENTS = [c["id"] for c in ACTIVE_CONFIG["components"]]
SET_ID = ACTIVE_CONFIG["set_id"]

sum_market_buys = 0
components_data = []

for cid in COMPONENTS:
    d = get_item_data(cid)
    raw_low = d.get("low", 0)
    
    # What the raw market dictates as the next competitive bid
    market_buy_price = (raw_low + 1172) if raw_low > 0 else 0
    sum_market_buys += market_buy_price
    
    # Avoid bidding against ourselves if we already hold the lowest price or higher
    my_active_bids = df[(df["item_id"] == cid) & (df["status"] == "Buying")]
    highest_my_bid = my_active_bids["price"].max() if not my_active_bids.empty else 0
    
    if raw_low > 0:
        if highest_my_bid >= raw_low:
            # We are the current winner (or tied). Protect against ledger typos.
            if highest_my_bid > raw_low * 1.05:
                target_buy = raw_low + 1172
            else:
                target_buy = highest_my_bid
        else:
            # Someone else is lower, or we don't have a bid, so we increment
            target_buy = raw_low + 1172
    else:
        target_buy = 0
    
    components_data.append({
        "id": cid,
        "name": ITEMS[cid],
        "target_buy": target_buy,
        "stale": data_is_stale,
        "raw_low": raw_low
    })

set_data = get_item_data(SET_ID)
raw_high = set_data.get("high", 0)
target_sell = raw_high - 1 if raw_high > 0 else 0
set_stale = data_is_stale

# Net Profit = (Target_Sell * 2% Tax) - Pure Market Buys
net_profit = (target_sell * 0.98) - sum_market_buys
break_even = sum_market_buys / 0.98 if sum_market_buys > 0 else 0

col1, col2 = st.columns([2, 1])
with col1:
    st.metric("Total Bid (Sum)", f"{sum_market_buys:,.0f} GP")
    
col3, col4 = st.columns([2, 1])
with col3:
    st.metric("Target Ask (Set)", f"{target_sell:,.0f} GP")
with col4:
    with st.popover("Sell Set", use_container_width=True):
        st.write("List Set(s) on GE")
        sell_qty = st.number_input("Qty", min_value=1, value=1, step=1, key="sell_set_qty")
        if st.button("Submit Sell Order", key="submit_sell_set", use_container_width=True):
            existing_idx = df_all[(df_all["user_email"] == current_user) & (df_all["item_id"] == SET_ID) & (df_all["status"] == "Selling")].index
            if not existing_idx.empty:
                idx = existing_idx[0]
                df_all.at[idx, "quantity"] += int(sell_qty)
                df_all.at[idx, "price"] = int(target_sell)
            else:
                new_row = {"user_email": current_user, "item_id": SET_ID, "item_name": ITEMS[SET_ID], "price": int(target_sell), "quantity": int(sell_qty), "status": "Selling", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}
                df_all = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
            conn.update(worksheet="Sheet1", data=df_all)
            st.cache_data.clear()
            st.success("Set sell order placed!")
            time.sleep(0.5)
            st.rerun()

profit_color = "green" if net_profit > 0 else "red"
st.markdown(f"<h3 style='text-align: center'>Net Profit: <span style='color:{profit_color}'>{net_profit:,.0f} GP</span></h3>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center'><b>Break-even Set Ask:</b> {break_even:,.0f} GP</p>", unsafe_allow_html=True)

if set_stale:
    st.error("⚠️ Set Sell Price is STALE (> 120s old)")

# Wiki link for the set
st.markdown(f"📈 [View Set Price Chart]({WIKI_LINK}{SET_ID})", unsafe_allow_html=True)

st.divider()

# --- Buy Priority Ranking ---
st.subheader("🏆 Buy Priority")

priority_data = []
for c in components_data:
    ts = fetch_timeseries(c['id'])
    if ts and len(ts) >= 2:
        # Get avg low price from last 24 data points (24 hours at 1h interval)
        recent = ts[-24:] if len(ts) >= 24 else ts
        low_prices = [p.get("avgLowPrice") for p in recent if p.get("avgLowPrice") is not None]
        if low_prices:
            avg_24h = sum(low_prices) / len(low_prices)
            current_low = c['raw_low']
            if avg_24h > 0 and current_low > 0:
                deviation_pct = ((current_low - avg_24h) / avg_24h) * 100
                priority_data.append({
                    "name": c['name'],
                    "id": c['id'],
                    "current_low": current_low,
                    "avg_24h": avg_24h,
                    "deviation": deviation_pct,
                    "target_buy": c['target_buy']
                })

if priority_data:
    # Sort by deviation ascending (most negative = biggest dip = buy first)
    priority_data.sort(key=lambda x: x['deviation'])
    
    for rank, p in enumerate(priority_data, 1):
        dev = p['deviation']
        if dev <= -2:
            icon = "🟢"
            color = "green"
        elif dev <= -0.5:
            icon = "🟡" 
            color = "#DAA520"
        elif dev <= 0.5:
            icon = "⚪"
            color = "gray"
        else:
            icon = "🔴"
            color = "red"
        
        st.markdown(
            f"**{rank}. {icon} {p['name']}** — "
            f"Low: `{p['current_low']:,.0f}` · "
            f"24h Avg: `{p['avg_24h']:,.0f}` · "
            f"<span style='color:{color}'>{dev:+.1f}%</span> "
            f"[📈]({WIKI_LINK}{p['id']})",
            unsafe_allow_html=True
        )
else:
    st.info("Waiting for timeseries data...")

st.divider()

st.subheader("Component Target Bids")
for c in components_data:
    stale_text = " ⚠️ **STALE**" if c["stale"] else ""
    col_item, col_link, col_btn = st.columns([3, 1, 2])
    with col_item:
        st.markdown(f"**{c['name']}**<br/>{c['target_buy']:,.0f} GP{stale_text}", unsafe_allow_html=True)
    with col_link:
        st.markdown(f"[📈]({WIKI_LINK}{c['id']})")
    with col_btn:
        with st.popover("Order", use_container_width=True):
            st.write(f"Buy {c['name']}")
            comp_qty = st.number_input("Qty", min_value=1, value=1, step=1, key=f"buy_qty_{c['id']}")
            if st.button("Submit Buy Order", key=f"buy_{c['id']}", use_container_width=True):
                existing_idx = df_all[(df_all["user_email"] == current_user) & (df_all["item_id"] == c['id']) & (df_all["status"] == "Buying")].index
                if not existing_idx.empty:
                    idx = existing_idx[0]
                    df_all.at[idx, "quantity"] += int(comp_qty)
                    df_all.at[idx, "price"] = int(c['target_buy'])
                else:
                    new_row = {"user_email": current_user, "item_id": int(c['id']), "item_name": c['name'], "price": int(c['target_buy']), "quantity": int(comp_qty), "status": "Buying", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}
                    df_all = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
                conn.update(worksheet="Sheet1", data=df_all)
                st.cache_data.clear()
                st.success(f"Ordered {comp_qty}x {c['name']}")
                time.sleep(0.5)
                st.rerun()

st.divider()

# --- Ledger & Inventory Management ---
st.header("Ledger & Inventory")

with st.expander("Log Transaction", expanded=False):
    with st.form("log_tx"):
        tx_item = st.selectbox("Item", list(ITEMS.values()))
        tx_price_raw = st.text_input("Actual Price (GP)", value="0")
        tx_quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
        tx_status = st.selectbox("Status", ["Buying", "Owned", "Sold"])
        
        if st.form_submit_button("Log Entry", use_container_width=True):
            item_id = [k for k, v in ITEMS.items() if v == tx_item][0]
            new_row = {
                "user_email": current_user,
                "item_id": int(item_id),
                "item_name": tx_item,
                "price": int(parse_gp_input(tx_price_raw)),
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

st.subheader("Active Orders")

target_prices = {c['id']: c['target_buy'] for c in components_data}
target_prices[SET_ID] = target_sell

active_df = df[df["status"].isin(["Buying", "Selling"])]
if not active_df.empty:
    for idx, row in active_df.iterrows():
        with st.container(border=True):
            target_p = target_prices.get(row['item_id'], 0)
            status_color = "green" if row["status"] == "Buying" else "red"
            warning_icon = ""
            
            # Check cooldown state from the sheet
            cooldown_val = row.get("cooldown") if "cooldown" in row.index else ""
            is_cooldown = str(cooldown_val).strip().lower() == "true" if not pd.isna(cooldown_val) else False
            
            if is_cooldown:
                status_color = "#3498db"
                warning_icon = "🧊 *(Cooldown — Price Squeezed)*"
            elif row["status"] == "Buying" and row["price"] < target_p:
                status_color = "orange"
                warning_icon = "⚠️ *(Outbid)*"
            elif row["status"] == "Selling" and row["price"] > target_p:
                status_color = "orange"
                warning_icon = "⚠️ *(Undercut)*"
                
            st.markdown(f"**<span style='color:{status_color}'>{row['status']}</span> {row['item_name']} {warning_icon}** &mdash; {row['quantity']}x @ {row['price']:,.0f} GP", unsafe_allow_html=True)
            colA, colB, colC = st.columns(3)
            with colA:
                with st.popover("✅ Fill", use_container_width=True):
                    max_q = int(row['quantity'])
                    fill_qty = st.number_input("Qty to Fill", min_value=1, max_value=max_q, value=max_q, step=1, key=f"fillq_{idx}")
                    if st.button("Confirm Fill", key=f"fillbtn_{idx}", use_container_width=True):
                        # Deduct from active
                        if fill_qty == max_q:
                            df_all = df_all.drop(index=idx)
                        else:
                            df_all.at[idx, "quantity"] = max_q - fill_qty
                            
                        # Add to filled
                        new_status = "Owned" if row["status"] == "Buying" else "Sold"
                        filled_row = row.copy()
                        filled_row["quantity"] = fill_qty
                        filled_row["status"] = new_status
                        filled_row["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        df_all = pd.concat([df_all, pd.DataFrame([filled_row])], ignore_index=True)
                        
                        conn.update(worksheet="Sheet1", data=df_all)
                        st.cache_data.clear()
                        st.rerun()
            with colB:
                def set_reset_state(i, p):
                    st.session_state[f"prc_{i}"] = f"{int(p):,}"
                    
                with st.popover("✏️ Edit", use_container_width=True):
                    new_qty = st.number_input("Qty", value=int(row["quantity"]), min_value=1, step=1, key=f"qty_{idx}")
                    new_price_raw = st.text_input("Price (GP)", value=f"{row['price']:,.0f}", key=f"prc_{idx}")
                    
                    target_p = target_prices.get(row['item_id'], 0)
                    if target_p > 0:
                        if st.button(f"Reset to {target_p:,}", key=f"reset_{idx}", on_click=set_reset_state, args=(idx, target_p), use_container_width=True):
                            df_all.at[idx, "price"] = int(target_p)
                            conn.update(worksheet="Sheet1", data=df_all)
                            st.cache_data.clear()
                            st.rerun()

                    if st.button("Update", key=f"upd_{idx}", use_container_width=True):
                        df_all.at[idx, "quantity"] = int(new_qty)
                        df_all.at[idx, "price"] = int(parse_gp_input(new_price_raw))
                        conn.update(worksheet="Sheet1", data=df_all)
                        st.cache_data.clear()
                        st.rerun()
            with colC:
                if st.button("❌ Drop", key=f"drop_{idx}", use_container_width=True):
                    df_all = df_all.drop(index=idx)
                    conn.update(worksheet="Sheet1", data=df_all)
                    st.cache_data.clear()
                    st.rerun()
else:
    st.info("No active orders.")

st.divider()

st.subheader("Inventory Work-in-Progress")
if not df.empty:
    # Inventory only counts items we officially own
    incoming_df = df[df["status"] == "Owned"]
    incoming_counts = incoming_df.groupby("item_id")["quantity"].sum().to_dict()
    
    sold_df = df[df["status"] == "Sold"]
    sold_counts = sold_df.groupby("item_id")["quantity"].sum().to_dict()
    
    current_inventory = {}
    for cid in COMPONENTS:
        # A set is functionally 1 of each component. Combine explicit component buys + explicit set buys.
        owned = incoming_counts.get(cid, 0) + incoming_counts.get(SET_ID, 0)
        sold = sold_counts.get(cid, 0) + sold_counts.get(SET_ID, 0)
        current_inventory[cid] = owned - sold
        
    comp_counts = [current_inventory.get(cid, 0) for cid in COMPONENTS]
    assembled_sets = min(comp_counts) if comp_counts else 0
    total_sets = assembled_sets
    loose_inventory = {cid: current_inventory.get(cid, 0) - assembled_sets for cid in COMPONENTS}
    
    if total_sets == 0 and not any(qty > 0 for qty in loose_inventory.values()):
        st.info("No pieces owned currently.")
    else:
        st.markdown(f"**Current Inventory:** {total_sets} full set(s)")
        loose_items_list = [f"{qty}x {ITEMS[cid]}" for cid, qty in loose_inventory.items() if qty > 0]
        if loose_items_list:
            st.markdown(f"**Loose pieces:** {', '.join(loose_items_list)}")
        
        missing = [cid for cid in COMPONENTS if loose_inventory.get(cid, 0) < 1]
        if 0 < len(missing) < len(COMPONENTS):
            st.write("You need these pieces to form another set:")
            for m_id in missing:
                c_name = ITEMS[m_id]
                live_low = next((c['raw_low'] for c in components_data if c['id'] == m_id), 0)
                st.write(f"- 🔴 **{c_name}** (Current Low: {live_low:,.0f} GP)")
else:
    st.info("No pieces owned currently.")

st.divider()

st.subheader("History & Profit Metrics")
if not df.empty:
    overall_total_revenue = 0
    overall_total_cogs = 0
    overall_inventory_cost = 0

    profit_breakdown = []
    
    # Pre-process owned rows for Exact FIFO universally
    owned_df = df[df["status"] == "Owned"].copy()
    owned_df["timestamp"] = pd.to_datetime(owned_df["timestamp"], errors="coerce")
    owned_df = owned_df.sort_values("timestamp")
    
    for s_name, cfg in SETS_CONFIG.items():
        s_id = cfg["set_id"]
        c_ids = [c["id"] for c in cfg["components"]]
        
        sold_mask = (df["status"] == "Sold") & (df["item_id"].isin([s_id] + c_ids))
        total_revenue = (df[sold_mask]["price"] * df[sold_mask]["quantity"] * 0.98).sum()
        
        sold_counts = df[sold_mask].groupby("item_id")["quantity"].sum().to_dict()
        
        set_owned_df = owned_df[owned_df["item_id"].isin([s_id] + c_ids)]
        
        prices_lists = {cid: [] for cid in c_ids}
        
        for _, row in set_owned_df.iterrows():
            r_id = row["item_id"]
            qty = int(row["quantity"])
            price = float(row["price"])
            
            if r_id == s_id:
                comp_price = price / float(len(c_ids))
                for cid in c_ids:
                    prices_lists[cid].extend([comp_price] * qty)
            elif r_id in c_ids:
                prices_lists[r_id].extend([price] * qty)
                
        set_cogs = 0
        set_inv_cost = 0
        
        for cid in c_ids:
            n_sold = int(sold_counts.get(cid, 0) + sold_counts.get(s_id, 0))
            prices = prices_lists[cid]
            cogs = sum(prices[:n_sold])
            inv = sum(prices[n_sold:])
            set_cogs += cogs
            set_inv_cost += inv
            
        realized_profit = total_revenue - set_cogs
        overall_total_revenue += total_revenue
        overall_total_cogs += set_cogs
        overall_inventory_cost += set_inv_cost
        
        if total_revenue > 0 or set_inv_cost > 0:
            profit_breakdown.append({
                "Set": s_name,
                "Realized Profit": realized_profit,
                "Unsold Value": set_inv_cost
            })
            
    overall_realized_profit = overall_total_revenue - overall_total_cogs

    colA, colB = st.columns(2)
    with colA:
        r_color = "green" if overall_realized_profit >= 0 else "red"
        st.markdown(f"**Realized Profit (All Sets):**<br><span style='color:{r_color}; font-size:20px'>{overall_realized_profit:,.0f} GP</span>", unsafe_allow_html=True)
    with colB:
        st.markdown(f"**Unsold Inventory (All Sets):**<br><span style='color:inherit; font-size:20px'>{overall_inventory_cost:,.0f} GP</span>", unsafe_allow_html=True)
    
    if profit_breakdown:
        breakdown_df = pd.DataFrame(profit_breakdown)
        breakdown_df["Realized Profit"] = breakdown_df["Realized Profit"].apply(lambda x: f"{x:,.0f} GP")
        breakdown_df["Unsold Value"] = breakdown_df["Unsold Value"].apply(lambda x: f"{x:,.0f} GP")
        st.dataframe(breakdown_df, hide_index=True, use_container_width=True)
        
    st.write("") # spacing
    with st.expander("View Ledger Logs", expanded=False):
        for i, row in df.sort_values(by="timestamp", ascending=False).head(20).iterrows():
            st.write(f"`{row['timestamp'][:16]}` | **{row['item_name']}** | {row['quantity']}x @ {row['price']:,.0f} GP [{row['status']}]")
else:
    st.write("No transaction history available.")


