"""
Simple Market Data Auto-Populator
Fetches market data and populates Excel spreadsheet

Data Sources:
- yfinance: Forex, stocks, commodities, crypto (free, no API key)
- FRED: Bond yields (requires API key)
"""

import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import yfinance as yf
import requests
import re
import io
from threading import Thread
import queue
import signal
import sys

warnings.filterwarnings('ignore')

# Import Gemini API
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  google-generativeai not installed. News generation will be skipped.")
    print("   Install with: pip install google-generativeai")

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully"""
    global shutdown_requested
    shutdown_requested = True
    print("\n\n⚠️  Shutdown requested. Finishing current operation and exiting...")

# Import API keys from config
try:
    from config import API_KEYS
except ImportError:
    print("❌ ERROR: config.py not found!")
    print("Please copy config.example.py to config.py and add your API keys.")
    exit(1)


class MarketDataFetcher:
    def __init__(self, api_keys):
        self.api_keys = api_keys

    def get_yfinance_data(self, symbol, date):
        """Fetch data from Yahoo Finance with timeout protection"""
        try:
            start_date = date - timedelta(days=7)
            end_date = date + timedelta(days=1)
            
            ticker = yf.Ticker(symbol)
            # Use timeout to prevent hanging (15 seconds should be enough)
            result_queue = queue.Queue()
            exception_queue = queue.Queue()
            
            def fetch_data():
                try:
                    hist = ticker.history(start=start_date, end=end_date)
                    result_queue.put(hist)
                except Exception as e:
                    exception_queue.put(e)
            
            thread = Thread(target=fetch_data)
            thread.daemon = True
            thread.start()
            thread.join(timeout=15)
            
            if thread.is_alive():
                # Thread is still running, it timed out
                print(f"    ⚠️  yfinance timeout for {symbol}")
                return None
            
            if not exception_queue.empty():
                raise exception_queue.get()
            
            if result_queue.empty():
                return None
            
            hist = result_queue.get()
            
            if not hist.empty:
                hist.index = hist.index.tz_localize(None)
                target_datetime = pd.Timestamp(date)
                
                if target_datetime in hist.index:
                    return float(hist.loc[target_datetime]['Close'])
                else:
                    valid_dates = hist[hist.index <= target_datetime]
                    if not valid_dates.empty:
                        return float(valid_dates.iloc[-1]['Close'])
            
            return None
        except Exception as e:
            print(f"    ⚠️  yfinance error for {symbol}: {e}")
            return None

    def get_forex_rate(self, from_currency, to_currency, date):
        """Fetch forex rate using yfinance"""
        symbol = f"{from_currency}{to_currency}=X"
        return self.get_yfinance_data(symbol, date)

    def get_stock_index(self, symbol, date):
        """Fetch stock index data using yfinance"""
        return self.get_yfinance_data(symbol, date)

    def get_eodhd_bond_yield(self, ticker, date):
        """Fetch bond yield from EODHD (daily data)"""
        if not self.api_keys.get('eodhd') or self.api_keys.get('eodhd') == 'YOUR_EODHD_API_KEY':
            return None

        try:
            url = f'https://eodhd.com/api/eod/{ticker}.GBOND'
            params = {
                'api_token': self.api_keys['eodhd'],
                'fmt': 'json',
                'from': (date - timedelta(days=7)).strftime('%Y-%m-%d'),
                'to': date.strftime('%Y-%m-%d')
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            # Check for rate limit
            if response.status_code == 402:
                return None  # Rate limited, will fall back to other sources
            
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    # Find the exact date or most recent before it
                    date_str = date.strftime('%Y-%m-%d')
                    for entry in reversed(data):
                        if entry.get('date') and entry['date'] <= date_str:
                            # EODHD returns close price, but for bonds we might need yield
                            # Some EODHD endpoints return yield directly
                            value = float(entry.get('close', entry.get('yield', 0)))
                            if value > 0:  # Valid yield
                                return value
                elif isinstance(data, dict) and 'error' in data:
                    return None
            
            return None
        except Exception as e:
            return None

    def get_investing_bond_yield(self, ticker, date):
        """Fetch bond yield from Investing.com (daily historical data)"""
        # Investing.com ticker mapping
        investing_tickers = {
            'DE10Y': 'germany-10-year-bond-yield',
            'UK10Y': 'uk-10-year-bond-yield',
            'JP10Y': 'japan-10-year-bond-yield'
        }
        
        investing_symbol = investing_tickers.get(ticker)
        if not investing_symbol:
            return None
        
        try:
            # Investing.com historical data URL
            # Format: https://www.investing.com/rates-bonds/{symbol}-historical-data
            url = f'https://www.investing.com/rates-bonds/{investing_symbol}-historical-data'
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5'
            }
            
            # For historical data, we need to use their API endpoint or scrape the historical data table
            # Investing.com has a data endpoint, but it requires authentication
            # Let's try scraping the historical data page
            date_str = date.strftime('%m/%d/%Y')
            
            # Try to get historical data via their data endpoint (if accessible)
            # This is a simplified approach - may need adjustment
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                
                # Look for the yield value in the historical data table
                # Investing.com shows data in tables, look for the date row
                # Pattern: look for date and corresponding yield value
                date_pattern = date.strftime('%b %d, %Y')  # e.g., "Sep 05, 2025"
                date_pattern2 = date.strftime('%m/%d/%Y')  # e.g., "09/05/2025"
                
                # Try to find the row with our date and extract yield
                # The yield is typically in a column after the date
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if date_pattern in line or date_pattern2 in line:
                        # Look for yield value in nearby lines (usually in same row or next few lines)
                        for j in range(max(0, i-5), min(len(lines), i+10)):
                            # Look for percentage pattern
                            yield_match = re.search(r'([\d.]+)\s*%', lines[j])
                            if yield_match:
                                try:
                                    yield_value = float(yield_match.group(1))
                                    if 0 < yield_value < 20:  # Reasonable yield range
                                        return yield_value
                                except ValueError:
                                    continue
                
                # Alternative: Look for JSON data embedded in the page
                json_patterns = [
                    r'window\.historicalData\s*=\s*(\[.+?\]);',
                    r'var historicalData\s*=\s*(\[.+?\]);',
                    r'"historicalData":\s*(\[.+?\]),'
                ]
                
                for pattern in json_patterns:
                    json_match = re.search(pattern, content, re.DOTALL)
                    if json_match:
                        try:
                            import json
                            data = json.loads(json_match.group(1))
                            if isinstance(data, list):
                                # Find entry matching our date
                                for entry in data:
                                    if isinstance(entry, dict):
                                        entry_date = entry.get('date', '')
                                        if date_str in entry_date or date_pattern in entry_date:
                                            yield_val = entry.get('yield') or entry.get('value') or entry.get('close')
                                            if yield_val:
                                                try:
                                                    yield_value = float(str(yield_val).replace('%', ''))
                                                    if 0 < yield_value < 20:
                                                        return yield_value
                                                except (ValueError, TypeError):
                                                    continue
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
            
            return None
        except Exception as e:
            return None

    def get_cnbc_bond_yield(self, ticker, date):
        """Fetch bond yield from CNBC by scraping (fallback for when APIs are rate-limited)"""
        # CNBC ticker mapping
        cnbc_tickers = {
            'DE10Y': 'DE10Y-DE',
            'UK10Y': 'UK10Y-GB',
            'JP10Y': 'JP10Y-JP'
        }
        
        cnbc_symbol = cnbc_tickers.get(ticker)
        if not cnbc_symbol:
            return None
        
        try:
            # CNBC URL for the bond quote page
            url = f'https://www.cnbc.com/quotes/{cnbc_symbol}'
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                content = response.text
                
                # Look for yield patterns in the HTML
                yield_patterns = [
                    r'Yield[^>]*>([\d.]+)%',
                    r'"yield"[^>]*>([\d.]+)',
                    r'Yield[^>]*>([\d.]+)',
                    r'data-yield="([\d.]+)"',
                ]
                
                for pattern in yield_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        try:
                            yield_value = float(matches[0])
                            return yield_value
                        except (ValueError, IndexError):
                            continue
                
                # Alternative: Look for JSON data in the page
                json_pattern = r'window\.__data\s*=\s*({.+?});'
                json_match = re.search(json_pattern, content, re.DOTALL)
                if json_match:
                    try:
                        import json
                        data = json.loads(json_match.group(1))
                        if isinstance(data, dict):
                            for key in ['quote', 'data', 'yield', 'Yield']:
                                if key in data:
                                    value = data[key]
                                    if isinstance(value, (int, float)):
                                        return float(value)
                                    elif isinstance(value, dict) and 'yield' in value:
                                        yield_val = value['yield']
                                        if isinstance(yield_val, (int, float)):
                                            return float(yield_val)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        pass
            
            return None
        except Exception as e:
            return None

    def get_stooq_bond_yield(self, ticker, date):
        """Fetch daily government bond yields from Stooq (free CSV feed) - THIS WORKS!"""
        stooq_map = {
            'US10Y': 'ust10y.us',
            'GERMAN_10YR': 'de10y.de',
            'UK_10YR': 'uk10y.uk',
            'JAPAN_10YR': 'jp10y.jp'
        }

        stooq_symbol = stooq_map.get(ticker)
        if not stooq_symbol:
            return None

        url = f'https://stooq.com/q/d/l/?s={stooq_symbol}&i=d'
        response = None
        try:
            response = requests.get(url, timeout=15)
        except (KeyboardInterrupt, SystemExit):
            # Ignore interrupts and retry once
            try:
                time.sleep(0.5)
                response = requests.get(url, timeout=15)
            except:
                return None
        except Exception as e:
            # Network errors - return None to try fallback
            return None
        
        # Process the response if we got one
        if response and response.status_code == 200 and response.text.strip():
            text = response.text.strip()
            if len(text) < 50:  # Too short, probably error
                return None
            
            try:
                df = pd.read_csv(io.StringIO(text))
                # Stooq CSV might have different column names
                date_col = None
                close_col = None
                
                for col in df.columns:
                    col_lower = col.lower().strip()
                    if 'date' in col_lower:
                        date_col = col
                    if 'close' in col_lower:
                        close_col = col
                
                if not date_col or not close_col:
                    return None
                
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df.dropna(subset=[date_col, close_col]).sort_values(date_col)
                
                if df.empty:
                    return None
                
                # Find the closest date (on or before target date)
                target_date = pd.to_datetime(date)
                target_df = df[df[date_col] <= target_date]
                
                if target_df.empty:
                    # If no data before target, try to get closest after (for future dates)
                    future_df = df[df[date_col] > target_date]
                    if not future_df.empty:
                        return float(future_df.iloc[0][close_col])
                    return None
                
                latest_row = target_df.iloc[-1]
                value = latest_row[close_col]
                
                # Convert to float, handling percentage format if needed
                if isinstance(value, str):
                    value = value.replace('%', '').strip()
                
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
            except Exception as e:
                return None
        else:
            return None

    def get_bond_yield(self, country, date):
        """Fetch bond yield - try multiple sources for daily data"""
        # US: Use yfinance for daily data
        if country == 'US':
            value = self.get_yfinance_data('^TNX', date)
            if value is not None:
                return value
            # Fallback to FRED daily data
            return self.get_fred_data('DGS10', date)
        
        # International bonds: Try Stooq first (FREE, daily, reliable!)
        stooq_tickers = {
            'GERMAN': 'GERMAN_10YR',
            'UK': 'UK_10YR',
            'JAPAN': 'JAPAN_10YR'
        }
        
        stooq_ticker = stooq_tickers.get(country)
        if stooq_ticker:
            value = self.get_stooq_bond_yield(stooq_ticker, date)
            if value is not None and value > 0:
                print(f"      ✓ {country} 10YR: {value:.3f}% (Stooq)")
                return value
            else:
                print(f"      ⚠️  {country} 10YR: Stooq failed, trying fallbacks...")
        
        # Fallback chain: EODHD -> Investing.com -> CNBC -> FRED
        eodhd_tickers = {
            'GERMAN': 'DE10Y',
            'UK': 'UK10Y',
            'JAPAN': 'JP10Y'
        }
        
        ticker = eodhd_tickers.get(country)
        if ticker:
            # Try EODHD for daily data (may be rate-limited)
            value = self.get_eodhd_bond_yield(ticker, date)
            if value is not None and value > 0:
                print(f"      ✓ {country} 10YR: {value:.3f}% (EODHD)")
                return value
            
            # Try Investing.com for daily historical data
            value = self.get_investing_bond_yield(ticker, date)
            if value is not None and value > 0:
                print(f"      ✓ {country} 10YR: {value:.3f}% (Investing.com)")
                return value
            
            # Try CNBC scraping as fallback
            value = self.get_cnbc_bond_yield(ticker, date)
            if value is not None and value > 0:
                print(f"      ✓ {country} 10YR: {value:.3f}% (CNBC)")
                return value
        
        # Last resort: FRED (monthly data)
        fred_series = {
            'GERMAN': 'IRLTLT01DEM156N',
            'UK': 'IRLTLT01GBM156N',
            'JAPAN': 'IRLTLT01JPM156N'
        }
        
        series_id = fred_series.get(country)
        if series_id:
            value = self.get_fred_data(series_id, date)
            if value is not None:
                print(f"      ✓ {country} 10YR: {value:.3f}% (FRED - monthly data)")
            else:
                print(f"      ❌ {country} 10YR: All sources failed")
            return value
        
        return None

    def get_fred_data(self, series_id, date):
        """Fetch bond yield data from FRED API (fallback - monthly data only)"""
        try:
            url = 'https://api.stlouisfed.org/fred/series/observations'
            params = {
                'series_id': series_id,
                'api_key': self.api_keys.get('fred'),
                'file_type': 'json',
                'start_date': (date - timedelta(days=90)).strftime('%Y-%m-%d'),
                'end_date': date.strftime('%Y-%m-%d'),
                'sort_order': 'desc',
                'limit': 50
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'observations' in data and data['observations']:
                for obs in data['observations']:
                    if obs['value'] != '.' and obs['value']:
                        value = float(obs['value'])
                        return value
            
            return None
        except Exception as e:
            print(f"    ⚠️  FRED error for {series_id}: {e}")
            return None

    def get_crypto_price(self, symbol, date):
        """Fetch cryptocurrency price using yfinance"""
        yf_symbol = f"{symbol}-USD"
        return self.get_yfinance_data(yf_symbol, date)

    def get_financial_headlines(self, date):
        """Fetch financial news headlines for a specific date using NewsAPI or EODHD"""
        date_str = date.strftime('%Y-%m-%d')
        financial_keywords = [
            'market', 'stock', 'economy', 'economic', 'inflation', 
            'fed', 'central bank', 'earnings', 'trading', 'investment',
            'dollar', 'currency', 'bond', 'yield', 'oil', 'gold',
            'bitcoin', 'crypto', 'gdp', 'unemployment', 'rate', 'policy',
            'finance', 'financial', 'bank', 'monetary', 'fiscal', 's&p',
            'dow', 'nasdaq', 'forex', 'commodity', 'equity', 'index'
        ]
        
        # NewsAPI free tier only goes back to 2025-10-22, so try it first for recent dates
        newsapi_min_date = datetime(2025, 10, 22).date()
        
        # Try NewsAPI first if date is within range
        if date.date() >= newsapi_min_date and self.api_keys.get('newsapi') and self.api_keys.get('newsapi') != 'YOUR_NEWSAPI_KEY':
            try:
                url = 'https://newsapi.org/v2/everything'
                params = {
                    'apiKey': self.api_keys['newsapi'],
                    'q': 'stock market OR economy OR inflation OR Fed OR central bank OR earnings OR trading',
                    'from': date_str,
                    'to': date_str,
                    'language': 'en',
                    'sortBy': 'relevancy',
                    'pageSize': 10
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    articles = data.get('articles', [])
                    headlines = []
                    for article in articles:
                        title = article.get('title', '').strip()
                        if title and len(title) > 15:
                            title_lower = title.lower()
                            if any(keyword in title_lower for keyword in financial_keywords):
                                headlines.append(title)
                                if len(headlines) >= 5:
                                    return headlines
                    if headlines:
                        return headlines
            except Exception:
                pass  # Fall through to EODHD
        
        # Try EODHD as fallback
        if self.api_keys.get('eodhd') and self.api_keys.get('eodhd') != 'YOUR_EODHD_API_KEY':
            try:
                url = 'https://eodhd.com/api/news'
                params = {
                    'api_token': self.api_keys['eodhd'],
                    's': 'AAPL.US',
                    'from': date_str,
                    'to': date_str,
                    'limit': 20
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data and isinstance(data, list):
                        headlines = []
                        for article in data:
                            title = article.get('title', '').strip()
                            article_date = article.get('date', '')
                            if article_date and date_str in article_date:
                                if title and len(title) > 15:
                                    title_lower = title.lower()
                                    if any(keyword in title_lower for keyword in financial_keywords):
                                        headlines.append(title)
                                        if len(headlines) >= 5:
                                            return headlines
                        if headlines:
                            return headlines
                elif response.status_code == 402:
                    pass  # Rate limited, return empty
            except Exception:
                pass
        
        return []  # No headlines found

    def generate_daily_news(self, date, market_data, formatted_data):
        """Generate a short daily news item based on market data using Gemini API"""
        if not GEMINI_AVAILABLE:
            return None
        
        if not self.api_keys.get('gemini') or self.api_keys.get('gemini') == 'YOUR_GEMINI_API_KEY':
            return None
        
        try:
            # Configure Gemini API
            genai.configure(api_key=self.api_keys['gemini'])
            # Use gemini-2.5-flash (fast and efficient for news generation)
            # Fallback to other available models if needed
            model = None
            model_used = None
            model_names_to_try = [
                'gemini-2.5-flash',  # Primary choice - fast and efficient
                'models/gemini-2.5-flash',  # With prefix
                'gemini-2.5-pro',  # More capable fallback
                'models/gemini-2.5-pro',
                'gemini-pro',  # Older stable model
                'models/gemini-pro',
            ]
            
            for model_name in model_names_to_try:
                try:
                    model = genai.GenerativeModel(model_name)
                    model_used = model_name
                    break
                except Exception as e:
                    continue
            
            if model is None:
                print(f"    ⚠️  Could not initialize any Gemini model")
                return None
            
            # Build market data summary
            market_summary_parts = []
            
            if formatted_data.get('EUR/USD'):
                market_summary_parts.append(f"EUR/USD: {formatted_data['EUR/USD']:.4f}")
            if formatted_data.get('STG/USD'):
                market_summary_parts.append(f"GBP/USD: {formatted_data['STG/USD']:.4f}")
            if formatted_data.get('USD/YEN'):
                market_summary_parts.append(f"USD/JPY: {formatted_data['USD/YEN']:.2f}")
            if formatted_data.get('DOW'):
                market_summary_parts.append(f"DOW: {formatted_data['DOW']:.2f}")
            if formatted_data.get('S&P'):
                market_summary_parts.append(f"S&P 500: {formatted_data['S&P']:.2f}")
            if formatted_data.get('NIKKEI'):
                market_summary_parts.append(f"Nikkei 225: {formatted_data['NIKKEI']:.2f}")
            if formatted_data.get('DAX'):
                market_summary_parts.append(f"DAX: {formatted_data['DAX']:.2f}")
            if formatted_data.get('FTSE'):
                market_summary_parts.append(f"FTSE 100: {formatted_data['FTSE']:.2f}")
            if formatted_data.get('GOLD'):
                market_summary_parts.append(f"Gold: ${formatted_data['GOLD']:.2f}/oz")
            if formatted_data.get('BRENT'):
                market_summary_parts.append(f"Brent Crude: ${formatted_data['BRENT']:.2f}/barrel")
            if formatted_data.get('BITCOIN'):
                market_summary_parts.append(f"Bitcoin: ${formatted_data['BITCOIN']:.2f}")
            
            market_summary = "\n".join(market_summary_parts)
            
            # Fetch actual news headlines for this date
            print(f"  → Fetching news headlines...")
            headlines = self.get_financial_headlines(date)
            if headlines:
                print(f"   ✓ Found {len(headlines)} headlines")
            else:
                print(f"   ⚠️  No headlines found, using market data only")
            
            # Build the prompt with headlines if available
            if headlines:
                headlines_text = "\n".join([f"- {h}" for h in headlines])
                prompt = f"""You are a financial news analyst. Based on the actual news headlines and market data below for {date.strftime('%B %d, %Y')}, write a brief, professional news item (1-2 sentences, maximum 100 words) explaining how the news affected the markets that day.

