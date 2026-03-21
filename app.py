import streamlit as st
import requests
import anthropic
import json
import pandas as pd

# --- APP CONFIG ---
st.set_page_config(page_title="Swathi's Market Intelligence", layout="wide")
st.title("🏡 Swathi's Real Estate Valuation Dashboard")

# --- SECURE KEYS ---
# Pulling from Streamlit Cloud "Advanced Settings" > Secrets
RENT_KEY = st.secrets["RENTCAST_API_KEY"]
AI_KEY = st.secrets["CLAUDE_API_KEY"]

# --- SIDEBAR: USER INPUTS ---
with st.sidebar:
    st.header("Property Config")
    address = st.text_input("Street Address", value="6089 Grand Loop Rd")
    city = st.text_input("City, State", value="Sugar Hill, GA")
    zip_code = st.text_input("Zip Code", value="30518")
    
    st.divider()
    st.header("Search Parameters")
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 1.5, 0.1)
    exclude_addr = st.text_input("Exclude Address?", placeholder="e.g., 4718")
    
    st.divider()
    st.header("Market Controls")
    mkt_adj = st.slider("Market Adjustment (%)", -10, 15, -3) / 100
    cond_score = st.select_slider("Condition (1-5)", options=[1,2,3,4,5], value=4)
    
    run_btn = st.button("Generate Valuation Report", type="primary")

# --- DATA FETCHING (The "Soft Filter" Logic) ---
@st.cache_data(ttl=3600)
def get_market_data(addr, cty, zp, radius):
    headers = {"X-Api-Key": RENT_KEY, "Accept": "application/json"}
    full_addr = f"{addr}, {cty}, {zp}"
    
    # 1. Fetch Subject Property Details (The "Source of Truth")
    prop_url = "https://api.rentcast.io/v1/properties"
    prop_params = {"address": full_addr}
    prop_res = requests.get(prop_url, headers=headers, params=prop_params).json()
    subject_details = prop_res[0] if isinstance(prop_res, list) and len(prop_res) > 0 else {}
    
    # 2. Fetch Valuation & Comps (The "Wide Net")
    # We do NOT filter for beds/basement here so we always get results
    avm_url = "https://api.rentcast.io/v1/avm/value"
    avm_params = {
        "address": full_addr,
        "propertyType": "Single Family",
        "radius": radius,
        "compCount": 25
    }
    avm_res = requests.get(avm_url, headers=headers, params=avm_params).json()
    
    return avm_res, subject_details

# --- MAIN PAGE: DATA DISPLAY ---
if run_btn:
    with st.spinner("Analyzing Market Data..."):
        avm_data, prop_info = get_market_data(address, city, zip_code, search_radius)
        
        # ✅ DATA EXTRACTION (Priority to prop_info)
        subject_beds = prop_info.get('bedrooms') or avm_data.get('bedrooms') or 0
        subject_tax = prop_info.get('taxAmt') or avm_data.get('taxAmt') or 0
        
        # Basement Check
        b_type = prop_info.get('basementType') or avm_data.get('basementType') or ""
        subject_basement = "Yes" if b_type and str(b_type).lower() != "none" else "No"
        
        # Metrics Display
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Subject Beds", subject_beds)
        col2.metric("Annual Tax", f"${subject_tax:,.0f}" if subject_tax else "N/A")
        col3.metric("Basement", subject_basement)
        col4.metric("Market Adj", f"{mkt_adj*100}%")

        # Table Display
        st.subheader("📍 Detailed Comparable Sales (Filtered)")
        all_comps = avm_data.get('comparables', [])
        
        # Apply exclusions if provided
        sold_comps = [c for c in all_comps if exclude_addr.lower() not in c.get('formattedAddress', '').lower()]
        
        if sold_comps:
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
            
            df = pd.DataFrame(comp_list)
            df_disp = df.copy()
            df_disp['Price'] = df_disp['Price'].map('${:,.0f}'.format)
            
            # ✅ STYLING: Highlight Same Bedrooms in Green
            def highlight_beds(val):
                return 'background-color: #1e4620; color: white;' if val == subject_beds else ''
            
            st.dataframe(df_disp.style.applymap(highlight_beds, subset=['Beds']), width='stretch')
        else:
            st.warning("No comps found. Try increasing the search radius in the sidebar.")

        # AI Analysis
        st.subheader("🧠 Strategic AI Analysis")
        client = anthropic.Anthropic(api_key=AI_KEY)
        
        prompt = f"""
        Subject Property: {address}. 
        Subject Details: {subject_beds} Bedrooms, Basement: {subject_basement}.
        Market Adjustment: {mkt_adj*100}%. Condition: {cond_score}/5.
        
        COMPARABLE DATA (JSON): {json.dumps(sold_comps)}
        
        ANALYSIS RULES:
        1. PRIORITIZE matches with exactly {subject_beds} bedrooms.
        2. BASEMENT ADJUSTMENT: If subject has a basement but comp doesn't, add value.
        3. OUTPUT: Provide a Suggested 'Strike Price', 'Floor Offer', and 3 detailed rationale points.
        4. FORMATTING: Use ### Headers and ensure spaces around **bold** prices.
        """
        
        # ✅ Using your specified model name
        message = client.messages.create(
            model="claude-sonnet-4-6", 
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        st.markdown("---")
        st.markdown(message.content[0].text)