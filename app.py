import streamlit as st
import requests
import anthropic
import json
import pandas as pd

# --- APP CONFIG ---
st.set_page_config(page_title="Residential Valuation Dashboard", layout="wide")
st.title("🏡 Residential Valuation Dashboard")

# --- KEYS FROM STREAMLIT SECRETS ---
# Configure these in .streamlit/secrets.toml locally, or in Settings -> Secrets
# on Streamlit Cloud. Missing keys degrade to a clear message instead of a crash.
RENT_KEY = st.secrets.get("RENTCAST_API_KEY")
AI_KEY = st.secrets.get("CLAUDE_API_KEY")

if not RENT_KEY:
    st.error(
        "`RENTCAST_API_KEY` is not configured. Add it to `.streamlit/secrets.toml` "
        "(see README) or to Settings -> Secrets on Streamlit Cloud."
    )
    st.stop()

# --- SIDEBAR: INPUTS ---
with st.sidebar:
    st.header("Property Config")
    address = st.text_input("Street Address", value="", placeholder="123 Example St")
    city = st.text_input("City, State", value="", placeholder="Atlanta, GA")
    tax_val = st.number_input("Tax Assessment ($)", value=0, step=1000)

    st.divider()
    st.header("Search Parameters")
    search_radius = st.slider("Search Radius (Miles)", 0.1, 5.0, 1.5, 0.1)
    exclude_addr = st.text_input(
        "Exclude Address?", value="", placeholder="house number or street fragment"
    )

    st.divider()
    st.header("Market Controls")
    mkt_adj = st.slider("Market Adjustment (%)", -10, 15, -3) / 100
    cond_score = st.select_slider("Condition (1-5)", options=[1, 2, 3, 4, 5], value=4)

    run_btn = st.button("Generate Valuation Report", type="primary")

# Georgia and most states assess at 40% of fair market value.
ASSESSMENT_RATIO = 0.4


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
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


# --- MAIN PAGE: REPORTING ---
if run_btn:
    if not address or not city:
        st.warning("Enter a street address and city before generating a report.")
        st.stop()

    with st.spinner("Analyzing Market Data via RentCast..."):
        try:
            data = get_valuation_data(search_radius, address, city)
        except requests.exceptions.Timeout:
            st.error("RentCast timed out after 30s. Try again in a moment.")
            st.stop()
        except requests.exceptions.HTTPError as exc:
            st.error(f"RentCast returned {exc.response.status_code}. Check the address and your API key.")
            st.stop()
        except requests.exceptions.RequestException as exc:
            st.error(f"Could not reach RentCast: {exc}")
            st.stop()

        all_comps = data.get('comparables', [])

        # Generic Exclusion Filter
        if exclude_addr:
            sold_comps = [c for c in all_comps if exclude_addr.lower() not in c.get('formattedAddress', '').lower()]
        else:
            sold_comps = all_comps

        tax_baseline = tax_val / ASSESSMENT_RATIO if tax_val else 0

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

                # Check for basement - Y if any basement type exists, otherwise N
                has_basement = "Y" if c.get('basementType') and str(c.get('basementType')).lower() != 'none' else "N"

                comp_data.append({
                    "Address": c.get('formattedAddress'),
                    "Sold Date": c.get('lastSeenDate', "")[:10],
                    "Beds": c.get('bedrooms', 0),
                    "Baths": c.get('bathrooms', 0),
                    "Basement": has_basement,
                    "Price": p,
                    "$/SqFt": round(p/s, 2) if s > 0 else 0,
                    "Dist (Mi)": round(c.get('distance', 0), 2)
                })

            # Convert to DataFrame and sort by Sold Date (Descending)
            df = pd.DataFrame(comp_data)
            df = df.sort_values(by="Sold Date", ascending=False)

            df_disp = df.copy()
            df_disp['Price'] = df_disp['Price'].map('${:,.0f}'.format)

            # Displaying with full container width
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
        else:
            st.warning("No comps found.")

        # AI Analysis with STRICT FORMATTING
        st.subheader("🧠 Strategic AI Analysis")
        if not AI_KEY:
            st.info("`CLAUDE_API_KEY` is not configured — skipping the AI analysis section.")
            st.stop()

        client = anthropic.Anthropic(api_key=AI_KEY)

        prompt = f"""
        Subject Property: {address}. Tax Baseline: ${tax_baseline:,.0f}.
        Market Adjustment: {mkt_adj*100}%. Condition: {cond_score}/5.

        COMPS DATA: {json.dumps(sold_comps)}

        REQUIRED OUTPUT SECTIONS:
        1. A suggested 'Strike Price' for listing.
        2. What is the least a buyer can put an offer.
        3. A 3-point rationale comparing subject features (Beds/Baths/Basement) to these comps.

        STRICT FORMATTING RULES:
        4. Use standard Markdown headers (###) for sections.
        5. Use bullet points for the rationale.
        6. IMPORTANT: Ensure there is a space before and after every asterisk (*) and bold marker (**).
        7. Do not combine numbers and text without spaces (e.g., use "$530,000" instead of "$530K").
        """

        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
        except anthropic.APIError as exc:
            st.error(f"Claude API error: {exc}")
            st.stop()

        st.markdown("---")
        st.markdown(message.content[0].text)