Actual News Headlines from {date.strftime('%B %d, %Y')}:
{headlines_text}

Market Data:
{market_summary}

Write a concise news item that connects the actual news headlines to the market movements. Reference specific headlines and explain how they influenced the markets. IMPORTANT: Vary your sentence structure and openings - do NOT start multiple entries with the same phrase. Use diverse openings:
- Start with specific markets: "The S&P 500...", "European indices..."
- Start with news events: "Following [headline]...", "News of [event]..."
- Start with economic factors: "Inflation concerns...", "Central bank signals..."
- Use different structures: questions, statements, cause-effect patterns

Mix short and medium-length sentences. Be specific about which markets moved and connect them to the actual news. Keep it brief and punchy."""
            else:
                # Fallback if no headlines available
                prompt = f"""You are a financial news analyst. Based on the market data below for {date.strftime('%B %d, %Y')}, write a brief, professional news item (1-2 sentences, maximum 100 words) explaining what likely affected the markets that day.

Market Data:
{market_summary}

Write a concise news item in the style of a financial news brief. IMPORTANT: Vary your sentence structure and openings - do NOT start multiple entries with the same phrase like "Global equities..." or "Markets..." Instead, use diverse openings such as:
- Start with specific markets: "The S&P 500...", "European indices...", "Asian markets..."
- Start with economic factors: "Inflation concerns...", "Central bank signals...", "Economic data..."
- Start with commodities/forex: "Oil prices...", "The dollar...", "Gold..."
- Use different structures: questions, statements, cause-effect patterns

