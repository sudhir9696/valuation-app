import streamlit as st
import requests
import anthropic
import json
import pandas as pd

# --- APP CONFIG ---
st.set_page_config(page_title="Swathi's Market Intelligence", layout="wide")
st.title("🏡 Swathi's Real Estate Valuation Dashboard")

# --- SECURE KEYS FROM STREAMLIT SECRETS ---
# This ensures GitHub never sees your real keys
RENT_KEY = st.secrets["RENTCAST_API_KEY"]
AI_KEY = st.secrets["CLAUDE_API_KEY"]

# --- SIDEBAR: INPUTS ---
with st.sidebar:
    st.header("Property Config")
    address = st.text_input("Street Address", value="6089 Grand Loop Rd")
    city = st.text_input("City, State", value="Sugar Hill, GA")
    tax_val = st.number_input("Tax Assessment ($)", value=302120)
    
    st.divider()
    st.header("Search Parameters")
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 1.5, 0.1)
    exclude_addr = st.text_input("Exclude Address?", value="", placeholder="e.g., 4718")
    
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
    params = {"address": f"{addr}, {cty}", "propertyType": "Single Family", "radius": radius_miles, "compCount": 20, "daysOld": 365}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# --- MAIN PAGE: REPORTING ---
if run_btn:
    with st.spinner("Analyzing Market Data via RentCast..."):
        data = get_valuation_data(search_radius, address, city)
        all_comps = data.get('comparables', [])
        
        # Generic Exclusion Filter
        if exclude_addr:
            sold_comps = [c for c in all_comps if exclude_addr.lower() not in c.get('formattedAddress', '').lower()]
        else:
            sold_comps = all_comps
        
        tax_baseline = tax_val / 0.4

        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Tax Baseline (FMV)", f"${tax_baseline:,.0f}")
        col2.metric("Market Sentiment", "Buyer's Market" if mkt_adj < 0 else "Seller's Market")
        col3.metric("Adjustment", f"{mkt_adj*100}%")

        # Table Display
        st.subheader("📍 Recent Comparable Sales")
        if sold_comps:
            comp_data = []
            for c in sold_comps:
                p, s = c.get('price', 0), c.get('squareFootage', 1)
                comp_data.append({
                    "Address": c.get('formattedAddress'),
                    "Sold Date": c.get('lastSeenDate', "")[:10],
                    "Price": p,
                    "$/SqFt": round(p/s, 2) if s > 0 else 0,
                    "Dist (Mi)": round(c.get('distance', 0), 2)
                })
            df = pd.DataFrame(comp_data)
            df_disp = df.copy()
            df_disp['Price'] = df_disp['Price'].map('${:,.0f}'.format)
            st.dataframe(df_disp, use_container_width=True)
        else:
            st.warning("No comps found.")

        # AI Analysis with STRICT FORMATTING
        st.subheader("🧠 Strategic AI Analysis")
        client = anthropic.Anthropic(api_key=AI_KEY) 
        
        prompt = f"""
        Subject: {address}. Tax Baseline: ${tax_baseline:,.0f}.
        Market Adj: {mkt_adj*100}%. Condition: {cond_score}/5.
        COMPS: {json.dumps(sold_comps)}
        
        REQUIRED OUTPUT SECTIONS:
        1. A suggested 'Strike Price' for listing.
        2. What is the least a buyer can put an offer.
        3. A 3-point rationale based on the current market sentiment.

        STRICT FORMATTING RULES:
        4. Use standard Markdown headers (###) for sections.
        5. Use bullet points for the rationale.
        6. IMPORTANT: Ensure there is a space before and after every asterisk (*) and bold marker (**).
        7. Do not combine numbers and text without spaces (e.g., use "$530,000" instead of "$530K").
        """
        
        # ✅ FIXED: Uses 'latest' to avoid the 404 error from your screenshot
        message = client.messages.create(
            model="claude-sonnet-4-6", 
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        st.markdown("---")
        st.markdown(message.content[0].text)