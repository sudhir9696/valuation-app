# valuation-app

A single-page Streamlit dashboard that pulls comparable sales for a residential
address, computes a tax-assessment baseline, and produces a short strike-price
analysis with Claude.

## What it does

1. Queries the [RentCast](https://www.rentcast.io/) AVM endpoint for up to 25
   comparable sales within a configurable radius.
2. Derives a fair-market baseline from the county tax assessment
   (`assessment / 0.4` — Georgia and most states assess at 40% of FMV).
3. Renders the comp set sorted by sale date, with `$/sqft` and distance.
4. Asks Claude for a suggested strike price, a floor offer, and a three-point
   rationale comparing the subject's beds/baths/basement to the comp set.

Every API failure degrades to a visible message rather than a stack trace, and
missing credentials are reported at startup instead of raising `KeyError`.

## Setup

```bash
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml`:

```toml
RENTCAST_API_KEY = "your-rentcast-key"
CLAUDE_API_KEY   = "sk-ant-..."
```

`RENTCAST_API_KEY` is required. `CLAUDE_API_KEY` is optional — without it the
comp table still renders and the AI analysis section is skipped.

On Streamlit Cloud, paste the same contents into **Settings → Secrets** instead.
Never commit `secrets.toml`.

## Run

```bash
streamlit run app.py
```

A devcontainer is included (`.devcontainer/devcontainer.json`) if you'd rather
run it in a container.

## Notes

- All inputs are blank by default; no property is pre-populated.
- Comp results are cached for one hour per (radius, address, city) tuple.
- The RentCast request carries a 30-second timeout.