Mix short and medium-length sentences. Focus on the most significant market movements and provide plausible explanations based on typical market drivers (economic data, central bank policy, geopolitical events, corporate earnings, etc.). Be specific about which markets moved and suggest realistic reasons why. Keep it brief and punchy."""

            # Generate news item
            response = model.generate_content(prompt)
            news_item = response.text.strip()
            
            # Clean up the response (remove markdown formatting if present)
            news_item = re.sub(r'\*\*|__', '', news_item)  # Remove bold markers
            news_item = re.sub(r'^#+\s*', '', news_item)  # Remove headers
            
            # Debug: show which model was used (only first time)
            if not hasattr(self, '_model_shown'):
                print(f"    ℹ️  Using Gemini model: {model_used}")
                self._model_shown = True
            
            return news_item
            
        except Exception as e:
            print(f"    ⚠️  Gemini API error: {e}")
            return None


def fetch_market_data(target_date, fetcher):
    """Fetch all market data for a specific date"""
    
    print(f"\n📊 Fetching data for {target_date.strftime('%Y-%m-%d')}...")
    
    data = {}
    
    # FOREX DATA
    print("  → Forex rates...")
    data['EUR/USD'] = fetcher.get_forex_rate('EUR', 'USD', target_date)
    data['GBP/USD'] = fetcher.get_forex_rate('GBP', 'USD', target_date)
    data['USD/JPY'] = fetcher.get_forex_rate('USD', 'JPY', target_date)
    
    # STOCK INDICES
    print("  → Stock indices...")
    indices = {
        'NIKKEI': '^N225',
        'DAX': '^GDAXI',
        'FTSE': '^FTSE',
        'DOW': '^DJI',
        'S&P': '^GSPC'
    }
    
    for key, symbol in indices.items():
        data[key] = fetcher.get_stock_index(symbol, target_date)
    
    # BOND YIELDS (using yfinance for daily data)
    print("  → Bond yields...")
    data['US_10YR'] = fetcher.get_bond_yield('US', target_date)
    data['GERMAN_10YR'] = fetcher.get_bond_yield('GERMAN', target_date)
    data['UK_10YR'] = fetcher.get_bond_yield('UK', target_date)
    data['JAPAN_10YR'] = fetcher.get_bond_yield('JAPAN', target_date)
    
    # COMMODITIES
    print("  → Commodities...")
    data['GOLD'] = fetcher.get_yfinance_data('GC=F', target_date)
    data['BRENT'] = fetcher.get_yfinance_data('BZ=F', target_date)
    
    # CRYPTOCURRENCY
    print("  → Cryptocurrency...")
    data['BITCOIN'] = fetcher.get_crypto_price('BTC', target_date)
    
    return data


def format_value(value, decimal_places):
    """Format value with specified decimal places"""
    if value is None or pd.isna(value):
        return None
    return round(float(value), decimal_places)


def format_market_data(data):
    """Format market data according to template requirements"""
    formatted = {}
    
    formatted['EUR/USD'] = format_value(data['EUR/USD'], 4)
    formatted['STG/USD'] = format_value(data['GBP/USD'], 4)
    formatted['USD/YEN'] = format_value(data['USD/JPY'], 2)
    formatted['NIKKEI'] = format_value(data['NIKKEI'], 2)
    formatted['DAX'] = format_value(data['DAX'], 2)
    formatted['FTSE'] = format_value(data['FTSE'], 2)
    formatted['DOW'] = format_value(data['DOW'], 2)
    formatted['S&P'] = format_value(data['S&P'], 2)
    formatted['JAPAN_10YR'] = format_value(data['JAPAN_10YR'], 3)
    formatted['GERMAN_10YR'] = format_value(data['GERMAN_10YR'], 3)
    formatted['UK_10YR'] = format_value(data['UK_10YR'], 3)
    formatted['US_10YR'] = format_value(data['US_10YR'], 3)
    formatted['GOLD'] = format_value(data['GOLD'], 2)
    formatted['BRENT'] = format_value(data['BRENT'], 2)
    formatted['BITCOIN'] = format_value(data['BITCOIN'], 2)
    
    return formatted


def process_spreadsheet(input_filename, output_filename=None):
    """Main function to process the spreadsheet"""
    global shutdown_requested
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)   # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Handle termination requests
    
    print("=" * 70)
    print("🚀 MARKET DATA AUTO-POPULATOR")
    print("=" * 70)
    
    # Initialize fetcher
    fetcher = MarketDataFetcher(API_KEYS)
    
    # Read the Excel file
    try:
        df = pd.read_excel(input_filename, sheet_name=0)
        print(f"✅ Successfully loaded {input_filename}")
        print(f"   Shape: {df.shape}")
    except Exception as e:
        print(f"❌ Error reading Excel file: {e}")
        return None
    
    # Find the date column
    date_col = None
    for col in df.columns:
        if 'DATE' in str(col).upper():
            date_col = col
            break
    
    if date_col is None:
        print("❌ Could not find DATE column!")
        return None
    
    print(f"✅ Found date column: '{date_col}'")
    print(f"\n📅 Processing dates...")
    
    # Process each row with a valid date
    updated_rows = 0
    skipped_rows = 0
    total_start_time = time.time()
    
    # Count total dates to process
    total_dates = sum(1 for _, row in df.iterrows() 
                      if not pd.isna(row[date_col]) 
                      and not (isinstance(row[date_col], str) and ('SAMPLE' in row[date_col].upper() or 'DELETE' in row[date_col].upper()))
                      and pd.to_datetime(row[date_col]).date() <= datetime.now().date())
    
    current_date_num = 0
    
    for idx, row in df.iterrows():
        # Check for shutdown request
        if shutdown_requested:
            print("\n⚠️  Shutdown requested. Saving progress and exiting...")
            break
        
        date_value = row[date_col]
        
        # Skip if date is empty, sample row, or invalid
        if pd.isna(date_value):
            continue
        
        if isinstance(date_value, str) and ('SAMPLE' in date_value.upper() or 'DELETE' in date_value.upper()):
            continue
        
        try:
            # Parse the date
            target_date = pd.to_datetime(date_value)
            
            # Only process dates that are today or in the past
            if target_date.date() > datetime.now().date():
                skipped_rows += 1
                continue
            
            current_date_num += 1
            date_start_time = time.time()
            print(f"\n[{current_date_num}/{total_dates}] Processing {target_date.strftime('%Y-%m-%d')}...")
            
            # Fetch market data
            try:
                market_data = fetch_market_data(target_date, fetcher)
            except (KeyboardInterrupt, SystemExit):
                # Check if shutdown was requested
                if shutdown_requested:
                    print("\n⚠️  Shutdown requested. Saving progress and exiting...")
                    break
                # Otherwise, retry once
                print("   ⚠️  Network interruption, retrying...")
                time.sleep(1)  # Brief pause before retry
                try:
                    market_data = fetch_market_data(target_date, fetcher)
                except:
                    print("   ⚠️  Skipping this date due to network issues")
                    continue
            except Exception as e:
                print(f"   ⚠️  Error fetching data: {e}")
                continue
            
            # Check again after fetching data
            if shutdown_requested:
                print("\n⚠️  Shutdown requested. Saving progress and exiting...")
                break
            
            formatted_data = format_market_data(market_data)
            
            # Generate daily news item
            if shutdown_requested:
                print("\n⚠️  Shutdown requested. Saving progress and exiting...")
                break
            
            print("  → Generating news item...")
            news_item = fetcher.generate_daily_news(target_date, market_data, formatted_data)
            if news_item:
                print(f"   ✓ News item generated ({len(news_item)} chars)")
            else:
                print("   ⚠️  News item generation skipped")
            
            # Check again before updating dataframe
            if shutdown_requested:
                print("\n⚠️  Shutdown requested. Saving progress and exiting...")
                break
            
            # Update the dataframe
            for col in df.columns:
                col_clean = str(col).upper().strip()
                
                if 'EUR' in col_clean and 'USD' in col_clean:
                    df.at[idx, col] = formatted_data['EUR/USD']
                elif ('STG' in col_clean or 'GBP' in col_clean) and 'USD' in col_clean:
                    df.at[idx, col] = formatted_data['STG/USD']
                elif 'USD' in col_clean and 'YEN' in col_clean:
                    df.at[idx, col] = formatted_data['USD/YEN']
                elif 'NIKKEI' in col_clean:
                    df.at[idx, col] = formatted_data['NIKKEI']
                elif 'DAX' in col_clean:
                    df.at[idx, col] = formatted_data['DAX']
                elif 'FTSE' in col_clean:
                    df.at[idx, col] = formatted_data['FTSE']
                elif 'DOW' in col_clean:
                    df.at[idx, col] = formatted_data['DOW']
                elif 'S&P' in col_clean:
                    df.at[idx, col] = formatted_data['S&P']
                elif 'JAPAN' in col_clean and '10' in col_clean:
                    df.at[idx, col] = formatted_data['JAPAN_10YR']
                elif 'GERMAN' in col_clean and '10' in col_clean:
                    df.at[idx, col] = formatted_data['GERMAN_10YR']
                elif 'UK' in col_clean and '10' in col_clean:
                    df.at[idx, col] = formatted_data['UK_10YR']
                elif 'US' in col_clean and '10' in col_clean:
                    df.at[idx, col] = formatted_data['US_10YR']
                elif 'GOLD' in col_clean:
                    df.at[idx, col] = formatted_data['GOLD']
                elif 'BRENT' in col_clean or 'CRUDE' in col_clean:
                    df.at[idx, col] = formatted_data['BRENT']
                elif 'BITCOIN' in col_clean:
                    df.at[idx, col] = formatted_data['BITCOIN']
                elif ('NEWS' in col_clean and 'DAILY' in col_clean) or ('SHORT' in col_clean and 'NEWS' in col_clean and 'ITEM' in col_clean):
                    # Match the news column: "Short DAILY NEWS ITEM(S) that affected one or more of today's prices"
                    if news_item:
                        df.at[idx, col] = news_item
            
            date_total_time = time.time() - date_start_time
            updated_rows += 1
            print(f"   ✓ Updated row {idx + 1} | Time: {date_total_time:.1f}s")
            
        except (KeyboardInterrupt, SystemExit):
            # Check if shutdown was requested
            if shutdown_requested:
                print("\n⚠️  Shutdown requested. Saving progress and exiting...")
                break
            # Otherwise, continue to next row
            print("   ⚠️  Interrupted, continuing with next date...")
            continue
        except Exception as e:
            print(f"   ❌ Error processing row {idx + 1} (date: {date_value}): {e}")
            continue
    
    # Save the updated file (even if interrupted)
    if output_filename is None:
        output_filename = f"Updated_{input_filename}"
    
    total_time = time.time() - total_start_time
    
    try:
        df.to_excel(output_filename, index=False, engine='openpyxl')
        print(f"\n{'=' * 70}")
        print(f"🎉 SUCCESS!")
        print(f"✅ Updated {updated_rows} rows with market data")
        if skipped_rows > 0:
            print(f"⏭️  Skipped {skipped_rows} future dates")
        print(f"⏱️  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        print(f"💾 Saved as: {output_filename}")
        print(f"{'=' * 70}")
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return None
    
    return df


if __name__ == "__main__":
    input_file = "Market Journal Fall 2025 Template.xlsx"
    output_file = "Market Journal Fall 2025.xlsx"
    
    print("\n📋 Input:  Market Journal Fall 2025 Template.xlsx")
    print("💾 Output: Market Journal Fall 2025.xlsx\n")
    
    process_spreadsheet(input_file, output_file)