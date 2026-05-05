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
        # STRATEGY 1: STANDARD CROSSOVER ALERTS
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
        # STRATEGY 2: 50 SMA PULLBACK ALERTS
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
            # Step B: Check if the 50 SMA pullback condition has ALREADY happened since the crossover
            pullback_happened_before = False
            
            for i in range(last_cross_idx + 1, curr_pos_idx):
                i_open = df['open'].iloc[i]
                i_close = df['close'].iloc[i]
                i_sma_50 = df['sma_50'].iloc[i]
                
                if last_cross_type == 'golden':
                    # Check for previous red candle below 50 SMA
                    if i_close < i_sma_50 and i_close < i_open:
                        pullback_happened_before = True
                        break
                elif last_cross_type == 'death':
                    # Check for previous green candle above 50 SMA
                    if i_close > i_sma_50 and i_close > i_open:
                        pullback_happened_before = True
                        break
            
            # Step C: If it hasn't happened before, check the CURRENT closed candle
            if not pullback_happened_before:
                curr_open = df['open'].iloc[curr_pos_idx]
                curr_close = df['close'].iloc[curr_pos_idx]
                curr_sma50 = df['sma_50'].iloc[curr_pos_idx]

                if last_cross_type == 'golden':
                    # Current candle is red and closed below 50 SMA
                    if curr_close < curr_sma50 and curr_close < curr_open:
                        msg = f"📉 <b>1ST PULLBACK (BELOW 50 SMA)</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\nPrice dropped below 50 SMA with a RED candle for the first time since Golden Cross."
                        print(msg)
                        send_telegram_alert(msg)
                
                elif last_cross_type == 'death':
                    # Current candle is green and closed above 50 SMA
                    if curr_close > curr_sma50 and curr_close > curr_open:
                        msg = f"📈 <b>1ST PULLBACK (ABOVE 50 SMA)</b>\n<b>Asset:</b> {symbol}\n<b>Timeframe:</b> {timeframe}\n<b>Time:</b> {time_str} (IST)\nPrice rose above 50 SMA with a GREEN candle for the first time since Death Cross."
                        print(msg)
                        send_telegram_alert(msg)
            
    except Exception as e:
        print(f"Error checking {symbol} on {timeframe}: {e}")

def main():
    print("Starting Multi-Timeframe Scanner (15m, 30m, 1h)...")
    print("Bot will calculate exact sleep times to fire 5 seconds after candle close.")
    
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        current_minute_floor = now.replace(second=0, microsecond=0)
        
        # --- OPTIMIZED FOR 15 MINUTE CYCLES ---
        minutes_to_next = 15 - (now.minute % 15)
        next_candle_close = current_minute_floor + datetime.timedelta(minutes=minutes_to_next)
        
        scan_timeframes = ['15m'] 
        
        # If the minute is a multiple of 30, it means a 30m candle just closed
        if next_candle_close.minute % 30 == 0:
            scan_timeframes.append('30m')
            
        # If the minute is 00, it means an hour just closed, so we add the 1h timeframe
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
                time.sleep(1) # Respect Binance rate limits

if __name__ == '__main__':
    main()