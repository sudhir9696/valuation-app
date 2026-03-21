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

# --- SIDEBAR: INPUTS ---
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
        "compCount": 25, # Higher count to allow for filtering
        "daysOld": 365
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# --- MAIN PAGE ---
if run_btn:
    with st.spinner("Analyzing Market Data..."):
        data = get_valuation_data(search_radius, address, city)
        
        # 1. GET SUBJECT DETAILS (No more manual tax entry!)
        subject = data # The AVM endpoint returns subject attributes automatically
        subject_beds = subject.get('bedrooms', 0)
        subject_tax = subject.get('taxAmt', 0)
        subject_basement = "Yes" if subject.get('basementType') else "No"
        
        all_comps = data.get('comparables', [])
        
        # 2. FILTER: Exclude address + Strictly look at Same Bedrooms if possible
        sold_comps = [c for c in all_comps if exclude_addr.lower() not in c.get('formattedAddress', '').lower()]
        
        # 3. DISPLAY METRICS
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Subject Beds", subject_beds)
        col2.metric("Annual Tax", f"${subject_tax:,.0f}" if subject_tax else "N/A")
        col3.metric("Basement", subject_basement)
        col4.metric("Market Adj", f"{mkt_adj*100}%")

        # 4. TABLE: Include Basement & Bed Comparison
        st.subheader("📍 Detailed Comparable Sales (Filtered)")
        comp_list = []
        for c in sold_comps:
            p, s = c.get('price', 0), c.get('squareFootage', 1)
            comp_list.append({
                "Address": c.get('formattedAddress'),
                "Beds": c.get('bedrooms'),
                "Basement": "Yes" if c.get('basementType') else "No",
                "Sold Date": c.get('lastSeenDate', "")[:10],
                "Price": p,
                "$/SqFt": round(p/s, 2) if s > 0 else 0,
                "Dist": round(c.get('distance', 0), 2)
            })
        
        if comp_list:
            df = pd.DataFrame(comp_list)
            # Apply color to help Swathi see same-bedroom matches
            def highlight_beds(val):
                return 'background-color: #2e7d32' if val == subject_beds else ''
            
            df_disp = df.copy()
            df_disp['Price'] = df_disp['Price'].map('${:,.0f}'.format)
            st.dataframe(df_disp.style.applymap(highlight_beds, subset=['Beds']), use_container_width=True)
        
        # 5. AI ANALYSIS: Focused on Beds and Basement
        st.subheader("🧠 Strategic AI Analysis")
        client = anthropic.Anthropic(api_key=AI_KEY) 
        
        prompt = f"""
        Subject: {address}. Beds: {subject_beds}. Basement: {subject_basement}.
        Annual Tax: ${subject_tax}. Market Adj: {mkt_adj*100}%.
        
        COMPS: {json.dumps(sold_comps)}
        
        STRATEGIC INSTRUCTIONS:
        1. PRIORITIZE: Give 2x weight to comps with exactly {subject_beds} bedrooms.
        2. BASEMENT VALUE: Compare the subject's basement ({subject_basement}) against the comps. 
           If the subject has a basement but a comp doesn't, justify a higher price.
        3. OUTPUT: Provide a 'Strike Price', 'Floor Offer', and 3-point rationale.
        4. FORMATTING: Use ### Headers and ensure spaces around **bold** text.
        """
        
        message = client.messages.create(
            model="claude-3-5-sonnet-latest", 
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        st.markdown("---")
        st.markdown(message.content[0].text)