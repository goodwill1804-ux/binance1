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

SYMBOLS = ['BTC/USDT', 'XAU/USDT', 'XAG/USDT','CLUSDT']

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
        
        # --- DYNAMIC INDEXING ---
        tf_ms = exchange.parse_timeframe(timeframe) * 1000
        current_time_ms = int(time.time() * 1000)
        last_candle_timestamp = df['timestamp'].iloc[-1]
        
        if current_time_ms >= (last_candle_timestamp + tf_ms):
            curr_idx = -1
        else:
            curr_idx = -2
            
        # Convert dynamic negative indices to positive integers for historical scanning
        curr_pos_idx = len(df) + curr_idx
        prev_pos_idx = curr_pos_idx - 1
            
        prev_50 = df['sma_50'].iloc[prev_pos_idx]
        prev_200 = df['sma_200'].iloc[prev_pos_idx]
        curr_50 = df['sma_50'].iloc[curr_pos_idx]
        curr_200 = df['sma_200'].iloc[curr_pos_idx]
        
        # Get current IST time
        now_ist = datetime.datetime.now(datetime.timezone.utc).astimezone(IST)
        time_str = now_ist.strftime('%I:%M %p')
        
        # ==========================================
        # 1. CHECK FOR STANDARD CROSSOVER
        # ==========================================
        if prev_50 <= prev_200 and curr_50 > curr_200:
            msg = f"🟢 <b>GOLDEN CROSS</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\n50 SMA crossed above 200 SMA."
            print(msg)
            send_telegram_alert(msg)
            
        elif prev_50 >= prev_200 and curr_50 < curr_200:
            msg = f"🔴 <b>DEATH CROSS</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\n50 SMA crossed below 200 SMA."
            print(msg)
            send_telegram_alert(msg)


        # ==========================================
        # 2. THE PULLBACK ENGINE
        # ==========================================
        last_cross_type = None
        last_cross_idx = None

        # Step A: Look backwards to find the established trend (Golden or Death)
        for i in range(prev_pos_idx, 0, -1):
            p_50 = df['sma_50'].iloc[i-1]
            p_200 = df['sma_200'].iloc[i-1]
            c_50 = df['sma_50'].iloc[i]
            c_200 = df['sma_200'].iloc[i]

            if p_50 <= p_200 and c_50 > c_200:
                last_cross_type = 'golden'
                last_cross_idx = i
                break
            elif p_50 >= p_200 and c_50 < c_200:
                last_cross_type = 'death'
                last_cross_idx = i
                break

        if last_cross_type is not None:
            # Step B: Check if price has already touched 200 SMA since the crossover
            touched_before = False
            for i in range(last_cross_idx + 1, curr_pos_idx):
                low = df['low'].iloc[i]
                high = df['high'].iloc[i]
                sma_200 = df['sma_200'].iloc[i]
                
                # A touch means the 200 SMA is between the high and low of the candle
                if low <= sma_200 and high >= sma_200:
                    touched_before = True
                    break
            
            # Step C: If it hasn't touched before, check the CURRENT closed candle
            if not touched_before:
                curr_low = df['low'].iloc[curr_pos_idx]
                curr_high = df['high'].iloc[curr_pos_idx]
                curr_open = df['open'].iloc[curr_pos_idx]
                curr_close = df['close'].iloc[curr_pos_idx]
                curr_sma200 = df['sma_200'].iloc[curr_pos_idx]

                # Check if current candle touches 200 SMA
                touches_now = (curr_low <= curr_sma200) and (curr_high >= curr_sma200)

                if touches_now:
                    # Bullish Pullback: Golden trend + Green Candle (Close > Open)
                    if last_cross_type == 'golden' and curr_close > curr_open:
                        msg = f"🔄 <b>1ST PULLBACK (BULLISH)</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\nPrice touched 200 SMA and formed a green candle after Golden Cross."
                        print(msg)
                        send_telegram_alert(msg)
                    
                    # Bearish Pullback: Death trend + Red Candle (Close < Open)
                    elif last_cross_type == 'death' and curr_close < curr_open:
                        msg = f"🔄 <b>1ST PULLBACK (BEARISH)</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\nPrice touched 200 SMA and formed a red candle after Death Cross."
                        print(msg)
                        send_telegram_alert(msg)
            
    except Exception as e:
        print(f"Error checking {symbol} on {timeframe}: {e}")

def main():
    print("Starting Ultra-Precision Scanner with Pullback Engine...")
    print("Bot will calculate exact sleep times to fire 5 seconds after candle close.")
    
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        
        current_minute_floor = now.replace(second=0, microsecond=0)
        minutes_to_next = 5 - (now.minute % 5)
        next_candle_close = current_minute_floor + datetime.timedelta(minutes=minutes_to_next)
        
        scan_timeframes = ['5m'] 
        if next_candle_close.minute % 15 == 0:
            scan_timeframes.append('15m')
        if next_candle_close.minute % 30 == 0:
            scan_timeframes.append('30m')
        if next_candle_close.minute == 0:
            scan_timeframes.append('1h')
            
        target_scan_time = next_candle_close + datetime.timedelta(seconds=5)
        sleep_seconds = (target_scan_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        
        if sleep_seconds > 0:
            target_ist = target_scan_time.astimezone(IST)
            print(f"\nNext scan scheduled for: {target_ist.strftime('%I:%M:%S %p')} IST")
            print(f"Server sleeping for {sleep_seconds:.1f} seconds...")
            time.sleep(sleep_seconds)
        
        # --- SERVER WAKES UP EXACTLY 5 SECONDS AFTER CANDLES CLOSE ---
        wake_time_ist = datetime.datetime.now(datetime.timezone.utc).astimezone(IST)
        print(f"--- [IST: {wake_time_ist.strftime('%I:%M:%S %p')}] Scanning: {scan_timeframes} ---")
        
        for symbol in SYMBOLS:
            for tf in scan_timeframes:
                check_crossover(symbol, tf)
                time.sleep(1) 

if __name__ == '__main__':
    main()