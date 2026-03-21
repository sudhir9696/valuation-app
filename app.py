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
    address = st.text_input("Street Address", value="2275 Lake Cove Ct")
    city = st.text_input("City, State", value="Buford, GA")
    zip_code = st.text_input("Zip Code", value="30519")
    
    st.divider()
    st.header("Search Parameters")
    # Setting default to 2.0 miles to ensure we hit enough houses
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 2.0, 0.1)
    exclude_addr = st.text_input("Exclude Address?", placeholder="e.g., 4718")
    
    st.divider()
    run_btn = st.button("Generate Valuation Report", type="primary")

# --- DATA FETCHING (Simplified & Reliable) ---
@st.cache_data(ttl=3600)
def get_market_data(addr, cty, zp, radius):
    headers = {"X-Api-Key": RENT_KEY, "Accept": "application/json"}
    full_addr = f"{addr}, {cty}, {zp}"
    
    # 1. Get Subject Details
    prop_url = "https://api.rentcast.io/v1/properties"
    prop_params = {"address": full_addr}
    prop_res = requests.get(prop_url, headers=headers, params=prop_params).json()
    subject = prop_res[0] if isinstance(prop_res, list) and len(prop_res) > 0 else {}
    
    # 2. Get Comps (No restrictive filters here so we ALWAYS get data)
    avm_url = "https://api.rentcast.io/v1/avm/value"
    avm_params = {
        "address": full_addr,
        "propertyType": "Single Family",
        "radius": radius,
        "compCount": 25
    }
    avm_res = requests.get(avm_url, headers=headers, params=avm_params).json()
    
    return avm_res, subject

if run_btn:
    with st.spinner("Fetching Data..."):
        avm_data, prop_info = get_market_data(address, city, zip_code, search_radius)
        
        # 📊 Metrics Extraction
        # We check both API responses to make sure we don't show 0
        subject_beds = prop_info.get('bedrooms') or avm_data.get('bedrooms') or 0
        subject_tax = prop_info.get('taxAmt') or avm_data.get('taxAmt') or 0
        b_type = prop_info.get('basementType') or avm_data.get('basementType') or ""
        subject_basement = "Yes" if b_type and str(b_type).lower() != "none" else "No"
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Subject Beds", subject_beds)
        col2.metric("Annual Tax", f"${subject_tax:,.0f}" if subject_tax else "N/A")
        col3.metric("Basement", subject_basement)

        # 📍 Table Logic
        st.subheader("📍 Recent Comparable Sales")
        all_comps = avm_data.get('comparables', [])
        sold_comps = [c for c in all_comps if exclude_addr.lower() not in c.get('formattedAddress', '').lower()]
        
        if sold_comps:
            comp_list = []
            for c in sold_comps:
                comp_list.append({
                    "Address": c.get('formattedAddress'),
                    "Beds": c.get('bedrooms', 0),
                    "Basement": "Yes" if c.get('basementType') and str(c.get('basementType')).lower() != "none" else "No",
                    "Price": c.get('price', 0),
                    "Dist (Mi)": round(c.get('distance', 0), 2)
                })
            df = pd.DataFrame(comp_list)
            
            # Format Price
            df['Price'] = df['Price'].map('${:,.0f}'.format)
            
            # Highlight same bedrooms
            st.dataframe(df.style.applymap(lambda x: 'background-color: #1e4620' if x == subject_beds else '', subset=['Beds']), width='stretch')
        else:
            st.warning("No comps found. Try increasing the search radius.")

        # 🧠 AI Analysis
        st.subheader("🧠 Strategic AI Analysis")
        client = anthropic.Anthropic(api_key=AI_KEY)
        
        prompt = f"Subject: {address}. Beds: {subject_beds}. Basement: {subject_basement}. Comps: {json.dumps(sold_comps)}. Suggest strike price and rationale."
        
        # Using the specific model you requested
        message = client.messages.create(
            model="claude-sonnet-4-6", 
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        st.markdown(message.content[0].text)