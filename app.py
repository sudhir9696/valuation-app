import streamlit as st
import requests
import anthropic
import json
import pandas as pd
from geopy.geocoders import Nominatim # ✅ New Import

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
    zip_code = st.text_input("Zip Code", value="30518") # ✅ Added Zip for better accuracy
    
    st.divider()
    st.header("Search Parameters")
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 1.5, 0.1)
    exclude_addr = st.text_input("Exclude Address?", placeholder="e.g., 4718")
    
    run_btn = st.button("Generate Valuation Report", type="primary")

# --- DYNAMIC GEOCODING & FETCHING ---
@st.cache_data(ttl=3600)
def get_dynamic_data(addr, cty, zp, radius):
    headers = {"X-Api-Key": RENT_KEY, "Accept": "application/json"}
    full_addr = f"{addr}, {cty}, {zp}"
    
    # 1. DYNAMIC GEOCODING: Convert address to Lat/Lon
    geolocator = Nominatim(user_agent="swathi_valuation_app")
    location = geolocator.geocode(full_addr)
    
    if not location:
        return None, None # Handle case where address isn't found
        
    lat, lon = location.latitude, location.longitude

    # 2. Fetch Valuation using those coordinates
    avm_url = "https://api.rentcast.io/v1/avm/value"
    avm_params = {
        "latitude": lat,
        "longitude": lon,
        "propertyType": "Single Family",
        "radius": radius, 
        "compCount": 25
    }
    avm_res = requests.get(avm_url, headers=headers, params=avm_params).json()
    
    # 3. Fetch Property Details for Subject
    prop_url = "https://api.rentcast.io/v1/properties"
    prop_params = {"address": full_addr}
    prop_res = requests.get(prop_url, headers=headers, params=prop_params).json()
    
    subject_details = prop_res[0] if isinstance(prop_res, list) and len(prop_res) > 0 else {}
    
    return avm_res, subject_details

# --- MAIN PAGE ---
if run_btn:
    with st.spinner(f"Geocoding {address}..."):
        avm_data, prop_info = get_dynamic_data(address, city, zip_code, search_radius)
        
        if not avm_data:
            st.error("Could not locate address. Please check the Zip Code and try again.")
        else:
            # Data Extraction
            subject_beds = prop_info.get('bedrooms') or 0
            subject_tax = prop_info.get('taxAmt') or 0
            b_val = prop_info.get('basementType') or ""
            subject_basement = "Yes" if b_val and str(b_val).lower() != "none" else "No"
            
            # (Rest of your Metrics, Table, and AI Analysis code goes here...)
            st.success(f"Market analysis complete for {address}!")
            # [Display logic remains the same as our previous 'bulletproof' version]