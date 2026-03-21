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
    # Defaulting to 2.0 miles ensures we find enough suburban comps
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 2.0, 0.1)
    exclude_addr = st.text_input("Exclude Address?", placeholder="e.g., 4718")
    
    st.divider()
    st.header("Market Controls")
    mkt_adj = st.slider("Market Adjustment (%)", -10, 15, -3) / 100
    
    run_btn = st.button("Generate Valuation Report", type="primary")

# --- DATA FETCHING (Reliable Logic) ---
@st.cache_data(ttl=3600)
def get_market_data(addr, cty, zp, radius):
    headers = {"X-Api-Key": RENT_KEY, "Accept": "application/json"}
    full_addr = f"{addr}, {cty}, {zp}"
    
    # 1. Get Subject Details directly from RentCast
    prop_url = "https://api.rentcast.io/v1/properties"
    prop_params = {"address": full_addr}
    prop_res = requests.get(prop_url, headers=headers, params=prop_params).json()
    subject = prop_res[0] if isinstance(prop_res, list) and len(prop_res) > 0 else {}
    
    # 2. Get Valuation & Comps (No rigid filters here to ensure results)
    avm_url = "https://api.rentcast.io/v1/avm/value"
    avm_params = {
        "address": full_addr,
        "propertyType": "Single Family",
        "radius": radius,
        "compCount": 25
    }
    avm_res = requests.get(avm_url, headers=headers, params=avm_params).json()
    
    return avm_res, subject

# --- MAIN PAGE ---
if run_btn:
    with st.spinner("Locking on to market data..."):
        avm_data, prop_info = get_market_data(address, city, zip_code, search_radius)
        
        # Data Extraction with fallbacks
        subject_beds = prop_info.get('bedrooms') or avm_data.get('bedrooms') or 0
        subject_tax = prop_info.get('taxAmt') or avm_data.get('taxAmt') or 0
        b_type = prop_info.get('basementType') or avm_data.get('basementType') or ""
        subject_basement = "Yes" if b_type and str(b_type).lower() != "none" else "No"
        
        # Top Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Subject Beds", subject_beds)
        col2.metric("Annual Tax", f"${subject_tax:,.0f}" if subject_tax else "N/A")
        col3.metric("Basement", subject_basement)
        col4.metric("Market Adj", f"{mkt_adj*100}%")

        # Comps Table
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
                    "$/SqFt": round(c.get('price', 0) / c.get('squareFootage', 1), 2),
                    "Dist (Mi)": round(c.get('distance', 0), 2)
                })
            df = pd.DataFrame(comp_list)
            df_disp = df.copy()
            df_disp['Price'] = df_disp['Price'].map('${:,.0f}'.format)
            
            # Highlight matching bedrooms in Dark Green
            def highlight_match(val):
                return 'background-color: #1e4620; color: white;' if val == subject_beds else ''
            
            st.dataframe(df_disp.style.applymap(highlight_match, subset=['Beds']), width='stretch')
        else:
            st.warning("No nearby sales found. Try increasing the search radius.")

        # AI Analysis
        st.subheader("🧠 Strategic AI Analysis")
        client = anthropic.Anthropic(api_key=AI_KEY)
        
        prompt = f"""
        Subject: {address}. {subject_beds} Beds, Basement: {subject_basement}.
        Market Adj: {mkt_adj*100}%.
        COMPS: {json.dumps(sold_comps)}
        
        Suggest a Strike Price, Floor Offer, and 3-point rationale. 
        Use ### headers and **bold** prices.
        """
        
        # Updated to your model name
        message = client.messages.create(
            model="claude-sonnet-4-6", 
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        st.markdown("---")
        st.markdown(message.content[0].text)