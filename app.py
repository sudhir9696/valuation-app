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

# --- VALUATION LOGIC ---
@st.cache_data(ttl=3600)
def get_valuation_data(radius_miles, addr, cty):
    headers = {"X-Api-Key": RENT_KEY, "Accept": "application/json"}
    url = "https://api.rentcast.io/v1/avm/value"
    params = {
        "address": f"{addr}, {cty}",
        "propertyType": "Single Family",
        "radius": radius_miles, 
        "compCount": 25,
        "daysOld": 365
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# --- MAIN PAGE ---
if run_btn:
    with st.spinner("Fetching Real-Time Market Data..."):
        data = get_valuation_data(search_radius, address, city)
        
        # ✅ FIX: RentCast often nests attributes inside 'property' or 'propertyData'
        # We try multiple paths to find the data so it's not '0'
        subject_beds = data.get('bedrooms') or data.get('propertyData', {}).get('bedrooms', 0)
        subject_tax = data.get('taxAmt') or data.get('propertyData', {}).get('taxAmt', 0)
        
        # Basement logic fix
        b_type = data.get('basementType') or data.get('propertyData', {}).get('basementType')
        subject_basement = "Yes" if b_type and b_type.lower() != "none" else "No"
        
        all_comps = data.get('comparables', [])
        sold_comps = [c for c in all_comps if exclude_addr.lower() not in c.get('formattedAddress', '').lower()]
        
        # 📊 Display Top-Level Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Subject Beds", subject_beds)
        col2.metric("Annual Tax", f"${subject_tax:,.0f}" if subject_tax else "N/A")
        col3.metric("Basement", subject_basement)
        col4.metric("Market Adj", f"{mkt_adj*100}%")

        # 📍 Comparison Table
        st.subheader("📍 Detailed Comparable Sales (Filtered)")
        comp_list = []
        for c in sold_comps:
            p = c.get('price', 0)
            s = c.get('squareFootage', 1)
            comp_list.append({
                "Address": c.get('formattedAddress'),
                "Beds": c.get('bedrooms', 0),
                "Basement": "Yes" if c.get('basementType') and c.get('basementType').lower() != "none" else "No",
                "Price": p,
                "$/SqFt": round(p/s, 2) if s > 0 else 0,
                "Dist (Mi)": round(c.get('distance', 0), 2)
            })
        
        if comp_list:
            df = pd.DataFrame(comp_list)
            # Apply color to help Swathi see same-bedroom matches
            def highlight_beds(val):
                return 'background-color: #1e4620; color: white;' if val == subject_beds else ''
            
            df_disp = df.copy()
            df_disp['Price'] = df_disp['Price'].map('${:,.0f}'.format)
            st.dataframe(df_disp.style.applymap(highlight_beds, subset=['Beds']), use_container_width=True)
        else:
            st.warning("No comparable sales found. Try increasing the search radius.")

        # 🧠 AI Analysis with Updated Rules
        st.subheader("🧠 Strategic AI Analysis")
        client = anthropic.Anthropic(api_key=AI_KEY) 
        
        prompt = f"""
        Subject: {address}. Beds: {subject_beds}. Basement: {subject_basement}.
        Annual Tax: ${subject_tax}. Market Adj: {mkt_adj*100}%.
        
        COMPS: {json.dumps(sold_comps)}
        
        STRATEGIC INSTRUCTIONS:
        1. WEIGHTING: Prioritize comps with exactly {subject_beds} bedrooms.
        2. BASEMENT: Adjust value based on basement status ({subject_basement}).
        3. OUTPUT: Strike Price, Floor Offer, and 3-point rationale.
        4. FORMATTING: Use ### Headers and ensure spaces around **bold** markers.
        """
        
        message = client.messages.create(
            model="claude-sonnet-4-6", 
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        st.markdown("---")
        st.markdown(message.content[0].text)