import csv
import requests
from datetime import datetime, timedelta
from config import API_KEYS

CSV_FILE = "market_journal.csv"
DATE_FORMAT = "%Y-%m-%d"

# ---------------- Helpers ----------------
def get_alpha_vantage(symbol):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={API_KEYS['alpha_vantage']}&outputsize=compact"
    r = requests.get(url)
    try:
        data = r.json()
        if "Time Series (Daily)" not in data:
            print(f"⚠️ No data returned for {symbol}, skipping")
            return {}
        return data["Time Series (Daily)"]
    except Exception as e:
        print(f"⚠️ Error fetching {symbol}: {e}")
        return {}

def get_fred_series(series_id):
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={API_KEYS['fred']}&file_type=json"
    r = requests.get(url)
    try:
        data = r.json()
        if "observations" not in data:
            print(f"⚠️ No data returned for {series_id}, skipping")
            return {}
        return {obs["date"]: obs["value"] for obs in data["observations"] if obs["value"] != "."}
    except Exception as e:
        print(f"⚠️ Error fetching {series_id}: {e}")
        return {}

# ---------------- Load Existing CSV ----------------
existing_data = []
try:
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Date"):  # skip empty date rows
                existing_data.append(row)
except FileNotFoundError:
    print(f"📄 {CSV_FILE} not found, creating a new one.")

# ---------------- Determine last date ----------------
existing_dates = {row["Date"] for row in existing_data if "Date" in row}
today = datetime.today().date()
last_date = max([datetime.strptime(d, DATE_FORMAT).date() for d in existing_dates], default=today - timedelta(days=2))

# ---------------- Fetch Recent Data ----------------
symbols = ["QQQ", "VIX"]
fred_series = {"10Y Yield": "DGS10"}

new_rows = []
for i in range(1, 3):  # last 2 days
    date = today - timedelta(days=i)
    date_str = date.strftime(DATE_FORMAT)
    if date_str in existing_dates:
        continue

    row = {"Date": date_str}

    # Alpha Vantage symbols
    for sym in symbols:
        data = get_alpha_vantage(sym)
        if date_str in data:
            row[sym] = round(float(data[date_str]["4. close"]), 2)
        else:
            row[sym] = ""

    # FRED series
    for col, series_id in fred_series.items():
        data = get_fred_series(series_id)
        row[col] = float(data.get(date_str, "")) if data.get(date_str) else ""

    new_rows.append(row)

# ---------------- Merge Data ----------------
existing_data.extend(new_rows)
existing_data.sort(key=lambda x: x.get("Date", ""))  # ensure chronological order

# ---------------- Determine Fieldnames ----------------
all_fieldnames = set()
for row in existing_data:
    all_fieldnames.update(row.keys())
fieldnames = list(all_fieldnames)

# ---------------- Write Back CSV ----------------
with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(existing_data)

if existing_data:
    print(f"✅ CSV updated! Last date: {existing_data[-1].get('Date', 'Unknown')}")
else:
    print("⚠️ No data to write.")
