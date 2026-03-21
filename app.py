import streamlit as st
import requests
import anthropic
import json
import pandas as pd

# --- APP CONFIG ---
st.set_page_config(page_title="Swathi's Market Intelligence", layout="wide")
st.title("🏡 Swathi's Real Estate Valuation Dashboard")

# --- SECURE KEYS ---
RENT_KEY = st.secrets["RENTCAST_API_KEY"]
AI_KEY = st.secrets["CLAUDE_API_KEY"]

# --- SIDEBAR ---
with st.sidebar:
    st.header("Property Config")
    address = st.text_input("Street Address", value="6089 Grand Loop Rd")
    city = st.text_input("City, State", value="Sugar Hill, GA")
    
    st.divider()
    st.header("Search Parameters")
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 1.5, 0.1)
    exclude_addr = st.text_input("Exclude Address?", placeholder="e.g., 4718")
    
    st.divider()
    st.header("Market Controls")
    mkt_adj = st.slider("Market Adjustment (%)", -10, 15, -3) / 100
    cond_score = st.select_slider("Condition (1-5)", options=[1,2,3,4,5], value=4)
    
    run_btn = st.button("Generate Valuation Report", type="primary")

# --- DATA FETCHING ---
@st.cache_data(ttl=3600)
def get_data(addr, cty, radius):
    headers = {"X-Api-Key": RENT_KEY, "Accept": "application/json"}
    full_addr = f"{addr}, {cty}"
    
    # 1. Fetch Valuation & Comps
    avm_url = "https://api.rentcast.io/v1/avm/value"
    avm_params = {"address": full_addr, "propertyType": "Single Family", "radius": radius, "compCount": 25}
    avm_res = requests.get(avm_url, headers=headers, params=avm_params).json()
    
    # 2. Fallback: Fetch Property Details (to fix the 0 Beds/Tax issue)
    prop_url = "https://api.rentcast.io/v1/properties"
    prop_params = {"address": full_addr}
    prop_res = requests.get(prop_url, headers=headers, params=prop_params).json()
    
    # Merge them: priority to property details for accuracy
    subject_details = prop_res[0] if isinstance(prop_res, list) and len(prop_res) > 0 else {}
    return avm_res, subject_details

# --- MAIN PAGE ---
if run_btn:
    with st.spinner("Synchronizing Data..."):
        avm_data, prop_info = get_data(address, city, search_radius)
        
        # ✅ DATA EXTRACTION (Checks multiple layers)
        subject_beds = prop_info.get('bedrooms') or avm_data.get('bedrooms') or 0
        subject_tax = prop_info.get('taxAmt') or avm_data.get('taxAmt') or 0
        
        # Basement Check
        b_val = prop_info.get('basementType') or avm_data.get('basementType') or ""
        subject_basement = "Yes" if b_val and str(b_val).lower() != "none" else "No"
        
        all_comps = avm_data.get('comparables', [])
        sold_comps = [c for c in all_comps if exclude_addr.lower() not in c.get('formattedAddress', '').lower()]
        
        # 📊 Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Subject Beds", subject_beds)
        col2.metric("Annual Tax", f"${subject_tax:,.0f}" if subject_tax else "N/A")
        col3.metric("Basement", subject_basement)
        col4.metric("Market Adj", f"{mkt_adj*100}%")

        # 📍 Table
        st.subheader("📍 Detailed Comparable Sales")
        comp_list = []
        for c in sold_comps:
            p, s = c.get('price', 0), c.get('squareFootage', 1)
            comp_list.append({
                "Address": c.get('formattedAddress'),
                "Beds": c.get('bedrooms', 0),
                "Basement": "Yes" if c.get('basementType') and str(c.get('basementType')).lower() != "none" else "No",
                "Price": p,
                "$/SqFt": round(p/s, 2) if s > 0 else 0,
                "Dist (Mi)": round(c.get('distance', 0), 2)
            })
        
        if comp_list:
            df = pd.DataFrame(comp_list)
            # Highlight matching bedrooms
            st.dataframe(df.style.applymap(lambda x: 'background-color: #1e4620' if x == subject_beds else '', subset=['Beds']), use_container_width=True)
        
        # 🧠 AI
        st.subheader("🧠 Strategic AI Analysis")
        client = anthropic.Anthropic(api_key=AI_KEY)
        prompt = f"Subject: {address}. Beds: {subject_beds}. Basement: {subject_basement}. Tax: {subject_tax}. Comps: {json.dumps(sold_comps)}. Provide strike price, floor offer, and 3-point rationale using ### headers."
        
        message = client.messages.create(model="claude-sonnet-4-6", max_tokens=1024, messages=[{"role": "user", "content": prompt}])
        st.markdown("---")
        st.markdown(message.content[0].text)