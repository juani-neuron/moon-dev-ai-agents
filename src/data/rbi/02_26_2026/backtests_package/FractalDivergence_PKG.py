import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

class FractalDivergence(Strategy):
    # Strategy parameters
    fractal_period = 5  # Williams Fractal period (2 bars on each side + center)
    rsi_period = 14
    atr_period = 14
    risk_per_trade = 0.02  # 2% risk per trade
    fib_levels = [0.382, 0.5, 0.618]  # Fibonacci retracement levels
    
    def init(self):
        # Clean and prepare data
        print("🌙 Moon Dev Backtest AI Initializing FractalDivergence Strategy...")
        print("✨ Cleaning column names and preparing data...")
        
        # Calculate Williams Fractals (Bearish and Bullish)
        self.fractal_high = self.I(self.calculate_fractal_high, self.data.High, period=self.fractal_period)
        self.fractal_low = self.I(self.calculate_fractal_low, self.data.Low, period=self.fractal_period)
        
        # Calculate RSI for divergence detection
        self.rsi = self.I(talib.RSI, self.data.Close, timeperiod=self.rsi_period)
        
        # Calculate ATR for stop loss sizing
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, timeperiod=self.atr_period)
        
        # Calculate recent swing highs and lows for Fibonacci levels
        self.swing_high = self.I(talib.MAX, self.data.High, timeperiod=20)
        self.swing_low = self.I(talib.MIN, self.data.Low, timeperiod=20)
        
        # Initialize state variables
        self.last_bearish_fractal_idx = -1
        self.last_bullish_fractal_idx = -1
        self.in_position = False
        self.position_type = None
        
        print("✅ Strategy indicators initialized successfully!")
        print(f"🔧 Parameters: Fractal Period={self.fractal_period}, RSI Period={self.rsi_period}")
        print(f"💰 Risk per trade: {self.risk_per_trade*100}%")
    
    def calculate_fractal_high(self, high, period=5):
        """Calculate bearish fractal (swing high)"""
        fractals = np.full(len(high), np.nan)
        half_window = period // 2
        
        for i in range(half_window, len(high) - half_window):
            center = high[i]
            left_window = high[i-half_window:i]
            right_window = high[i+1:i+half_window+1]
            
            if len(left_window) == half_window and len(right_window) == half_window:
                if center > max(left_window) and center > max(right_window):
                    fractals[i] = center
        
        return fractals
    
    def calculate_fractal_low(self, low, period=5):
        """Calculate bullish fractal (swing low)"""
        fractals = np.full(len(low), np.nan)
        half_window = period // 2
        
        for i in range(half_window, len(low) - half_window):
            center = low[i]
            left_window = low[i-half_window:i]
            right_window = low[i+1:i+half_window+1]
            
            if len(left_window) == half_window and len(right_window) == half_window:
                if center < min(left_window) and center < min(right_window):
                    fractals[i] = center
        
        return fractals
    
    def calculate_fibonacci_levels(self, start_price, end_price):
        """Calculate Fibonacci retracement levels"""
        if start_price == end_price:
            return {}
        
        diff = end_price - start_price
        levels = {}
        
        for level in self.fib_levels:
            fib_price = end_price - (diff * level)
            levels[level] = fib_price
        
        return levels
    
    def check_bearish_divergence(self, price_high, rsi_value, lookback=20):
        """Check for bearish divergence (price makes higher high, RSI makes lower high)"""
        if len(self.rsi) < lookback or len(self.data.High) < lookback:
            return False
        
        # Find previous high and RSI values
        prev_high_idx = np.argmax(self.data.High[-lookback:-5])
        prev_high = self.data.High[-lookback:-5][prev_high_idx]
        prev_rsi = self.rsi[-lookback:-5][prev_high_idx] if len(self.rsi[-lookback:-5]) > prev_high_idx else 50
        
        # Check for divergence
        if price_high > prev_high and rsi_value < prev_rsi:
            print(f"⚠️ BEARISH DIVERGENCE DETECTED! Price: {price_high:.2f} > {prev_high:.2f}, RSI: {rsi_value:.2f} < {prev_rsi:.2f}")
            return True
        
        return False
    
    def check_bullish_divergence(self, price_low, rsi_value, lookback=20):
        """Check for bullish divergence (price makes lower low, RSI makes higher low)"""
        if len(self.rsi) < lookback or len(self.data.Low) < lookback:
            return False
        
        # Find previous low and RSI values
        prev_low_idx = np.argmin(self.data.Low[-lookback:-5])
        prev_low = self.data.Low[-lookback:-5][prev_low_idx]
        prev_rsi = self.rsi[-lookback:-5][prev_low_idx] if len(self.rsi[-lookback:-5]) > prev_low_idx else 50
        
        # Check for divergence
        if price_low < prev_low and rsi_value > prev_rsi:
            print(f"⚠️ BULLISH DIVERGENCE DETECTED! Price: {price_low:.2f} < {prev_low:.2f}, RSI: {rsi_value:.2f} > {prev_rsi:.2f}")
            return True
        
        return False
    
    def next(self):
        current_idx = len(self.data) - 1
        
        # Update last fractal indices
        if not np.isnan(self.fractal_high[-1]):
            self.last_bearish_fractal_idx = current_idx
            print(f"📍 BEARISH FRACTAL detected at index {current_idx}, price: {self.fractal_high[-1]:.2f}")
        
        if not np.isnan(self.fractal_low[-1]):
            self.last_bullish_fractal_idx = current_idx
            print(f"📍 BULLISH FRACTAL detected at index {current_idx}, price: {self.fractal_low[-1]:.2f}")
        
        # Check for SHORT setup
        if not self.in_position and self.last_bearish_fractal_idx > 0:
            # Find the last swing low before the bearish fractal
            swing_low_before_fractal = None
            for i in range(self.last_bearish_fractal_idx - 1, max(0, self.last_bearish_fractal_idx - 50), -1):
                if not np.isnan(self.fractal_low[i]):
                    swing_low_before_fractal = self.fractal_low[i]
                    swing_low_idx = i
                    break
            
            if swing_low_before_fractal is not None:
                # Calculate Fibonacci retracement levels
                fib_levels = self.calculate_fibonacci_levels(
                    swing_low_before_fractal, 
                    self.fractal_high[self.last_bearish_fractal_idx]
                )
                
                # Check if current price is near a Fibonacci level
                current_price = self.data.Close[-1]
                current_high = self.data.High[-1]
                
                for level, fib_price in fib_levels.items():
                    price_diff_pct = abs(current_price - fib_price) / fib_price
                    
                    # If price is near Fibonacci level (within 0.5%)
                    if price_diff_pct < 0.005 and level >= 0.5:  # Focus on 50% and 61.8% levels
                        # Check for bearish divergence
                        current_rsi = self.rsi[-1]
                        divergence_detected = self.check_bearish_divergence(current_high, current_rsi)
                        
                        # Check if new bearish fractal is forming at this level
                        fractal_forming = False
                        if current_idx > 2:
                            # Simple check: if current high is near the fractal high and we have a pattern
                            center_high = self.data.High[-2]
                            left_highs = [self.data.High[-4], self.data.High[-3]]
                            right_highs = [self.data.High[-1]]
                            
                            if (len(left_highs) == 2 and len(right_highs) == 1 and
                                center_high > max(left_highs) and center_high > max(right_highs)):
                                fractal_forming = True
                        
                        if divergence_detected and fractal_forming:
                            print(f"🚨 SHORT SETUP DETECTED! 🌙")
                            print(f"   Fibonacci {level*100:.1f}% level: {fib_price:.2f}")
                            print(f"   Current price: {current_price:.2f}")
                            print(f"   RSI: {current_rsi:.2f}")
                            
                            # Entry trigger: break below center candle low
                            entry_price = self.data.Low[-2]  # Low of center candle
                            stop_loss = current_high * 1.002  # 0.2% above the fractal high
                            risk_per_share = stop_loss - entry_price
                            
                            if risk_per_share > 0:
                                # Calculate position size based on risk
                                account_equity = self.equity
                                risk_amount = account_equity * self.risk_per_trade
                                position_size = int(round(risk_amount / risk_per_share))
                                
                                # Calculate take profit levels (Fibonacci extensions)
                                price_diff = self.fractal_high[self.last_bearish_fractal_idx] - swing_low_before_fractal
                                tp1 = entry_price - price_diff  # 100% extension
                                tp2 = entry_price - (price_diff * 1.618)  # 161.8% extension
                                
                                print(f"   Entry: {entry_price:.2f}")
                                print(f"   Stop Loss: {stop_loss:.2f}")
                                print(f"   Take Profit 1: {tp1:.2f} (100% extension)")
                                print(f"   Take Profit 2: {tp2:.2f} (161.8% extension)")
                                print(f"   Position size: {position_size} shares")
                                
                                # Place sell order
                                self.sell(size=position_size, sl=stop_loss, tp=tp1)
                                self.in_position = True
                                self.position_type = 'SHORT'
                                break
        
        # Check for LONG setup (reverse logic)
        if not self.in_position and self.last_bullish_fractal_idx > 0:
            # Find the last swing high before the bullish fractal
            swing_high_before_fractal = None
            for i in range(self.last_bullish_fractal_idx - 1, max(0, self.last_bullish_fractal_idx - 50), -1):
                if not np.isnan(self.fractal_high[i]):
                    swing_high_before_fractal = self.fractal_high[i]
                    swing_high_idx = i
                    break
            
            if swing_high_before_fractal is not None:
                # Calculate Fibonacci retracement levels
                fib_levels = self.calculate_fibonacci_levels(
                    self.fractal_low[self.last_bullish_fractal_idx],
                    swing_high_before_fractal
                )
                
                # Check if current price is near a Fibonacci level
                current_price = self.data.Close[-1]
                current_low = self.data.Low[-1]
                
                for level, fib_price in fib_levels.items():
                    price_diff_pct = abs(current_price - fib_price) / fib_price
                    
                    # If price is near Fibonacci support level
                    if price_diff_pct < 0.005 and level <= 0.382:  # Focus on 38.2% and lower levels
                        # Check for bullish divergence
                        current_rsi = self.rsi[-1]
                        divergence_detected = self.check_bullish_divergence(current_low, current_rsi)
                        
                        # Check if new bullish fractal is forming at this level
                        fractal_forming = False
                        if current_idx > 2:
                            # Simple check: if current low is near the fractal low and we have a pattern
                            center_low = self.data.Low[-2]
                            left_lows = [self.data.Low[-4], self.data.Low[-3]]
                            right_lows = [self.data.Low[-1]]
                            
                            if (len(left_lows) == 2 and len(right_lows) == 1 and
                                center_low < min(left_lows) and center_low < min(right_lows)):
                                fractal_forming = True
                        
                        if divergence_detected and fractal_forming:
                            print(f"🚨 LONG SETUP DETECTED! 🌙")
                            print(f"   Fibonacci {level*100:.1f}% level: {fib_price:.2f}")
                            print(f"   Current price: {current_price:.2f}")
                            print(f"   RSI: {current_rsi:.2f}")
                            
                            # Entry trigger: break above center candle high
                            entry_price = self.data.High[-2]  # High of center candle
                            stop_loss = current_low * 0.998  # 0.2% below the fractal low
                            risk_per_share = entry_price - stop_loss
                            
                            if risk_per_share > 0:
                                # Calculate position size based on risk
                                account_equity = self.equity
                                risk_amount = account_equity * self.risk_per_trade
                                position_size = int(round(risk_amount / risk_per_share))
                                
                                # Calculate take profit levels (Fibonacci extensions)
                                price_diff = swing_high_before_fractal - self.fractal_low[self.last_bullish_fractal_idx]
                                tp1 = entry_price + price_diff  # 100% extension
                                tp2 = entry_price + (price_diff * 1.618)  # 161.8% extension
                                
                                print(f"   Entry: {entry_price:.2f}")
                                print(f"   Stop Loss: {stop_loss:.2f}")
                                print(f"   Take Profit 1: {tp1:.2f} (100% extension)")
                                print(f"   Take Profit 2: {tp2:.2f} (161.8% extension)")
                                print(f"   Position size: {position_size} shares")
                                
                                # Place buy order
                                self.buy(size=position_size, sl=stop_loss, tp=tp1)
                                self.in_position = True
                                self.position_type = 'LONG'
                                break

