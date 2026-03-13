import pandas as pd
import talib
import numpy as np
from backtesting import Backtest, Strategy
import os

# Get absolute path to data
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
DATA_PATH = os.path.join(PROJECT_ROOT, 'src', 'data', 'rbi', 'BTC-USD-15m-train.csv')

def _bb_upper(close, period, std):
    u, _, _ = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return u

def _bb_mid(close, period, std):
    _, m, _ = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return m

def _bb_lower(close, period, std):
    _, _, l = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return l

def _bbw(close, period, std):
    u, m, l = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return np.where(m == 0, 0, (u - l) / m)


class VolatilityBreakout(Strategy):
    # Strategy parameters
    bb_period = 20
    bb_std = 2.0
    bbw_sma_period = 50
    risk_percent = 0.02  # 2% risk per trade
    atr_period = 14
    stop_atr_multiplier = 1.5

    def init(self):
        self.bb_upper = self.I(_bb_upper, self.data.Close, self.bb_period, self.bb_std)
        self.bb_lower = self.I(_bb_lower, self.data.Close, self.bb_period, self.bb_std)

        bbw_raw = self.I(_bbw, self.data.Close, self.bb_period, self.bb_std)
        self.bbw = bbw_raw
        self.bbw_sma = self.I(talib.SMA, bbw_raw, timeperiod=self.bbw_sma_period)

        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close,
                         timeperiod=self.atr_period)
    
    def next(self):
        # Skip if we don't have enough data
        if len(self.data.Close) < max(self.bb_period, self.bbw_sma_period, self.atr_period) + 1:
            return
        
        current_idx = len(self.data.Close) - 1
        
        # 🌙 MOON DEV DEBUG: Print current status
        if current_idx % 100 == 0:
            print(f"🌙 Processing candle {current_idx} | Close: {self.data.Close[-1]:.2f}")
            print(f"   BB Lower: {self.bb_lower[-1]:.2f}, BB Upper: {self.bb_upper[-1]:.2f}")
            print(f"   BBW: {self.bbw[-1]:.4f}, BBW SMA: {self.bbw_sma[-1]:.4f}")
        
        # Check if we're in a trade
        if not self.position:
            # Check entry conditions for SHORT
            # 1. Low volatility condition: BBW < BBW_SMA
            low_vol_condition = self.bbw[-1] < self.bbw_sma[-1]
            
            # 2. Breakout signal: Previous close broke below BB Lower
            breakout_condition = self.data.Close[-2] < self.bb_lower[-2]
            
            if low_vol_condition and breakout_condition:
                # 🌙 ENTRY SIGNAL DETECTED!
                print(f"🚀 SHORT ENTRY SIGNAL! Candle {current_idx}")
                print(f"   Close: {self.data.Close[-1]:.2f}, BB Lower: {self.bb_lower[-1]:.2f}")
                print(f"   BBW: {self.bbw[-1]:.4f} < BBW SMA: {self.bbw_sma[-1]:.4f}")
                
                # Calculate position size with risk management
                entry_price = self.data.Close[-1]
                stop_price = entry_price + (self.atr[-1] * self.stop_atr_multiplier)
                risk_per_share = abs(stop_price - entry_price)
                
                if risk_per_share <= 0:
                    print("⚠️  Risk calculation error - skipping trade")
                    return
                
                # Calculate position size based on 2% risk
                risk_amount = self.equity * self.risk_percent
                position_size = risk_amount / risk_per_share
                
                # 🌙 MOON DEV FIX: Round to whole number for unit-based sizing
                position_size = int(round(position_size))
                
                if position_size > 0:
                    # Enter short position
                    self.sell(size=position_size, sl=stop_price)
                    print(f"   📉 Entered SHORT: Size={position_size}, Entry={entry_price:.2f}")
                    print(f"   🛡️  Stop Loss: {stop_price:.2f}, Risk: ${risk_amount:.2f}")
        else:
            # We're in a trade, check exit conditions
            # Exit when close crosses above BB Upper
            if self.data.Close[-1] >= self.bb_upper[-1]:
                # 🌙 EXIT SIGNAL DETECTED!
                print(f"✅ EXIT SIGNAL! Candle {current_idx}")
                print(f"   Close: {self.data.Close[-1]:.2f} >= BB Upper: {self.bb_upper[-1]:.2f}")
                print(f"   💰 Profit/Loss: ${self.position.pl:.2f}")
                self.position.close()

# Load and prepare data
print("🌙 Loading data from:", DATA_PATH)
data = pd.read_csv(DATA_PATH)

# Clean column names
data.columns = data.columns.str.strip().str.lower()

# Drop unnamed columns
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])

# Rename columns to match backtesting.py requirements
column_mapping = {
    'open': 'Open',
    'high': 'High', 
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume'
}

data = data.rename(columns=column_mapping)

# Ensure we have the required columns
required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
for col in required_cols:
    if col not in data.columns:
        print(f"⚠️  Warning: Missing column {col}")

# Convert datetime column if present
if 'datetime' in data.columns:
    data['datetime'] = pd.to_datetime(data['datetime'])
    data = data.set_index('datetime')
elif 'date' in data.columns:
    data['date'] = pd.to_datetime(data['date'])
    data = data.set_index('date')
elif 'time' in data.columns:
    data['time'] = pd.to_datetime(data['time'])
    data = data.set_index('time')

print(f"📊 Data loaded: {len(data)} candles")
print(f"📈 Columns: {list(data.columns)}")

# Run backtest
print("\n" + "="*50)
print("🌙 STARTING BACKTEST - VOLATILITY BREAKOUT STRATEGY")
print("="*50)

bt = Backtest(data, VolatilityBreakout, cash=1000000, commission=.002)

# Run with default parameters
stats = bt.run()

# Print full statistics
print("\n" + "="*50)
print("📊 BACKTEST RESULTS")
print("="*50)
print(stats)
print("\n" + "="*50)
print("🎯 STRATEGY DETAILS")
print("="*50)
print(stats._strategy)