```python
import pandas as pd
import talib
import numpy as np
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import os

class BandStochasticBreakout(Strategy):
    bb_period = 20
    bb_dev = 2.0
    stoch_k = 14
    stoch_d = 3
    stoch_slow = 3
    overbought = 80
    oversold = 20
    risk_per_trade = 0.01  # 1% risk per trade
    
    def init(self):
        close = self.data.Close
        
        # Calculate Bollinger Bands using talib
        self.bb_upper = self.I(talib.BBANDS, close, timeperiod=self.bb_period, 
                               nbdevup=self.bb_dev, nbdevdn=self.bb_dev, matype=0)[0]
        self.bb_middle = self.I(talib.BBANDS, close, timeperiod=self.bb_period, 
                                nbdevup=self.bb_dev, nbdevdn=self.bb_dev, matype=0)[1]
        self.bb_lower = self.I(talib.BBANDS, close, timeperiod=self.bb_period, 
                               nbdevup=self.bb_dev, nbdevdn=self.bb_dev, matype=0)[2]
        
        # Calculate Stochastic Oscillator using talib
        self.stoch_k_line = self.I(talib.STOCH, self.data.High, self.data.Low, close,
                                   fastk_period=self.stoch_k, slowk_period=self.stoch_slow,
                                   slowk_matype=0, slowd_period=self.stoch_d, slowd_matype=0)[0]
        self.stoch_d_line = self.I(talib.STOCH, self.data.High, self.data.Low, close,
                                   fastk_period=self.stoch_k, slowk_period=self.stoch_slow,
                                   slowk_matype=0, slowd_period=self.stoch_d, slowd_matype=0)[1]
        
        # Calculate recent swing highs and lows for stop loss
        self.swing_high = self.I(talib.MAX, self.data.High, timeperiod=5)
        self.swing_low = self.I(talib.MIN, self.data.Low, timeperiod=5)
        
        print("🌙 Moon Dev's BandStochastic Breakout Strategy Initialized! ✨")
        print(f"⚙️  Settings: BB Period={self.bb_period}, Stoch %K={self.stoch_k}")
        print(f"📊 Risk per trade: {self.risk_per_trade*100}% 🌙")
        
    def next(self):
        current_idx = len(self.data) - 1
        if current_idx < max(self.bb_period, self.stoch_k) + 5:
            return
            
        close = self.data.Close[-1]
        bb_upper = self.bb_upper[-1]
        bb_middle = self.bb_middle[-1]
        bb_lower = self.bb_lower[-1]
        stoch_k = self.stoch_k_line[-1]
        prev_stoch_k = self.stoch_k_line[-2] if current_idx > 0 else stoch_k
        
        # Calculate band position (0 = lower band, 1 = upper band)
        if bb_upper != bb_lower:
            band_position = (close - bb_lower) / (bb_upper - bb_lower)
        else:
            band_position = 0.5
            
        # Check if price is within middle 50% of bands
        in_middle_band = 0.25 <= band_position <= 0.75
        
        # Calculate position size based on risk management
        equity = self.equity
        risk_amount = equity * self.risk_per_trade
        
        # Long entry conditions
        if not self.position and in_middle_band:
            # Long signal
            if (close > bb_upper and 
                stoch_k > self.oversold and prev_stoch_k <= self.oversold and
                stoch_k > prev_stoch_k):
                
                # Calculate stop loss for long
                sl_middle = bb_middle
                sl_swing = self.swing_low[-1]
                stop_loss = max(sl_middle, sl_swing)
                
                risk_per_unit = close - stop_loss
                if risk_per_unit <= 0:
                    return
                    
                position_size = risk_amount / risk_per_unit
                position_size = int(round(position_size))
                
                if position_size > 0:
                    print(f"🚀 MOON SHOT! Long Entry Signal Detected! 🌙")
                    print(f"📈 Price: {close:.2f}, BB Upper: {bb_upper:.2f}")
                    print(f"📊 Stoch %K: {stoch_k:.2f} (crossed above {self.oversold})")
                    print(f"🎯 Entry at next open, Position size: {position_size}")
                    print(f"🛡️  Stop Loss: {stop_loss:.2f}, Risk: {risk_per_unit:.2f} ✨")
                    
                    # Enter long on next candle
                    self.buy(size=position_size, sl=stop_loss)
                    
                    # Calculate take profit levels
                    tp1_price = close + risk_per_unit  # 1:1 R:R
                    self.tp1 = tp1_price
                    
            # Short signal
            elif (close < bb_lower and 
                  stoch_k < self.overbought and prev_stoch_k >= self.overbought and
                  stoch_k < prev_stoch_k):
                
                # Calculate stop loss for short
                sl_middle = bb_middle
                sl_swing = self.swing_high[-1]
                stop_loss = min(sl_middle, sl_swing)
                
                risk_per_unit = stop_loss - close
                if risk_per_unit <= 0:
                    return
                    
                position_size = risk_amount / risk_per_unit
                position_size = int(round(position_size))
                
                if position_size > 0:
                    print(f"🌒 DARK MOON! Short Entry Signal Detected! 🌙")
                    print(f"📉 Price: {close:.2f}, BB Lower: {bb_lower:.2f}")
                    print(f"📊 Stoch %K: {stoch_k:.2f} (crossed below {self.overbought})")
                    print(f"🎯 Entry at next open, Position size: {position_size}")
                    print(f"🛡️  Stop Loss: {stop_loss:.2f}, Risk: {risk_per_unit:.2f} ✨")
                    
                    # Enter short on next candle
                    self.sell(size=position_size, sl=stop_loss)
                    
                    # Calculate take profit levels
                    tp1_price = close - risk_per_unit  # 1:1 R:R
                    self.tp1 = tp1_price
        
        # Manage existing positions
        if self.position:
            entry_price = self.position.entry_price
            is_long = self.position.is_long
            
            if not hasattr(self, 'tp1_hit'):
                self.tp1_hit = False
                
            # Check for TP1 hit
            if not self.tp1_hit:
                if is_long and self.data.Close[-1] >= self.tp1:
                    print(f"💰 TP1 HIT! Taking partial profits! 🌙")
                    print(f"🎯 Target: {self.tp1:.2f}, Current: {self.data.Close[-1]:.2f}")
                    
                    # Close 50% of position at TP1
                    close_size = int(round(self.position.size * 0.5))
                    self.position.close(portion=0.5)
                    self.tp1_hit = True
                    
                    # Move stop to breakeven for remaining position
                    if self.position:
                        self.position.sl = entry_price
                        print(f"🔄 Stop moved to breakeven: {entry_price:.2f} ✨")
                        
                elif not is_long and self.data.Close[-1] <= self.tp1:
                    print(f"💰 TP1 HIT! Taking partial profits! 🌙")
                    print(f"🎯 Target: {self.tp1:.2f}, Current: {self.data.Close[-1]:.2f}")
                    
                    # Close 50% of position at TP1
                    close_size = int(round(self.position.size * 0.5))
                    self.position.close(portion=0.5)
                    self.tp1_hit = True
                    
                    # Move stop to breakeven for remaining position
                    if self.position:
                        self.position.sl = entry_price
                        print(f"🔄 Stop moved to breakeven: {entry_price:.2f} ✨")
            
            # Check for TP2 exit conditions (for remaining position)
            if self.tp1_hit and self.position:
                current_close = self.data.Close[-1]
                current_stoch = self.stoch_k_line[-1]
                
                if is_long:
                    # Exit when price closes back inside bands OR stochastic reaches overbought
                    if current_close <= bb_upper or current_stoch >= self.overbought:
                        print(f"🌕 FULL MOON PROFIT! Exiting remaining long position! 🌙")
                        print(f"📊 Exit reason: {'Price back in bands' if current_close <= bb_upper else 'Stoch overbought'}")
                        self.position.close()
                        delattr(self, 'tp1_hit')
                        
                else:  # Short position
                    # Exit when price closes back inside bands OR stochastic reaches oversold
                    if current_close >= bb_lower or current_stoch <= self.oversold:
                        print(f"🌑 NEW MOON PROFIT! Exiting remaining short position! 🌙")
                        print(f"📊 Exit reason: {'Price back in bands' if current_close >= bb_lower else 'Stoch oversold'}")
                        self.position.close()
                        delattr(self, 'tp1_hit')

# Data preparation
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
data_path = os.path.join(project_root, "src/data/rbi/BTC-USD-15m-train.csv")

print(f"📂 Loading data from: {data_path} 🌙")
data = pd.read_csv(data_path)

# Clean column names
data.columns = data.columns.str.strip().str.lower()

# Drop unnamed columns
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])

# Rename columns to match Backtesting.py requirements
column_mapping = {
    'open': 'Open',
    'high': 'High', 
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume'
}

for old_col, new_col in column_mapping.items():
    if old_col in data.columns:
        data = data.rename(columns={old_col: new_col})

# Ensure datetime is proper
if 'datetime' in data.columns:
    data['datetime'] = pd.to_datetime(data['datetime'])
    data = data.set_index('datetime')

print(f"📊 Data loaded successfully! Shape: {data.shape} 🌙")
print(f"📅 Date range: {data.index[0]} to {data.index[-1]} ✨")
print(f"🔍 Columns: {list(data.columns)}")

# Run backtest
bt = Backtest(data, BandStochasticBreakout, cash=1000000, commission=.002)

print("\n" + "="*50)
print("🚀 STARTING MOON DEV BACKTEST... 🌙")
print("="*50 + "\n")

stats = bt.run()
print(stats)
print(stats._strategy)