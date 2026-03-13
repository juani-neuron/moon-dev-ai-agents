import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

class VolatilityDivergence(Strategy):
    atr_period = 14
    ema_fast_period = 50
    ema_slow_period = 200
    swing_period = 10
    risk_per_trade = 0.01
    rr_ratio = 2
    
    def init(self):
        print("🌙 Moon Dev's Volatility Divergence Backtest Initializing...")
        
        # Clean data columns
        self.data.df.columns = self.data.df.columns.str.strip().str.lower()
        self.data.df = self.data.df.drop(columns=[col for col in self.data.df.columns if 'unnamed' in col])
        
        # Required columns mapping
        required_cols = {'open': 'Open', 'high': 'High', 'low': 'Low', 
                        'close': 'Close', 'volume': 'Volume'}
        for old, new in required_cols.items():
            if old in self.data.df.columns:
                self.data.df[new] = self.data.df[old]
        
        print("✨ Data cleaning complete. Starting indicator calculation...")
        
        # Calculate indicators using talib with self.I()
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, 
                         timeperiod=self.atr_period, name='ATR')
        
        self.ema_fast = self.I(talib.EMA, self.data.Close, timeperiod=self.ema_fast_period, 
                              name='EMA_50')
        
        self.ema_slow = self.I(talib.EMA, self.data.Close, timeperiod=self.ema_slow_period, 
                              name='EMA_200')
        
        # Calculate swing highs and lows
        self.swing_high = self.I(talib.MAX, self.data.High, timeperiod=self.swing_period, 
                                name='Swing_High')
        self.swing_low = self.I(talib.MIN, self.data.Low, timeperiod=self.swing_period, 
                               name='Swing_Low')
        
        # For divergence detection
        self.higher_low = np.zeros(len(self.data.Close))
        self.lower_atr = np.zeros(len(self.data.Close))
        
        print("🚀 Indicators calculated. Ready for backtest execution!")
    
    def next(self):
        # Skip early bars where indicators aren't ready
        if len(self.data.Close) < max(self.atr_period * 2, self.ema_fast_period, self.swing_period * 3):
            return
        
        current_idx = len(self.data.Close) - 1
        
        # Calculate recent swing points
        lookback = min(100, current_idx)
        if lookback < self.swing_period * 3:
            return
        
        # Find recent swing low (higher low detection)
        recent_lows = []
        recent_atrs = []
        for i in range(current_idx - lookback, current_idx - 5):
            if self.data.Low[i] <= self.swing_low[i]:
                recent_lows.append((i, self.data.Low[i], self.atr[i]))
        
        # Find recent swing high for breakout level
        recent_highs = []
        for i in range(current_idx - lookback, current_idx - 5):
            if self.data.High[i] >= self.swing_high[i]:
                recent_highs.append((i, self.data.High[i]))
        
        if len(recent_lows) < 2 or len(recent_highs) < 1:
            return
        
        # Get the two most recent swing lows
        swing_low1_idx, swing_low1_price, swing_low1_atr = recent_lows[-1]
        swing_low2_idx, swing_low2_price, swing_low2_atr = recent_lows[-2]
        
        # Get the most recent swing high between these lows
        swing_high_price = 0
        for idx, price in recent_highs:
            if swing_low2_idx < idx < swing_low1_idx:
                swing_high_price = max(swing_high_price, price)
        
        if swing_high_price == 0:
            return
        
        # Check for hidden bullish divergence conditions
        price_higher_low = swing_low1_price > swing_low2_price
        atr_lower_low = swing_low1_atr < swing_low2_atr
        
        # Trend filter
        in_uptrend = self.data.Close[current_idx] > self.ema_fast[current_idx]
        
        # Breakout condition
        breakout_trigger = self.data.Close[current_idx] > swing_high_price
        
        # Entry logic
        if not self.position:
            if (price_higher_low and atr_lower_low and in_uptrend and breakout_trigger):
                print(f"🎯 Moon Dev Signal Detected! Hidden Bullish Divergence at {self.data.index[-1]}")
                print(f"   Price HL: {swing_low1_price:.2f} > {swing_low2_price:.2f}")
                print(f"   ATR LL: {swing_low1_atr:.4f} < {swing_low2_atr:.4f}")
                print(f"   Breakout above: {swing_high_price:.2f}")
                
                # Calculate risk management
                stop_loss_price = swing_low1_price - (1.5 * self.atr[current_idx])
                risk_per_share = self.data.Close[current_idx] - stop_loss_price
                
                if risk_per_share <= 0:
                    print("⚠️ Risk calculation error. Skipping trade.")
                    return
                
                # Calculate position size with 1% risk
                risk_amount = self.equity * self.risk_per_trade
                position_size = risk_amount / risk_per_share
                
                # Ensure integer position size
                position_size = int(round(position_size))
                
                if position_size > 0:
                    # Calculate take profit
                    take_profit_price = self.data.Close[current_idx] + (self.rr_ratio * risk_per_share)
                    
                    print(f"📊 Entry: {self.data.Close[current_idx]:.2f}")
                    print(f"🛑 Stop Loss: {stop_loss_price:.2f}")
                    print(f"🎯 Take Profit: {take_profit_price:.2f}")
                    print(f"💰 Position Size: {position_size} shares")
                    print(f"📈 Risk/Reward: 1:{self.rr_ratio}")
                    
                    # Enter long position
                    self.buy(size=position_size, 
                            sl=stop_loss_price,
                            tp=take_profit_price)
        
        # Check for exit conditions on existing position
        elif self.position.is_long:
            # Trailing stop logic (optional - can be commented out if using fixed TP/SL)
            if self.data.Close[current_idx] > self.position.entry_price:
                new_stop = self.data.Close[current_idx] - (2 * self.atr[current_idx])
                if new_stop > self.position.sl:
                    self.position.sl = new_stop
                    print(f"🌙 Trailing stop updated to: {new_stop:.2f}")

