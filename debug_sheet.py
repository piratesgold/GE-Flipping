import pandas as pd, streamlit as st
from streamlit_gsheets import GSheetsConnection

conn = st.connection('gsheets', type=GSheetsConnection)
df = conn.read(worksheet='Sheet1', ttl=0)
print('--- Sheet Snapshot ---')
print(df[['item_name','status','price','quantity','cooldown','last_known_high','last_alert_price']].to_string(index=False))
