import ccxt
import pandas as pd
import time
import requests
import os
import datetime
import pytz

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

exchange = ccxt.binanceusdm({
    'enableRateLimit': True,
})

SYMBOLS = ['BTC/USDT', 'XAU/USDT', 'XAG/USDT']
# Timeframes are now handled dynamically by the clock

# Set Timezone to India
IST = pytz.timezone('Asia/Kolkata')

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing:\n", message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def check_crossover(symbol, timeframe):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=210)
        
        if len(bars) < 200:
            return

        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()
        
        prev_50 = df['sma_50'].iloc[-3]
        prev_200 = df['sma_200'].iloc[-3]
        curr_50 = df['sma_50'].iloc[-2]
        curr_200 = df['sma_200'].iloc[-2]
        
        # Get current IST time for the alert message
        now_ist = datetime.datetime.now(datetime.timezone.utc).astimezone(IST)
        time_str = now_ist.strftime('%I:%M %p')
        
        if prev_50 <= prev_200 and curr_50 > curr_200:
            msg = f"🟢 <b>GOLDEN CROSS</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\n50 SMA crossed above 200 SMA."
            print(msg)
            send_telegram_alert(msg)
            
        elif prev_50 >= prev_200 and curr_50 < curr_200:
            msg = f"🔴 <b>DEATH CROSS</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\n50 SMA crossed below 200 SMA."
            print(msg)
            send_telegram_alert(msg)
            
    except Exception as e:
        print(f"Error checking {symbol} on {timeframe}: {e}")

def main():
    print("Starting Precision Clock Scanner (IST Timezone)...")
    print("Bot will scan exactly 5 seconds after candles close.")
    
    while True:
        # Get current absolute time
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        # Check if we are exactly at the 5th second of the minute
        if now_utc.second == 5:
            scan_timeframes = []
            
            # 5-minute candles close when minute is 0, 5, 10, 15, etc.
            if now_utc.minute % 5 == 0:
                scan_timeframes.append('5m')
            
            # 15-minute candles close when minute is 0, 15, 30, 45
            if now_utc.minute % 15 == 0:
                scan_timeframes.append('15m')
                
            # 30-minute candles close when minute is 0, 30
            if now_utc.minute % 30 == 0:
                scan_timeframes.append('30m')
                
            # 1-hour candles close at the top of the UTC hour (which is XX:30 IST)
            if now_utc.minute == 0:
                scan_timeframes.append('1h')
            
            # If any candles just closed, run the scans
            if scan_timeframes:
                now_ist = now_utc.astimezone(IST)
                print(f"\n--- [IST: {now_ist.strftime('%I:%M:%S %p')}] Scanning: {scan_timeframes} ---")
                
                for symbol in SYMBOLS:
                    for tf in scan_timeframes:
                        check_crossover(symbol, tf)
                        time.sleep(1) # Respect API limits
                        
            # Sleep for 50 seconds so we don't accidentally run again in the same minute
            time.sleep(50)
            
        # Sleep briefly (0.5s) to accurately catch the exact 5th second without burning CPU
        time.sleep(0.5)

if __name__ == '__main__':
    main()