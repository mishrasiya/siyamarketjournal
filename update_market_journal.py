import csv
import requests
from datetime import datetime
from config import API_KEYS

# -----------------------
# Configurable settings
# -----------------------
CSV_FILE = "market_journal.csv"
ALPHA_SYMBOLS = ["QQQ", "VIX"]  # Add more tickers as needed
FRED_SERIES = ["DGS10"]  # 10-year treasury yield
DATE_FORMAT = "%Y-%m-%d"

# -----------------------
# Helper functions
# -----------------------
def get_alpha_vantage(symbol):
    """Fetch daily adjusted close data for a symbol"""
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={API_KEYS['alpha_vantage']}&outputsize=compact"
    r = requests.get(url)
    try:
        data = r.json()["Time Series (Daily)"]
    except Exception:
        print(f"⚠️ Alpha Vantage limit hit or invalid response for {symbol}")
        return {}
    return data

def get_fred_series(series_id):
    """Fetch FRED series data"""
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={API_KEYS['fred']}&file_type=json"
    r = requests.get(url)
    try:
        observations = r.json()["observations"]
        return {obs["date"]: obs["value"] for obs in observations if obs["value"] != "."}
    except Exception:
        print(f"⚠️ FRED API limit hit or invalid response for {series_id}")
        return {}

# -----------------------
# Load existing CSV
# -----------------------
with open(CSV_FILE, "r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    if not headers:
        raise ValueError("CSV has no headers!")
    # Detect date column
    date_col = next((c for c in headers if "date" in c.lower()), None)
    if not date_col:
        raise ValueError("No date column found in CSV!")
    existing_data = list(reader)
    existing_dates = {row[date_col] for row in existing_data}

# -----------------------
# Fetch new data
# -----------------------
print("📈 Fetching market data...")
alpha_data = {sym: get_alpha_vantage(sym) for sym in ALPHA_SYMBOLS}
fred_data = {series: get_fred_series(series) for series in FRED_SERIES}

# -----------------------
# Collect all dates to update
# -----------------------
all_dates = set(existing_dates)
for data in alpha_data.values():
    all_dates.update(data.keys())
for data in fred_data.values():
    all_dates.update(data.keys())

# Sort dates newest to oldest
all_dates = sorted(all_dates, reverse=True)

# -----------------------
# Build updated CSV rows
# -----------------------
updated_rows = []
for date in all_dates:
    row = {h: "" for h in headers}  # keep all columns
    row[date_col] = date

    # Fill alpha_vantage data
    for sym in ALPHA_SYMBOLS:
        if sym in headers and date in alpha_data.get(sym, {}):
            row[sym] = alpha_data[sym][date]["4. close"]

    # Fill FRED series data
    for series in FRED_SERIES:
        if series in headers and date in fred_data.get(series, {}):
            row[series] = fred_data[series][date]

    # If the date exists in CSV, preserve old row values for missing columns
    if date in existing_dates:
        old_row = next(r for r in existing_data if r[date_col] == date)
        for h in headers:
            if not row[h]:
                row[h] = old_row.get(h, "")

    updated_rows.append(row)

# -----------------------
# Write updated CSV safely
# -----------------------
with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(updated_rows)

print(f"✅ Market journal updated! Total rows: {len(updated_rows)}")
