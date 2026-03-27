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
        
        # --- LEAD ENGINEER FIX: DYNAMIC INDEXING ---
        # Convert timeframe to milliseconds (e.g., 5m = 300,000 ms)
        tf_ms = exchange.parse_timeframe(timeframe) * 1000
        current_time_ms = int(time.time() * 1000)
        
        # Get the timestamp of the very last bar Binance gave us
        last_candle_timestamp = df['timestamp'].iloc[-1]
        
        # Determine if Binance has pushed the new forming candle yet
        if current_time_ms >= (last_candle_timestamp + tf_ms):
            # API is lagging: The last bar in the dataframe IS the fully closed candle
            curr_idx = -1
            prev_idx = -2
        else:
            # API is fast: The last bar is currently forming, so drop back one index
            curr_idx = -2
            prev_idx = -3
            
        prev_50 = df['sma_50'].iloc[prev_idx]
        prev_200 = df['sma_200'].iloc[prev_idx]
        curr_50 = df['sma_50'].iloc[curr_idx]
        curr_200 = df['sma_200'].iloc[curr_idx]
        
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
    print("Starting Ultra-Precision Scanner (Dynamic Indexing Built-In)...")
    print("Bot will calculate exact sleep times to fire 5 seconds after candle close.")
    
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # 1. Calculate the exact time the NEXT 5-minute candle closes
        current_minute_floor = now.replace(second=0, microsecond=0)
        minutes_to_next = 5 - (now.minute % 5)
        next_candle_close = current_minute_floor + datetime.timedelta(minutes=minutes_to_next)
        
        # --- FIX: Define target timeframes BEFORE sleeping to prevent drift bugs ---
        scan_timeframes = ['5m'] 
        if next_candle_close.minute % 15 == 0:
            scan_timeframes.append('15m')
        if next_candle_close.minute % 30 == 0:
            scan_timeframes.append('30m')
        if next_candle_close.minute == 0:
            scan_timeframes.append('1h')
            
        # 2. Add our 5-second delay buffer
        target_scan_time = next_candle_close + datetime.timedelta(seconds=5)
        
        # 3. Calculate exactly how many seconds to sleep to hit that target
        sleep_seconds = (target_scan_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        
        if sleep_seconds > 0:
            target_ist = target_scan_time.astimezone(IST)
            print(f"\nNext scan scheduled for: {target_ist.strftime('%I:%M:%S %p')} IST")
            print(f"Server sleeping for {sleep_seconds:.1f} seconds...")
            # Put the server to sleep until the exact target time
            time.sleep(sleep_seconds)
        
        # --- SERVER WAKES UP EXACTLY 5 SECONDS AFTER CANDLES CLOSE ---
        
        wake_time_ist = datetime.datetime.now(datetime.timezone.utc).astimezone(IST)
        print(f"--- [IST: {wake_time_ist.strftime('%I:%M:%S %p')}] Scanning: {scan_timeframes} ---")
        
        for symbol in SYMBOLS:
            for tf in scan_timeframes:
                check_crossover(symbol, tf)
                time.sleep(1) # Respect Binance rate limits

if __name__ == '__main__':
    main()