```python
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import os

# Data path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src/data/rbi/BTC-USD-15m-train.csv")

class VolumetricReversal(Strategy):
    # Strategy parameters
    vwrsi_period = 14
    oversold_threshold = 30
    volume_sma_period = 20
    breakout_lookback = 5
    risk_per_trade = 0.02  # 2% risk per trade
    reward_ratio = 2.0  # 2:1 reward ratio
    max_hold_bars = 10  # Time-based exit
    
    def init(self):
        # Clean column names
        self.data.df.columns = self.data.df.columns.str.strip().str.lower()
        
        # Calculate indicators using self.I() wrapper
        print("🌙 Initializing VolumetricReversal Strategy...")
        print("✨ Calculating VWRSI indicator...")
        
        # Calculate RSI
        self.rsi = self.I(talib.RSI, self.data.Close, timeperiod=self.vwrsi_period)
        
        # Calculate SMA of volume
        self.sma_volume = self.I(talib.SMA, self.data.Volume, timeperiod=self.volume_sma_period)
        
        # Calculate VWRSI: (RSI * Volume) / SMA(Volume)
        def calculate_vwrsi():
            rsi_values = self.rsi.array
            volume_values = self.data.Volume.array
            sma_vol_values = self.sma_volume.array
            
            # Avoid division by zero
            sma_vol_values = np.where(sma_vol_values == 0, 1, sma_vol_values)
            
            # Calculate VWRSI
            vwrsi = (rsi_values * volume_values) / sma_vol_values
            return vwrsi
        
        self.vwrsi = self.I(calculate_vwrsi)
        
        # Calculate recent highs for breakout
        self.recent_high = self.I(talib.MAX, self.data.High, timeperiod=self.breakout_lookback)
        
        # Track oversold candle information
        self.oversold_candle_index = None
        self.oversold_candle_high = None
        self.oversold_candle_low = None
        
        # Track entry bar for time-based exit
        self.entry_bar = 0
        
        print("🚀 Indicators initialized successfully!")

    def next(self):
        current_bar = len(self.data) - 1
        
        # Check for oversold condition
        if self.vwrsi[-1] < self.oversold_threshold:
            self.oversold_candle_index = current_bar
            self.oversold_candle_high = self.data.High[-1]
            self.oversold_candle_low = self.data.Low[-1]
            print(f"🌙 Oversold detected! VWRSI: {self.vwrsi[-1]:.2f} at bar {current_bar}")
        
        # If we're not in a position and have an oversold signal
        if not self.position and self.oversold_candle_index is not None:
            # Check if oversold candle is recent (within 20 bars)
            if current_bar - self.oversold_candle_index <= 20:
                # Check breakout conditions
                breakout_condition = self.data.Close[-1] > self.oversold_candle_high
                volume_condition = self.data.Volume[-1] > self.sma_volume[-1]
                
                if breakout_condition and volume_condition:
                    print(f"🚀 ENTRY SIGNAL! Breakout confirmed at bar {current_bar}")
                    print(f"   Close: {self.data.Close[-1]:.2f}, Oversold High: {self.oversold_candle_high:.2f}")
                    print(f"   Volume: {self.data.Volume[-1]:.2f}, SMA Volume: {self.sma_volume[-1]:.2f}")
                    
                    # Calculate position size based on 2% risk
                    entry_price = self.data.Close[-1]
                    stop_loss = self.oversold_candle_low
                    risk_per_share = entry_price - stop_loss
                    
                    if risk_per_share > 0:
                        risk_amount = self.equity * self.risk_per_trade
                        position_size = risk_amount / risk_per_share
                        
                        # Calculate fractional position size (0-1 range)
                        max_position = self.equity / entry_price
                        fractional_size = min(position_size / max_position, 1.0)
                        
                        # Calculate take profit
                        take_profit = entry_price + (self.reward_ratio * risk_per_share)
                        
                        print(f"✨ Entry Price: {entry_price:.2f}")
                        print(f"✨ Stop Loss: {stop_loss:.2f}")
                        print(f"✨ Take Profit: {take_profit:.2f}")
                        print(f"✨ Risk per share: {risk_per_share:.2f}")
                        print(f"✨ Position size: {fractional_size:.4f}")
                        
                        # Enter long position
                        self.buy(size=fractional_size, 
                                sl=stop_loss,
                                tp=take_profit)
                        
                        # Record entry bar for time-based exit
                        self.entry_bar = current_bar
                        
                        # Reset oversold candle tracking
                        self.oversold_candle_index = None
        
        # Time-based exit
        if self.position:
            bars_held = current_bar - self.entry_bar
            if bars_held >= self.max_hold_bars:
                print(f"⏰ Time-based exit at bar {current_bar}, held for {bars_held} bars")
                self.position.close()

# Load and prepare data
print("🌙 Loading data from:", DATA_PATH)
data = pd.read_csv(DATA_PATH)

# Clean column names
data.columns = data.columns.str.strip().str.lower()

# Drop unnamed columns
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])

# Ensure proper column mapping
required_columns = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}
for old_col, new_col in required_columns.items():
    if old_col in data.columns:
        data.rename(columns={old_col: new_col}, inplace=True)

# Ensure datetime column is properly formatted
if 'datetime' in data.columns:
    data['datetime'] = pd.to_datetime(data['datetime'])
    data.set_index('datetime', inplace=True)
elif 'date' in data.columns:
    data['date'] = pd.to_datetime(data['date'])
    data.set_index('date', inplace=True)

print("✨ Data loaded successfully!")
print(f"📊 Data shape: {data.shape}")
print(f"📈 Columns: {data.columns.tolist()}")

# Run backtest
print("\n" + "="*50)
print("🚀 STARTING BACKTEST FOR VOLUMETRIC REVERSAL STRATEGY")
print("="*50 + "\n")

bt = Backtest(data, VolumetricReversal, cash=1000000, commission=.002)
stats = bt.run()

print("\n" + "="*50)
print("📊 BACKTEST RESULTS")
print("="*50)
print(stats)
print("\n" + "="*50)
print("🎯 STRATEGY DETAILS")
print("="*50)
print(stats._strategy)```