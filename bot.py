import ccxt
import pandas as pd
import time
import requests
import os

# --- CONFIGURATION ---
# Pulling sensitive data from Render Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Initialize Binance USDT-Margined Futures
exchange = ccxt.binanceusdm({
    'enableRateLimit': True,
})

SYMBOLS = ['BTC/USDT', 'XAU/USDT', 'XAG/USDT']
TIMEFRAMES = ['5m', '15m', '30m', '1h']

def send_telegram_alert(message):
    """Sends a formatted message to your Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing. Print to console only:\n", message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def check_crossover(symbol, timeframe):
    """Fetches data and calculates the 50/200 SMA crossover."""
    try:
        # Fetch 210 candles to ensure we have enough data for a 200 SMA
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=210)
        
        if len(bars) < 200:
            print(f"Not enough data for {symbol} on {timeframe}")
            return

        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate Simple Moving Averages
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()
        
        # Avoid repainting: 
        # index [-1] is the current open/forming candle
        # index [-2] is the last fully closed candle
        # index [-3] is the candle before the last closed one
        prev_50 = df['sma_50'].iloc[-3]
        prev_200 = df['sma_200'].iloc[-3]
        
        curr_50 = df['sma_50'].iloc[-2]
        curr_200 = df['sma_200'].iloc[-2]
        
        # Golden Cross: 50 was below 200, now it is above
        if prev_50 <= prev_200 and curr_50 > curr_200:
            msg = f"🟢 <b>GOLDEN CROSS</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n50 SMA crossed above 200 SMA."
            print(msg)
            send_telegram_alert(msg)
            
        # Death Cross: 50 was above 200, now it is below
        elif prev_50 >= prev_200 and curr_50 < curr_200:
            msg = f"🔴 <b>DEATH CROSS</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n50 SMA crossed below 200 SMA."
            print(msg)
            send_telegram_alert(msg)
            
    except Exception as e:
        print(f"Error checking {symbol} on {timeframe}: {e}")

def main():
    print("Starting Market Scanner...")
    
    while True:
        print(f"\n--- Scanning at {pd.Timestamp.utcnow()} ---")
        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                check_crossover(symbol, tf)
                # Small sleep to respect Binance API rate limits
                time.sleep(1) 
        
        print("Scan complete. Sleeping for 5 minutes...")
        # Sleep for 5 minutes (300 seconds) before checking again
        # Since the lowest timeframe is 5m, we don't need to scan faster than this
        time.sleep(300) 

if __name__ == '__main__':
    main()