# Load and prepare data
print("🌙 Moon Dev Backtest AI Loading Data...")
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_path = os.path.join(project_root, "src/data/rbi/BTC-USD-15m-train.csv")

print(f"📂 Loading data from: {data_path}")
data = pd.read_csv(data_path)

# Clean column names
print("🧹 Cleaning column names...")
data.columns = data.columns.str.strip().str.lower()

# Drop any unnamed columns
unnamed_cols = [col for col in data.columns if 'unnamed' in col.lower()]
if unnamed_cols:
    print(f"🗑️ Dropping unnamed columns: {unnamed_cols}")
    data = data.drop(columns=unnamed_cols)

# Ensure proper column mapping
print("🔄 Mapping columns to backtesting format...")
column_mapping = {
    'open': 'Open',
    'high': 'High', 
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume'
}

for old_col, new_col in column_mapping.items():
    if old_col in data.columns:
        data[new_col] = data[old_col]
        if old_col != new_col.lower():
            data = data.drop(columns=[old_col])

# Convert datetime column if exists
if 'datetime' in data.columns:
    data['datetime'] = pd.to_datetime(data['datetime'])
    data = data.set_index('datetime')
elif 'date' in data.columns:
    data['date'] = pd.to_datetime(data['date'])
    data = data.set_index('date')

# Ensure we have all required columns
required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
for col in required_cols:
    if col not in data.columns:
        print(f"⚠️ Warning: Required column '{col}' not found in data")
        # Create placeholder if missing
        if col == 'Volume':
            data[col] = 1000
        else:
            data[col] = data['Close']

print(f"✅ Data loaded successfully! Shape: {data.shape}")
print(f"📊 Columns: {data.columns.tolist()}")
print(f"📅 Date range: {data.index.min()} to {data.index.max()}")

# Run backtest
print("\n🚀 Starting FractalDivergence Backtest...")
print("=" * 50)

bt = Backtest(data, FractalDivergence, cash=1000000, commission=.002)
stats = bt.run()

print("\n" + "=" * 50)
print("📊 BACKTEST RESULTS:")
print("=" * 50)
print(stats)
print("\n" + "=" * 50)
print("🔧 STRATEGY DETAILS:")
print("=" * 50)
print(stats._strategy)