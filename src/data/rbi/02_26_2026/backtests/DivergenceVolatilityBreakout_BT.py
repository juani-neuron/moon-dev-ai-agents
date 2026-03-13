```python
import pandas as pd
import talib
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import numpy as np
import os

class DivergenceVolatilityBreakout(Strategy):
    # Parameters
    rsi_period = 14
    kc_ema_period = 20
    kc_atr_period = 20
    kc_multiplier = 1.5
    bb_period = 20
    bb_std = 2
    bb_expansion_lookback = 10
    risk_per_trade = 0.01
    atr_stop_multiple = 1.5
    
    def init(self):
        # Clean data
        self.data.df.columns = [col.strip().lower() for col in self.data.df.columns]
        
        # Calculate RSI
        self.rsi = self.I(talib.RSI, self.data.Close, timeperiod=self.rsi_period)
        
        # Calculate ATR for Keltner Channel
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, 
                         timeperiod=self.kc_atr_period)
        
        # Calculate Keltner Channel
        self.ema = self.I(talib.EMA, self.data.Close, timeperiod=self.kc_ema_period)
        self.kc_upper = self.ema + (self.atr * self.kc_multiplier)
        self.kc_lower = self.ema - (self.atr * self.kc_multiplier)
        
        # Calculate Bollinger Bands
        self.bb_upper, self.bb_middle, self.bb_lower = self.I(
            lambda close: talib.BBANDS(close, timeperiod=self.bb_period, nbdevup=self.bb_std, 
                                      nbdevdn=self.bb_std, matype=0),
            self.data.Close
        )
        
        # Calculate BB width for expansion detection
        self.bb_width = self.bb_upper - self.bb_lower
        self.bb_width_avg = self.I(talib.SMA, self.bb_width, timeperiod=self.bb_expansion_lookback)
        
        # Track swing lows for divergence detection
        self.price_lows = []
        self.rsi_lows = []
        self.swing_lookback = 20
        
        # Initialize trade tracking
        self.entry_price = None
        self.stop_loss = None
        
    def next(self):
        current_idx = len(self.data) - 1
        
        if current_idx < max(self.swing_lookback, self.bb_expansion_lookback, self.kc_ema_period):
            return
            
        # Update swing lows
        self._update_swing_lows(current_idx)
        
        # Check if we're in a position
        if self.position:
            self._manage_position(current_idx)
        else:
            self._check_entry_signal(current_idx)
    
    def _update_swing_lows(self, idx):
        """Update swing low arrays for divergence detection"""
        # Find recent price low
        price_window = self.data.Low[idx-self.swing_lookback:idx+1]
        if len(price_window) > 0 and self.data.Low[idx] == min(price_window):
            self.price_lows.append((idx, self.data.Low[idx]))
            if len(self.price_lows) > 10:  # Keep last 10 lows
                self.price_lows.pop(0)
        
        # Find recent RSI low
        rsi_window = self.rsi[idx-self.swing_lookback:idx+1]
        if len(rsi_window) > 0 and self.rsi[idx] == min(rsi_window):
            self.rsi_lows.append((idx, self.rsi[idx]))
            if len(self.rsi_lows) > 10:  # Keep last 10 lows
                self.rsi_lows.pop(0)
    
    def _check_divergence(self, current_idx):
        """Check for bullish divergence between price and RSI"""
        if len(self.price_lows) < 2 or len(self.rsi_lows) < 2:
            return False
            
        # Get the two most recent swing lows
        price_low_2_idx, price_low_2 = self.price_lows[-1]
        price_low_1_idx, price_low_1 = self.price_lows[-2]
        
        rsi_low_2_idx, rsi_low_2 = self.rsi_lows[-1]
        rsi_low_1_idx, rsi_low_1 = self.rsi_lows[-2]
        
        # Ensure we're looking at recent lows
        if (current_idx - price_low_2_idx > 50) or (current_idx - rsi_low_2_idx > 50):
            return False
            
        # Check for bullish divergence: price makes lower/equal low, RSI makes higher low
        price_condition = price_low_2 <= price_low_1  # Lower or equal low
        rsi_condition = rsi_low_2 > rsi_low_1  # Higher low
        
        return price_condition and rsi_condition
    
    def _check_volatility_expansion(self):
        """Check if Bollinger Bands are expanding"""
        if len(self.bb_width) < self.bb_expansion_lookback:
            return False
        
        current_width = self.bb_width[-1]
        avg_width = self.bb_width_avg[-1]
        
        # Check if current width is above average (expanding)
        return current_width > avg_width
    
    def _check_entry_signal(self, idx):
        """Check all entry conditions"""
        # Condition 1: Bullish Divergence 🌙
        divergence = self._check_divergence(idx)
        if not divergence:
            return
        
        # Condition 2: Volatility Expansion ✨
        volatility_expanding = self._check_volatility_expansion()
        if not volatility_expanding:
            return
        
        # Condition 3: Keltner Channel Breakout 🚀
        breakout = self.data.Close[-1] > self.kc_upper[-1]
        if not breakout:
            return
        
        # Condition 4: Strong bullish candle (not doji)
        candle_body = abs(self.data.Close[-1] - self.data.Open[-1])
        candle_range = self.data.High[-1] - self.data.Low[-1]
        if candle_range == 0 or candle_body / candle_range < 0.3:  # Avoid doji candles
            return
        
        # All conditions met! Moon Dev entry signal! 🌕
        print(f"🌙 MOON DEV SIGNAL DETECTED at {self.data.index[-1]}")
        print(f"   ✨ Divergence: {divergence}, Volatility: {volatility_expanding}, Breakout: {breakout}")
        
        # Calculate position size with risk management
        entry_price = self.data.Close[-1]
        stop_loss_price = entry_price - (self.atr[-1] * self.atr_stop_multiple)
        risk_per_share = entry_price - stop_loss_price
        
        if risk_per_share <= 0:
            return
            
        risk_amount = self.equity * self.risk_per_trade
        position_size = risk_amount / risk_per_share
        
        # Convert to integer units (backtesting.py requirement)
        position_size = int(round(position_size))
        
        if position_size <= 0:
            return
            
        # Store trade info
        self.entry_price = entry_price
        self.stop_loss = stop_loss_price
        
        # Enter long position
        self.buy(size=position_size, sl=stop_loss_price)
        print(f"   🚀 ENTER LONG: {position_size} units at ${entry_price:.2f}")
        print(f"   ⚠️  STOP LOSS: ${stop_loss_price:.2f} (Risk: ${risk_per_share:.2f} per unit)")
    
    def _manage_position(self, idx):
        """Manage open position"""
        if not self.position:
            return
            
        # Exit condition: Close below Upper Keltner Channel
        exit_signal = self.data.Close[-1] < self.kc_upper[-1]
        
        if exit_signal:
            print(f"🌙 EXIT SIGNAL: Price closed below Upper Keltner at {self.data.index[-1]}")
            print(f"   📉 Exit price: ${self.data.Close[-1]:.2f}")
            self.position.close()

# Load and prepare data
data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                         "src", "data", "rbi", "BTC-USD-15m-train.csv")

# Load data with proper handling
data = pd.read_csv(data_path)

# Clean column names
data.columns = data.columns.str.strip().str.lower()

# Drop any unnamed columns
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])

# Map to required columns (Backtesting.py expects specific case)
column_mapping = {
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume'
}

# Rename columns
data = data.rename(columns={k: v for k, v in column_mapping.items() if k in data.columns})

# Ensure datetime is properly formatted
if 'datetime' in data.columns:
    data['datetime'] = pd.to_datetime(data['datetime'])
    data = data.set_index('datetime')
elif 'date' in data.columns:
    data['date'] = pd.to_datetime(data['date'])
    data = data.set_index('date')

print("🌙 MOON DEV BACKTEST INITIALIZED")
print(f"📊 Data shape: {data.shape}")
print(f"📈 Columns: {data.columns.tolist()}")
print(f"📅 Date range: {data.index[0]} to {data.index[-1]}")
print("-" * 50)

# Run backtest
bt = Backtest(data, DivergenceVolatilityBreakout, 
              cash=1000000, 
              commission=0.001,  # 0.1% commission
              exclusive_orders=True)

# Run and print stats
stats = bt.run()
print(stats)
print(stats._strategy)```