import os
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy

class GannConvergence(Strategy):
    # Strategy parameters
    sma_period = 5
    gann_slope = 1.0  # 1x1 angle
    pivot_lookback = 20
    risk_pct = 0.01  # 1% risk per trade
    atr_period = 14
    
    def init(self):
        # Clean and prepare data
        price = self.data.Close
        high = self.data.High
        low = self.data.Low
        
        # Calculate indicators
        self.sma5 = self.I(talib.SMA, price, timeperiod=self.sma_period)
        self.atr = self.I(talib.ATR, high, low, price, timeperiod=self.atr_period)
        
        # Calculate swing highs and lows for pivot points
        self.swing_high = self.I(talib.MAX, high, timeperiod=self.pivot_lookback)
        self.swing_low = self.I(talib.MIN, low, timeperiod=self.pivot_lookback)
        
        # Track current Gann angle value (simulated)
        self.gann_angle = self.I(self.calculate_gann_angle)
        
        # Track trend direction
        self.trend = self.I(self.detect_trend)
        
        # Print initialization message
        print("🌙 Moon Dev's GannConvergence Strategy Initialized ✨")
        print(f"SMA Period: {self.sma_period}, Risk: {self.risk_pct*100}%, Pivot Lookback: {self.pivot_lookback}")
    
    def calculate_gann_angle(self):
        """Calculate Gann Angle based on recent pivot points"""
        gann_values = np.zeros(len(self.data.Close))
        
        # Simple Gann angle simulation: track recent pivot and project angle
        recent_pivot_idx = -1
        recent_pivot_value = 0
        trend_dir = 0  # 1 for uptrend, -1 for downtrend
        
        for i in range(len(self.data.Close)):
            # Find most recent swing high/low
            if i >= self.pivot_lookback:
                # Check if current bar is a swing high
                if self.data.High[i] == self.swing_high[i]:
                    recent_pivot_idx = i
                    recent_pivot_value = self.data.High[i]
                    trend_dir = -1  # Potential downtrend start
                # Check if current bar is a swing low
                elif self.data.Low[i] == self.swing_low[i]:
                    recent_pivot_idx = i
                    recent_pivot_value = self.data.Low[i]
                    trend_dir = 1  # Potential uptrend start
            
            # Calculate Gann angle from pivot
            if recent_pivot_idx >= 0 and trend_dir != 0:
                bars_since_pivot = i - recent_pivot_idx
                angle_slope = self.gann_slope * self.atr[i] if i > 0 else 0
                gann_values[i] = recent_pivot_value + (trend_dir * bars_since_pivot * angle_slope)
            else:
                gann_values[i] = np.nan
        
        return gann_values
    
    def detect_trend(self):
        """Detect overall trend direction"""
        trend_values = np.zeros(len(self.data.Close))
        
        for i in range(len(self.data.Close)):
            if i < 20:
                trend_values[i] = 0
                continue
            
            # Simple trend detection using price structure
            highs = self.data.High[i-20:i+1]
            lows = self.data.Low[i-20:i+1]
            
            # Check for higher highs and higher lows (uptrend)
            if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                if highs[-1] > np.max(highs[:-2]) and lows[-1] > np.min(lows[:-2]):
                    trend_values[i] = 1
            # Check for lower highs and lower lows (downtrend)
            elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                if highs[-1] < np.min(highs[:-2]) and lows[-1] < np.max(lows[:-2]):
                    trend_values[i] = -1
            else:
                trend_values[i] = trend_values[i-1] if i > 0 else 0
        
        return trend_values
    
    def calculate_position_size(self, entry_price, stop_price):
        """Calculate position size based on risk percentage"""
        account_value = self.equity
        risk_amount = account_value * self.risk_pct
        
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_price)
        
        if risk_per_unit == 0:
            return 0
        
        # Calculate position size
        position_size = risk_amount / risk_per_unit
        
        # Convert to integer for backtesting.py
        position_size = int(round(position_size))
        
        print(f"💰 Position Size Calculation:")
        print(f"   Account: ${account_value:,.2f}")
        print(f"   Risk Amount: ${risk_amount:,.2f}")
        print(f"   Risk per Unit: ${risk_per_unit:.4f}")
        print(f"   Calculated Size: {position_size} units")
        
        return position_size
    
    def calculate_profit_target(self, entry_price, current_gann, current_sma):
        """Calculate dynamic profit target based on Gann-SMA convergence"""
        # Simple projection: target is where Gann and SMA would converge
        # Based on current rates of change
        if len(self.sma5) < 2 or len(self.gann_angle) < 2:
            return entry_price * 1.02  # Default 2% target
        
        # Get recent slopes
        sma_slope = self.sma5[-1] - self.sma5[-2]
        gann_slope = self.gann_angle[-1] - self.gann_angle[-2] if not np.isnan(self.gann_angle[-2]) else 0
        
        # Project convergence
        if abs(sma_slope - gann_slope) > 0:
            bars_to_converge = (current_gann - current_sma) / (sma_slope - gann_slope)
            bars_to_converge = max(1, min(20, bars_to_converge))  # Limit projection
            target_price = current_sma + (sma_slope * bars_to_converge)
        else:
            # Default to 2:1 risk-reward if no convergence projection
            target_price = entry_price + (2 * abs(entry_price - (entry_price * 0.98)))
        
        return target_price
    
    def next(self):
        price = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]
        sma = self.sma5[-1]
        gann = self.gann_angle[-1]
        current_trend = self.trend[-1]
        
        # Skip if we don't have enough data or Gann angle is NaN
        if (len(self.data.Close) < 50 or np.isnan(gann) or 
            np.isnan(sma) or current_trend == 0):
            return
        
        # Check for engulfing patterns
        if len(self.data.Close) >= 3:
            # Bullish engulfing pattern
            bullish_engulfing = (
                self.data.Close[-2] < self.data.Open[-2] and  # Previous bearish candle
                self.data.Close[-1] > self.data.Open[-1] and  # Current bullish candle
                self.data.Open[-1] < self.data.Close[-2] and  # Current open below previous close
                self.data.Close[-1] > self.data.Open[-2]      # Current close above previous open
            )
            
            # Bearish engulfing pattern
            bearish_engulfing = (
                self.data.Close[-2] > self.data.Open[-2] and  # Previous bullish candle
                self.data.Close[-1] < self.data.Open[-1] and  # Current bearish candle
                self.data.Open[-1] > self.data.Close[-2] and  # Current open above previous close
                self.data.Close[-1] < self.data.Open[-2]      # Current close below previous open
            )
        else:
            bullish_engulfing = bearish_engulfing = False
        
        # Check if price is near Gann angle (within 0.5%)
        near_gann = abs(price - gann) / price <= 0.005
        
        # ENTRY LOGIC
        if not self.position:
            # LONG ENTRY
            if (current_trend == 1 and  # Uptrend
                near_gann and  # Price near Gann angle
                bullish_engulfing and  # Bullish reversal pattern
                sma < price and  # SMA below price
                sma > self.sma5[-2]):  # SMA rising
                
                # Calculate stop loss (below Gann angle and recent swing low)
                stop_price = min(gann * 0.995, self.swing_low[-1])
                stop_price = max(stop_price, low * 0.99)  # Ensure stop is below current low
                
                # Calculate position size
                position_size = self.calculate_position_size(price, stop_price)
                
                if position_size > 0:
                    # Calculate profit target
                    target_price = self.calculate_profit_target(price, gann, sma)
                    
                    print(f"🚀 MOON DEV LONG SIGNAL! 🌙")
                    print(f"   Entry: ${price:.2f}")
                    print(f"   Stop: ${stop_price:.2f}")
                    print(f"   Target: ${target_price:.2f}")
                    print(f"   Risk: ${abs(price-stop_price):.2f} ({abs(price-stop_price)/price*100:.2f}%)")
                    print(f"   R:R Ratio: {(target_price-price)/(price-stop_price):.2f}:1")
                    
                    # Enter position
                    self.buy(size=position_size, 
                            sl=stop_price, 
                            tp=target_price)
            
            # SHORT ENTRY
            elif (current_trend == -1 and  # Downtrend
                  near_gann and  # Price near Gann angle
                  bearish_engulfing and  # Bearish reversal pattern
                  sma > price and  # SMA above price
                  sma < self.sma5[-2]):  # SMA falling
                
                # Calculate stop loss (above Gann angle and recent swing high)
                stop_price = max(gann * 1.005, self.swing_high[-1])
                stop_price = min(stop_price, high * 1.01)  # Ensure stop is above current high
                
                # Calculate position size
                position_size = self.calculate_position_size(price, stop_price)
                
                if position_size > 0:
                    # Calculate profit target
                    target_price = self.calculate_profit_target(price, gann, sma)
                    
                    print(f"📉 MOON DEV SHORT SIGNAL! 🌙")
                    print(f"   Entry: ${price:.2f}")
                    print(f"   Stop: ${stop_price:.2f}")
                    print(f"   Target: ${target_price:.2f}")
                    print(f"   Risk: ${abs(price-stop_price):.2f} ({abs(price-stop_price)/price*100:.2f}%)")
                    print(f"   R:R Ratio: {(price-target_price)/(stop_price-price):.2f}:1")
                    
                    # Enter position
                    self.sell(size=position_size, 
                             sl=stop_price, 
                             tp=target_price)
        
        # EXIT LOGIC for existing positions
        else:
            # Check for trailing stop or early exit conditions
            if self.position.is_long:
                # Trailing stop using 5-period SMA
                trailing_stop = self.sma5[-1] * 0.995
                current_stop = self.position.sl if self.position.sl else 0
                
                # Update stop if SMA provides better protection
                if trailing_stop > current_stop:
                    self.position.sl = trailing_stop
                    print(f"🔒 Long trailing stop updated to: ${trailing_stop:.2f}")
            
            elif self.position.is_short:
                # Trailing stop using 5-period SMA
                trailing_stop = self.sma5[-1] * 1.005
                current_stop = self.position.sl if self.position.sl else float('inf')
                
                # Update stop if SMA provides better protection
                if trailing_stop < current_stop:
                    self.position.sl = trailing_stop
                    print(f"🔒 Short trailing stop updated to: ${trailing_stop:.2f}")

