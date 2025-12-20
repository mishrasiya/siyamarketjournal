# 📊 Market Data Auto-Populator

Automatically fills your Market Journal spreadsheet with real market data!

---

## 🚀 Quick Start (3 Steps)

### Step 1️⃣: Setup (One time)

Open Terminal and run:

```bash
# First, navigate to wherever you saved this project folder
cd "path/to/Automatic Market Journal"

# Then run:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2️⃣: Add Your API Keys (One time)

```bash
cp config.example.py config.py
```

Then edit `config.py` and paste your API keys. Get them here:
- **EODHD** (required): https://eodhd.com/register
- **Alpha Vantage**: https://www.alphavantage.co/support/#api-key
- **FRED**: https://fred.stlouisfed.org/docs/api/api_key.html

### Step 3️⃣: Run It

Every time you want to update your spreadsheet:

```bash
# Activate virtual environment (if not already active)
source venv/bin/activate

# Run the market data fetcher
python3 market_data_fetcher.py
```

Or if you prefer to use the venv's Python directly:

```bash
venv/bin/python3 market_data_fetcher.py
```

Updated spreadsheet is saved as: `Market Journal Fall 2025.xlsx`

**To convert Excel to CSV for web deployment:**
```bash
python3 -c "import pandas as pd; pd.read_excel('Market Journal Fall 2025.xlsx').to_csv('market_journal.csv', index=False)"
```

---

## 📋 What It Does

✅ **Forex Rates**: EUR/USD, GBP/USD, USD/JPY  
✅ **Stock Indices**: NIKKEI, DAX, FTSE, DOW, S&P 500  
✅ **Bond Yields**: Japan, Germany, UK, US (10-Year)  
✅ **Commodities**: Gold, Brent Crude Oil  
✅ **Crypto**: Bitcoin

---

## 🆘 Troubleshooting

### "config.py not found"
```bash
cp config.example.py config.py
# Then edit config.py and add your API keys
```

### "Module not found"
```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## 📁 Files

```
Market Journal Fall 2025 Template.xlsx  ← Your template (don't edit this!)
Market Journal Fall 2025.xlsx   ← Your output (this gets created)
market_data_fetcher.py                   ← Main script (run this!)
market_journal.csv                       ← CSV version for web deployment
config.py                                ← Your secret API keys (not in git)
index.html                               ← Web interface for Vercel
```

---


## ❓ Need Help?

1. Make sure you're in the right folder
2. Make sure `config.py` has your API keys
3. Make sure you ran the setup (Step 1) first

**Questions?** Check that:
- ✅ `venv/` folder exists
- ✅ `config.py` exists (not `config.example.py`)
- ✅ Your API keys are in `config.py`