# Data loading and cleaning
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
data_path = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")

print(f"🌙 Loading data from: {data_path}")

try:
    data = pd.read_csv(data_path)
    
    # Clean column names
    data.columns = data.columns.str.strip().str.lower()
    
    # Drop unnamed columns
    data = data.drop(columns=[col for col in data.columns if 'unnamed' in col])
    
    # Ensure required columns exist
    required_mapping = {
        'open': 'Open',
        'high': 'High', 
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume',
        'datetime': 'Date'
    }
    
    for old_col, new_col in required_mapping.items():
        if old_col in data.columns:
            data[new_col] = data[old_col]
    
    # Convert to datetime if needed
    if 'Date' in data.columns:
        data['Date'] = pd.to_datetime(data['Date'])
        data.set_index('Date', inplace=True)
    
    # Ensure all required columns exist
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in required_cols:
        if col not in data.columns:
            raise ValueError(f"Missing required column: {col}")
    
    print(f"✨ Data loaded successfully! Shape: {data.shape}")
    print(f"📅 Date range: {data.index[0]} to {data.index[-1]}")
    
    # Run backtest
    bt = Backtest(data, VolatilityDivergence, cash=1000000, commission=.002)
    
    print("🚀 Starting Moon Dev's Volatility Divergence Backtest...")
    print("=" * 60)
    
    stats = bt.run()
    
    print("=" * 60)
    print("🌙 BACKTEST COMPLETE - FINAL STATISTICS")
    print("=" * 60)
    
    # Print detailed statistics
    print(stats)
    print("\n" + "=" * 60)
    print("📊 STRATEGY DETAILS")
    print("=" * 60)
    print(stats._strategy)
    
except FileNotFoundError:
    print(f"❌ ERROR: Data file not found at {data_path}")
    print("Please ensure the file exists and the path is correct.")
except Exception as e:
    print(f"❌ ERROR: {str(e)}")
    print("Please check the data format and columns.")