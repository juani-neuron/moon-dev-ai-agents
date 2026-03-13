import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

class VolumetricBreakout(Strategy):
    # Strategy parameters
    donchian_period = 20
    volume_sma_period = 20
    volume_multiplier = 1.5
    ema_period = 50
    risk_per_trade = 0.02  # 2% risk per trade
    reward_ratio = 2.0  # 2:1 reward to risk
    
    def init(self):
        # Clean data columns
        self.data.df.columns = self.data.df.columns.str.strip().str.lower()
        
        # Calculate indicators using TA-Lib
        print("🌙 Moon Dev: Initializing VolumetricBreakout Strategy...")
        
        # Donchian Channel (recent highs and lows)
        self.donchian_high = self.I(talib.MAX, self.data.High, timeperiod=self.donchian_period)
        self.donchian_low = self.I(talib.MIN, self.data.Low, timeperiod=self.donchian_period)
        
        # Volume indicators
        self.volume_sma = self.I(talib.SMA, self.data.Volume, timeperiod=self.volume_sma_period)
        
        # Trend filter (EMA)
        self.ema = self.I(talib.EMA, self.data.Close, timeperiod=self.ema_period)
        
        # Store previous EMA for slope calculation
        self.prev_ema = None
        
        print(f"✨ Indicators initialized: Donchian({self.donchian_period}), Volume SMA({self.volume_sma_period}), EMA({self.ema_period})")
    
    def next(self):
        current_price = self.data.Close[-1]
        current_volume = self.data.Volume[-1]
        current_high = self.data.High[-1]
        current_low = self.data.Low[-1]
        
        # Calculate volume spike condition
        if len(self.volume_sma) > 1 and self.volume_sma[-1] > 0:
            volume_ratio = current_volume / self.volume_sma[-1]
            volume_spike = volume_ratio > self.volume_multiplier
        else:
            volume_spike = False
            volume_ratio = 0
        
        # Calculate EMA slope (trend filter)
        ema_slope_up = False
        ema_slope_down = False
        
        if len(self.ema) > 1:
            current_ema = self.ema[-1]
            if self.prev_ema is not None and self.prev_ema > 0:
                ema_slope_up = current_ema > self.prev_ema
                ema_slope_down = current_ema < self.prev_ema
            self.prev_ema = current_ema
        
        # Check if we're in a trade
        if self.position:
            position = self.position
            entry_price = position.entry_price
            
            if position.is_long:
                # Calculate stop loss and take profit for long positions
                stop_loss = self.donchian_high[-2] if len(self.donchian_high) > 1 else entry_price * 0.99
                risk_per_share = entry_price - stop_loss
                take_profit = entry_price + (risk_per_share * self.reward_ratio)
                
                # Exit conditions for long
                if current_price <= stop_loss:
                    print(f"📉 Moon Dev: LONG STOP LOSS HIT! Entry: {entry_price:.2f}, Exit: {current_price:.2f}, PnL: {position.pl:.2f}")
                    self.position.close()
                elif current_price >= take_profit:
                    print(f"🎯 Moon Dev: LONG TAKE PROFIT HIT! Entry: {entry_price:.2f}, Exit: {current_price:.2f}, PnL: {position.pl:.2f}")
                    self.position.close()
                # Exit on volume divergence (optional)
                elif len(self.volume_sma) > 3 and current_volume < self.volume_sma[-1] * 0.5:
                    print(f"📊 Moon Dev: LONG EXIT - Volume divergence detected")
                    self.position.close()
                    
            elif position.is_short:
                # Calculate stop loss and take profit for short positions
                stop_loss = self.donchian_low[-2] if len(self.donchian_low) > 1 else entry_price * 1.01
                risk_per_share = stop_loss - entry_price
                take_profit = entry_price - (risk_per_share * self.reward_ratio)
                
                # Exit conditions for short
                if current_price >= stop_loss:
                    print(f"📈 Moon Dev: SHORT STOP LOSS HIT! Entry: {entry_price:.2f}, Exit: {current_price:.2f}, PnL: {position.pl:.2f}")
                    self.position.close()
                elif current_price <= take_profit:
                    print(f"🎯 Moon Dev: SHORT TAKE PROFIT HIT! Entry: {entry_price:.2f}, Exit: {current_price:.2f}, PnL: {position.pl:.2f}")
                    self.position.close()
                # Exit on volume divergence (optional)
                elif len(self.volume_sma) > 3 and current_volume < self.volume_sma[-1] * 0.5:
                    print(f"📊 Moon Dev: SHORT EXIT - Volume divergence detected")
                    self.position.close()
        
        # Entry signals (only if not in a position)
        else:
            # LONG ENTRY CONDITIONS
            long_condition = False
            if len(self.donchian_high) > 1 and len(self.ema) > 1:
                # Price closed above Donchian high (resistance breakout)
                price_above_resistance = current_price > self.donchian_high[-2]
                
                # Volume spike confirmation
                volume_confirmed = volume_spike
                
                # Trend filter (optional)
                trend_filter = current_price > self.ema[-1] and ema_slope_up
                
                long_condition = price_above_resistance and volume_confirmed and trend_filter
                
                if long_condition:
                    # Calculate position size based on risk management
                    stop_loss = self.donchian_high[-2]
                    risk_per_share = current_price - stop_loss
                    
                    if risk_per_share > 0:
                        risk_amount = self.equity * self.risk_per_trade
                        position_size = risk_amount / risk_per_share
                        position_size = int(round(position_size))
                        
                        if position_size > 0:
                            print(f"🚀🌙 MOON DEV: LONG SIGNAL DETECTED!")
                            print(f"   Price: {current_price:.2f} > Resistance: {self.donchian_high[-2]:.2f}")
                            print(f"   Volume Ratio: {volume_ratio:.2f}x (Threshold: {self.volume_multiplier}x)")
                            print(f"   Trend: Price above EMA & EMA rising")
                            print(f"   Position Size: {position_size} shares")
                            print(f"   Stop Loss: {stop_loss:.2f}, Risk: {risk_per_share:.2f} per share")
                            
                            self.buy(size=position_size)
            
            # SHORT ENTRY CONDITIONS
            short_condition = False
            if len(self.donchian_low) > 1 and len(self.ema) > 1:
                # Price closed below Donchian low (support breakdown)
                price_below_support = current_price < self.donchian_low[-2]
                
                # Volume spike confirmation
                volume_confirmed = volume_spike
                
                # Trend filter (optional)
                trend_filter = current_price < self.ema[-1] and ema_slope_down
                
                short_condition = price_below_support and volume_confirmed and trend_filter
                
                if short_condition:
                    # Calculate position size based on risk management
                    stop_loss = self.donchian_low[-2]
                    risk_per_share = stop_loss - current_price
                    
                    if risk_per_share > 0:
                        risk_amount = self.equity * self.risk_per_trade
                        position_size = risk_amount / risk_per_share
                        position_size = int(round(position_size))
                        
                        if position_size > 0:
                            print(f"📉🌙 MOON DEV: SHORT SIGNAL DETECTED!")
                            print(f"   Price: {current_price:.2f} < Support: {self.donchian_low[-2]:.2f}")
                            print(f"   Volume Ratio: {volume_ratio:.2f}x (Threshold: {self.volume_multiplier}x)")
                            print(f"   Trend: Price below EMA & EMA falling")
                            print(f"   Position Size: {position_size} shares")
                            print(f"   Stop Loss: {stop_loss:.2f}, Risk: {risk_per_share:.2f} per share")
                            
                            self.sell(size=position_size)