# Data preparation function
def prepare_data(filepath):
    print(f"📊 Loading data from: {filepath}")
    
    # Read data
    data = pd.read_csv(filepath)
    
    # Clean column names
    data.columns = data.columns.str.strip().str.lower()
    
    # Drop any unnamed columns
    data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
    
    # Ensure required columns exist
    required_cols = {'open', 'high', 'low', 'close', 'volume'}
    available_cols = set(data.columns)
    
    # Map available columns to required format
    column_mapping = {}
    for req in required_cols:
        for avail in available_cols:
            if req in avail:
                column_mapping[avail] = req.capitalize()
                break
    
    # Rename columns
    data = data.rename(columns=column_mapping)
    
    # Ensure all required columns exist
    for req in required_cols:
        if req.capitalize() not in data.columns:
            print(f"⚠️  Warning: Missing required column: {req.capitalize()}")
    
    # Convert to datetime index
    if 'datetime' in data.columns:
        data['datetime'] = pd.to_datetime(data['datetime'])
        data = data.set_index('datetime')
    elif 'date' in data.columns:
        data['date'] = pd.to_datetime(data['date'])
        data = data.set_index('date')
    
    print(f"✅ Data loaded: {len(data)} rows, {len(data.columns)} columns")
    print(f"   Date range: {data.index[0]} to {data.index[-1]}")
    
    return data

# Main execution
if __name__ == "__main__":
    # Set data path
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")
    
    # Load and prepare data
    data = prepare_data(DATA_PATH)
    
    # Ensure we have the required columns in proper case
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    # Check if we have minimum required data
    if 'Open' not in data.columns or 'Close' not in data.columns:
        print("❌ Error: Required price columns not found in data")
        exit()
    
    print("🌙 Starting Moon Dev's GannConvergence Backtest...")
    print("=" * 50)
    
    # Initialize and run backtest
    bt = Backtest(data, GannConvergence, cash=1000000, commission=.002)
    
    # Run backtest
    stats = bt.run()
    
    # Print results
    print("\n" + "=" * 50)
    print("📈 BACKTEST RESULTS - GANNCONVERGENCE STRATEGY")
    print("=" * 50)
    print(stats)
    print("\n" + "=" * 50)
    print("🎯 STRATEGY DETAILS")
    print("=" * 50)
    print(stats._strategy)