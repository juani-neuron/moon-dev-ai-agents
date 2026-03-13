import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
from backtesting.lib import crossover, crossunder
import os

# Set up paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")

class BandShiftReversion(Strategy):
    # Strategy parameters
    bb_period = 20
    bb_std = 2
    atr_period = 14
    risk_percent = 0.01  # 1% risk per trade
    stop_atr_multiple = 2
    trail_atr_multiple = 2
    
    def init(self):
        # 🌙 Moon Dev Debug: Strategy Initialization
        print("🌙 BandShiftReversion Strategy Initializing...")
        print(f"✨ Parameters: BB({self.bb_period}, {self.bb_std}), ATR({self.atr_period})")
        print(f"✨ Risk Management: {self.risk_percent*100}% risk per trade")
        
        # Clean column names
        self.data.df.columns = self.data.df.columns.str.strip().str.lower()
        
        # Calculate Bollinger Bands using talib
        self.bb_middle = self.I(talib.SMA, self.data.Close, timeperiod=self.bb_period)
        self.bb_upper = self.I(talib.BBANDS, self.data.Close, 
                              timeperiod=self.bb_period, nbdevup=self.bb_std, nbdevdn=self.bb_std)[0]
        self.bb_lower = self.I(talib.BBANDS, self.data.Close, 
                              timeperiod=self.bb_period, nbdevup=self.bb_std, nbdevdn=self.bb_std)[2]
        
        # Calculate 20-period SMA (same as BB middle but we'll use for clarity)
        self.sma_20 = self.I(talib.SMA, self.data.Close, timeperiod=20)
        
        # Calculate ATR for stop loss and position sizing
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, 
                         timeperiod=self.atr_period)
        
        # Track highest high since entry for trailing stop
        self.highest_high = None
        
        print("🚀 Indicators calculated successfully!")
    
    def next(self):
        # Current index
        current_idx = len(self.data) - 1
        
        # Skip if we don't have enough data
        if current_idx < max(self.bb_period, self.atr_period):
            return
        
        # Get current values
        current_close = self.data.Close[-1]
        current_low = self.data.Low[-1]
        current_high = self.data.High[-1]
        bb_lower_current = self.bb_lower[-1]
        sma_20_current = self.sma_20[-1]
        atr_current = self.atr[-1]
        
        # 🌙 Moon Dev Debug: Print current market conditions
        if current_idx % 100 == 0:
            print(f"🌙 Current Price: {current_close:.2f}, BB Lower: {bb_lower_current:.2f}, "
                  f"SMA20: {sma_20_current:.2f}, ATR: {atr_current:.2f}")
        
        # If we have an open position, manage it
        if self.position:
            position = self.position
            
            # Update highest high since entry
            if self.highest_high is None:
                self.highest_high = current_high
            else:
                self.highest_high = max(self.highest_high, current_high)
            
            # Calculate trailing stop price
            trail_stop_price = self.highest_high - (self.trail_atr_multiple * atr_current)
            
            # Exit conditions:
            # 1. Price touches or crosses above the middle band (SMA20)
            exit_condition_1 = current_close >= sma_20_current
            
            # 2. Trailing stop hit
            exit_condition_2 = current_close <= trail_stop_price
            
            if exit_condition_1 or exit_condition_2:
                reason = "Middle Band Touch" if exit_condition_1 else "Trailing Stop"
                print(f"✅ EXIT SIGNAL: {reason} | Price: {current_close:.2f} | "
                      f"Profit: {position.pl:.2f} ({position.pl_pct:.2%})")
                self.position.close()
                self.highest_high = None
                return
        
        # ENTRY CONDITIONS (only if no open position)
        if not self.position:
            # Reset highest high tracker
            self.highest_high = None
            
            # Condition 1: Price touches or crosses below the lower Bollinger Band
            condition_1 = current_low <= bb_lower_current
            
            # Condition 2: Lower Bollinger Band is ABOVE the 20-period SMA
            condition_2 = bb_lower_current > sma_20_current
            
            if condition_1 and condition_2:
                print(f"🚀 ENTRY SIGNAL DETECTED!")
                print(f"   Price: {current_close:.2f} <= BB Lower: {bb_lower_current:.2f}")
                print(f"   BB Lower: {bb_lower_current:.2f} > SMA20: {sma_20_current:.2f}")
                
                # Calculate stop loss
                stop_price = current_close - (self.stop_atr_multiple * atr_current)
                
                # Calculate position size based on 1% risk
                account_equity = self.equity
                risk_amount = account_equity * self.risk_percent
                risk_per_share = current_close - stop_price
                
                if risk_per_share > 0:
                    # Calculate position size (must be integer for backtesting.py)
                    position_size = risk_amount / risk_per_share
                    position_size = int(round(position_size))
                    
                    # Ensure minimum position size
                    if position_size > 0:
                        print(f"   Entry: {current_close:.2f}, Stop: {stop_price:.2f}")
                        print(f"   Risk: ${risk_amount:.2f}, Position Size: {position_size} units")
                        
                        # Place buy order with stop loss
                        self.buy(size=position_size, sl=stop_price)
                        
                        # Initialize highest high for trailing stop
                        self.highest_high = current_high
                        print(f"   ✅ LONG POSITION ENTERED!")
                    else:
                        print(f"   ⚠️ Position size too small: {position_size}")
                else:
                    print(f"   ⚠️ Invalid risk calculation (risk_per_share <= 0)")

# Main execution
if __name__ == "__main__":
    # Load and prepare data
    print("🌙 Loading data from:", DATA_PATH)
    data = pd.read_csv(DATA_PATH)
    
    # Clean column names
    data.columns = data.columns.str.strip().str.lower()
    
    # Drop any unnamed columns
    data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
    
    # Ensure proper column names for backtesting.py
    column_mapping = {
        'open': 'Open',
        'high': 'High', 
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    }
    
    # Rename columns
    for old_col, new_col in column_mapping.items():
        if old_col in data.columns:
            data[new_col] = data[old_col]
    
    # Convert datetime column
    if 'datetime' in data.columns:
        data['datetime'] = pd.to_datetime(data['datetime'])
        data = data.set_index('datetime')
    elif 'date' in data.columns:
        data['date'] = pd.to_datetime(data['date'])
        data = data.set_index('date')
    
    # Ensure we have required columns
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing_cols = [col for col in required_cols if col not in data.columns]
    
    if missing_cols:
        print(f"⚠️ Missing columns: {missing_cols}")
        print("Available columns:", data.columns.tolist())
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Select only required columns in correct order
    data = data[required_cols]
    
    print(f"✨ Data loaded: {len(data)} rows")
    print(f"✨ Date range: {data.index[0]} to {data.index[-1]}")
    print(f"✨ Initial equity: $1,000,000")
    
    # Create and run backtest
    bt = Backtest(data, BandShiftReversion, cash=1000000, commission=.002)
    
    print("\n" + "="*50)
    print("🌙 RUNNING BANDSHIFTREVERSION BACKTEST...")
    print("="*50 + "\n")
    
    # Run backtest
    stats = bt.run()
    
    # Print full statistics
    print("\n" + "="*50)
    print("📊 BACKTEST RESULTS")
    print("="*50)
    print(stats)
    print("\n" + "="*50)
    print("🔧 STRATEGY DETAILS")
    print("="*50)
    print(stats._strategy)