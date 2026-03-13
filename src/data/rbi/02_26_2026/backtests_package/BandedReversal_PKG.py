import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

class BandedReversal(Strategy):
    rsi_period = 14
    bb_period = 20
    bb_std = 2
    trend_ema_period = 50
    risk_per_trade = 0.02
    
    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        
        print("🌙 Initializing BandedReversal Strategy...")
        print(f"📊 RSI Period: {self.rsi_period}")
        print(f"📈 BB Period: {self.bb_period}, Std: {self.bb_std}")
        print(f"📉 Trend EMA Period: {self.trend_ema_period}")
        print(f"💰 Risk per Trade: {self.risk_per_trade*100}%")
        
        self.rsi = self.I(talib.RSI, close, timeperiod=self.rsi_period)
        self.rsi_sma = self.I(talib.SMA, self.rsi, timeperiod=self.bb_period)
        self.rsi_std = self.I(talib.STDDEV, self.rsi, timeperiod=self.bb_period)
        self.rsi_upper = self.rsi_sma + (self.rsi_std * self.bb_std)
        self.rsi_lower = self.rsi_sma - (self.rsi_std * self.bb_std)
        self.trend_ema = self.I(talib.EMA, close, timeperiod=self.trend_ema_period)
        
        print("✨ Indicators calculated successfully!")
        
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.position_size = 0
        
    def next(self):
        current_close = self.data.Close[-1]
        current_rsi = self.rsi[-1]
        current_rsi_upper = self.rsi_upper[-1]
        current_rsi_lower = self.rsi_lower[-1]
        current_ema = self.trend_ema[-1]
        
        prev_rsi = self.rsi[-2] if len(self.rsi) > 1 else current_rsi
        prev_rsi_upper = self.rsi_upper[-2] if len(self.rsi_upper) > 1 else current_rsi_upper
        prev_rsi_lower = self.rsi_lower[-2] if len(self.rsi_lower) > 1 else current_rsi_lower
        
        if not self.position:
            self.check_entries(current_close, current_rsi, current_ema, 
                             prev_rsi, prev_rsi_upper, prev_rsi_lower)
        else:
            self.check_exits(current_rsi, current_rsi_upper, current_rsi_lower)
    
    def check_entries(self, close, rsi, ema, prev_rsi, prev_rsi_upper, prev_rsi_lower):
        account_equity = self.equity
        
        if close > ema:
            if prev_rsi < prev_rsi_lower and rsi > self.rsi_lower[-1]:
                print(f"🚀 LONG SIGNAL DETECTED!")
                print(f"   📈 Price {close:.2f} > EMA {ema:.2f}")
                print(f"   📊 RSI crossed above lower band: {prev_rsi:.2f} -> {rsi:.2f}")
                
                atr = talib.ATR(self.data.High, self.data.Low, self.data.Close, timeperiod=14)[-1]
                stop_loss_price = self.data.Low[-1] - (atr * 1.5)
                risk_amount = account_equity * self.risk_per_trade
                risk_per_share = close - stop_loss_price
                
                if risk_per_share > 0:
                    self.position_size = int(round(risk_amount / risk_per_share))
                    if self.position_size > 0:
                        self.buy(size=self.position_size)
                        self.entry_price = close
                        self.stop_loss = stop_loss_price
                        print(f"   💰 Entry: {close:.2f}, Stop: {stop_loss_price:.2f}")
                        print(f"   📦 Position Size: {self.position_size} units")
        
        elif close < ema:
            if prev_rsi > prev_rsi_upper and rsi < self.rsi_upper[-1]:
                print(f"📉 SHORT SIGNAL DETECTED!")
                print(f"   📉 Price {close:.2f} < EMA {ema:.2f}")
                print(f"   📊 RSI crossed below upper band: {prev_rsi:.2f} -> {rsi:.2f}")
                
                atr = talib.ATR(self.data.High, self.data.Low, self.data.Close, timeperiod=14)[-1]
                stop_loss_price = self.data.High[-1] + (atr * 1.5)
                risk_amount = account_equity * self.risk_per_trade
                risk_per_share = stop_loss_price - close
                
                if risk_per_share > 0:
                    self.position_size = int(round(risk_amount / risk_per_share))
                    if self.position_size > 0:
                        self.sell(size=self.position_size)
                        self.entry_price = close
                        self.stop_loss = stop_loss_price
                        print(f"   💰 Entry: {close:.2f}, Stop: {stop_loss_price:.2f}")
                        print(f"   📦 Position Size: {self.position_size} units")
    
    def check_exits(self, rsi, rsi_upper, rsi_lower):
        if self.position.is_long:
            if rsi > rsi_upper:
                print(f"✅ EXIT LONG: RSI {rsi:.2f} > Upper Band {rsi_upper:.2f}")
                self.position.close()
            elif self.data.Close[-1] < self.stop_loss:
                print(f"🛑 STOP LOSS HIT for LONG at {self.data.Close[-1]:.2f}")
                self.position.close()
        
        elif self.position.is_short:
            if rsi < rsi_lower:
                print(f"✅ EXIT SHORT: RSI {rsi:.2f} < Lower Band {rsi_lower:.2f}")
                self.position.close()
            elif self.data.Close[-1] > self.stop_loss:
                print(f"🛑 STOP LOSS HIT for SHORT at {self.data.Close[-1]:.2f}")
                self.position.close()

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
data_path = os.path.join(project_root, "src", "data", "rbi", "BTC-USD-15m-train.csv")

print(f"🌙 Loading data from: {data_path}")
data = pd.read_csv(data_path)

data.columns = data.columns.str.strip().str.lower()
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])

column_mapping = {
    'open': 'Open',
    'high': 'High', 
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume',
    'datetime': 'Open'
}

for old_col, new_col in column_mapping.items():
    if old_col in data.columns:
        data = data.rename(columns={old_col: new_col})

if 'Open' not in data.columns and 'datetime' in data.columns:
    data = data.rename(columns={'datetime': 'Open'})

data['Open'] = pd.to_datetime(data['Open'])
data = data.set_index('Open')

required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
for col in required_cols:
    if col not in data.columns:
        raise ValueError(f"Missing required column: {col}")

print("✨ Data loaded successfully!")
print(f"📅 Date Range: {data.index.min()} to {data.index.max()}")
print(f"📊 Data Shape: {data.shape}")

bt = Backtest(data, BandedReversal, cash=1000000, commission=.002)
print("🚀 Running backtest...")
stats = bt.run()
print(stats)
print(stats._strategy)