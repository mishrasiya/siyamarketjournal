"""
update_market_journal.py
Fetches latest market and economic data and safely updates market_journal.csv
"""

import csv
import os
from datetime import datetime, timedelta
import requests
from config import API_KEYS

# ===== SETTINGS =====
CSV_FILE = "market_journal.csv"
DATE_FORMAT = "%Y-%m-%d"
YEARS_TO_KEEP = 5

# Symbols to fetch
STOCKS = ["QQQ", "VIX"]
FRED_SERIES = {
    "10Y Yield": "DGS10",
    "Fed Funds Rate": "FEDFUNDS"
}

# ===== FUNCTIONS =====

def fetch_alpha_vantage(symbol):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={API_KEYS['alpha_vantage']}&outputsize=compact"
    try:
        r = requests.get(url)
        data = r.json()
        return data.get("Time Series (Daily)", {})
    except Exception as e:
        print(f"⚠️ Alpha Vantage error for {symbol}: {e}")
        return {}

def fetch_fred(series_id):
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={API_KEYS['fred']}&file_type=json"
    try:
        r = requests.get(url)
        data = r.json()
        return {obs["date"]: obs["value"] for obs in data.get("observations", []) if obs["value"] != "."}
    except Exception as e:
        print(f"⚠️ FRED error for {series_id}: {e}")
        return {}

# ===== LOAD EXISTING CSV =====
existing_data = []
if os.path.exists(CSV_FILE):
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing_data.append(row)

# Keep track of existing dates to avoid duplicates
existing_dates = set()
for row in existing_data:
    date_val = row.get("Date", "").strip()
    if date_val:
        existing_dates.add(date_val)

# ===== FETCH NEW DATA =====
print("📈 Fetching market data...")

stock_data = {}
for symbol in STOCKS:
    stock_data[symbol] = fetch_alpha_vantage(symbol)

fred_data = {}
for name, series_id in FRED_SERIES.items():
    fred_data[name] = fetch_fred(series_id)

# ===== COMBINE DATA =====
combined_dates = set(existing_dates)
for symbol, data in stock_data.items():
    combined_dates.update(data.keys())
for series in fred_data.values():
    combined_dates.update(series.keys())

combined = []

for date in sorted(combined_dates):
    row = {"Date": date}
    # Add existing row data first (preserve original columns)
    existing_row = next((r for r in existing_data if r.get("Date", "").strip() == date), {})
    row.update(existing_row)

    # Update stock prices if available
    for symbol in STOCKS:
        if date in stock_data.get(symbol, {}):
            try:
                row[symbol] = round(float(stock_data[symbol][date]["4. close"]), 2)
            except Exception:
                pass  # keep existing if API failed

    # Update FRED data if available
    for name in FRED_SERIES.keys():
        if date in fred_data.get(name, {}):
            try:
                row[name] = round(float(fred_data[name][date]), 2)
            except Exception:
                pass

    combined.append(row)

# ===== FILTER BY DATE (last N YEARS) =====
cutoff_date = datetime.now().date() - timedelta(days=YEARS_TO_KEEP*365)
filtered_data = []
for row in combined:
    date_str = row.get("Date", "").strip()
    if not date_str:
        continue
    try:
        row_date = datetime.strptime(date_str, DATE_FORMAT).date()
        if row_date >= cutoff_date:
            filtered_data.append(row)
    except ValueError:
        continue  # skip invalid dates

# ===== WRITE BACK CSV =====
# Use all columns seen in any row
all_columns = set()
for row in filtered_data:
    all_columns.update(row.keys())
all_columns = sorted(all_columns)

with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=all_columns)
    writer.writeheader()
    for row in filtered_data:
        # Fill missing columns with empty strings
        safe_row = {col: row.get(col, "") for col in all_columns}
        writer.writerow(safe_row)

print(f"✅ Market journal updated successfully. Kept last {YEARS_TO_KEEP} years.")