# Data loading and preparation
print("🌙 Moon Dev: Loading BTC-USD data...")
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
data_path = os.path.join(project_root, "src", "data", "rbi", "BTC-USD-15m-train.csv")

# Read and clean the data
data = pd.read_csv(data_path)
data.columns = data.columns.str.strip().str.lower()

# Drop any unnamed columns
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])

# Convert datetime and set as index
if 'datetime' in data.columns:
    data['datetime'] = pd.to_datetime(data['datetime'])
    data.set_index('datetime', inplace=True)
elif 'date' in data.columns:
    data['date'] = pd.to_datetime(data['date'])
    data.set_index('date', inplace=True)

# Ensure proper column names (capital first letter for backtesting.py)
data = data.rename(columns={
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume'
})

# Ensure all required columns are present
required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
for col in required_cols:
    if col not in data.columns:
        raise ValueError(f"Missing required column: {col}")

print(f"📊 Data loaded successfully: {len(data)} rows")
print(f"   Date range: {data.index[0]} to {data.index[-1]}")
print(f"   Columns: {list(data.columns)}")

# Run backtest
print("\n🌙✨ MOON DEV BACKTEST INITIATED ✨🌙")
print("=" * 50)

bt = Backtest(data, VolumetricBreakout, cash=1000000, commission=.002)
stats = bt.run()

print("\n" + "=" * 50)
print("🌙✨ MOON DEV BACKTEST COMPLETE ✨🌙")
print("=" * 50 + "\n")

print(stats)
print("\n" + "=" * 50)
print("STRATEGY DETAILS:")
print("=" * 50)
print(stats._strategy)