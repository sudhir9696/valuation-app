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
GOOGLE_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY") # New Key

# --- SIDEBAR ---
with st.sidebar:
    st.header("Property Config")
    address = st.text_input("Street Address", value="6089 Grand Loop Rd")
    city = st.text_input("City, State", value="Sugar Hill, GA")
    zip_code = st.text_input("Zip Code", value="30518")
    
    st.divider()
    st.header("Search Parameters")
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 1.5, 0.1)
    exclude_addr = st.text_input("Exclude Address?", placeholder="e.g., 4718")
    
    run_btn = st.button("Generate Valuation Report", type="primary")

# --- DATA FETCHING ---
@st.cache_data(ttl=3600)
def get_market_data(addr, cty, zp, radius):
    headers = {"X-Api-Key": RENT_KEY, "Accept": "application/json"}
    full_addr = f"{addr}, {cty}, {zp}"
    lat, lon = None, None

    # 1. DYNAMIC GEOCODING (Google Maps is much more reliable)
    if GOOGLE_KEY:
        g_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_addr}&key={GOOGLE_KEY}"
        g_res = requests.get(g_url).json()
        if g_res['status'] == 'OK':
            lat = g_res['results'][0]['geometry']['location']['lat']
            lon = g_res['results'][0]['geometry']['location']['lng']

    # 2. Fetch Valuation (Uses Lat/Lon if found, otherwise falls back to address string)
    avm_url = "https://api.rentcast.io/v1/avm/value"
    avm_params = {
        "propertyType": "Single Family", "radius": radius, "compCount": 25
    }
    if lat and lon:
        avm_params.update({"latitude": lat, "longitude": lon})
    else:
        avm_params.update({"address": full_addr})
        
    avm_res = requests.get(avm_url, headers=headers, params=avm_params).json()
    
    # 3. Fetch Subject Details
    prop_url = "https://api.rentcast.io/v1/properties"
    prop_params = {"address": full_addr}
    prop_res = requests.get(prop_url, headers=headers, params=prop_params).json()
    
    subject_details = prop_res[0] if isinstance(prop_res, list) and len(prop_res) > 0 else {}
    return avm_res, subject_details

# --- MAIN PAGE ---
if run_btn:
    with st.spinner("Locking on to property..."):
        avm_data, prop_info = get_market_data(address, city, zip_code, search_radius)
        
        # ✅ DATA EXTRACTION (Fixed paths)
        subject_beds = prop_info.get('bedrooms') or 0
        subject_tax = prop_info.get('taxAmt') or 0
        b_val = prop_info.get('basementType') or ""
        subject_basement = "Yes" if b_val and str(b_val).lower() != "none" else "No"
        
        # Metrics Display
        col1, col2, col3 = st.columns(3)
        col1.metric("Subject Beds", subject_beds)
        col2.metric("Annual Tax", f"${subject_tax:,.0f}" if subject_tax else "N/A")
        col3.metric("Basement", subject_basement)

        # Comparison Table
        st.subheader("📍 Detailed Comparable Sales")
        all_comps = avm_data.get('comparables', [])
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
                    "Dist (Mi)": round(c.get('distance', 0), 2)
                })
            df = pd.DataFrame(comp_list)
            df['Price'] = df['Price'].map('${:,.0f}'.format)
            st.dataframe(df.style.applymap(lambda x: 'background-color: #1e4620' if x == subject_beds else '', subset=['Beds']), use_container_width=True)
            
            # AI Analysis
            st.subheader("🧠 Strategic AI Analysis")
            client = anthropic.Anthropic(api_key=AI_KEY)
            prompt = f"Address: {address}. Comps: {json.dumps(sold_comps)}. Beds: {subject_beds}. Basement: {subject_basement}. Give strike price, floor offer, and 3 rationale points."
            msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=1024, messages=[{"role": "user", "content": prompt}])
            st.markdown(msg.content[0].text)