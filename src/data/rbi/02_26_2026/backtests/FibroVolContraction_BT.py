import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import talib
import os

# Clean and prepare data function
def prepare_data(filepath):
    data = pd.read_csv(filepath)
    
    # Clean column names
    data.columns = data.columns.str.strip().str.lower()
    
    # Drop unnamed columns
    data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
    
    # Ensure proper column mapping
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
            data = data.rename(columns={old_col: new_col})
    
    # Convert datetime
    if 'datetime' in data.columns:
        data['datetime'] = pd.to_datetime(data['datetime'])
        data = data.set_index('datetime')
    
    # Ensure all required columns exist
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in required_cols:
        if col not in data.columns:
            raise ValueError(f"Missing required column: {col}")
    
    return data

class FibroVolContraction(Strategy):
    # Strategy parameters
    atr_period = 14
    sma_trend_period = 50
    swing_period = 20
    fib_levels = [0.382, 0.5, 0.618]
    risk_pct = 0.02  # 2% risk per trade
    atr_stop_multiplier = 1.5
    position_size_amount = 1000000
    
    def init(self):
        # 🌙 Moon Dev Indicator Setup
        print("🌙 Initializing FibroVolContraction Strategy...")
        
        # Trend indicators
        self.sma = self.I(talib.SMA, self.data.Close, timeperiod=self.sma_trend_period)
        
        # Volatility indicators
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, timeperiod=self.atr_period)
        self.atr_sma = self.I(talib.SMA, self.atr, timeperiod=self.atr_period)
        
        # Swing highs and lows
        self.swing_high = self.I(talib.MAX, self.data.High, timeperiod=self.swing_period)
        self.swing_low = self.I(talib.MIN, self.data.Low, timeperiod=self.swing_period)
        
        # Track recent swing points for Fibonacci calculation
        self.swing_high_idx = []
        self.swing_low_idx = []
        self.fib_levels_array = []
        
        # State variables
        self.in_position = False
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.fib_level_hit = 0
        
        print("✨ Indicators initialized successfully!")
    
    def calculate_swings(self):
        """Identify swing highs and lows for Fibonacci calculations"""
        # Find swing highs (peaks)
        for i in range(len(self.data)-1):
            if i >= self.swing_period:
                current_high = self.data.High[i]
                lookback_highs = self.data.High[i-self.swing_period:i]
                lookforward_highs = self.data.High[i+1:i+self.swing_period+1]
                
                if len(lookback_highs) > 0 and len(lookforward_highs) > 0:
                    if current_high > max(lookback_highs) and current_high > max(lookforward_highs):
                        if i not in self.swing_high_idx:
                            self.swing_high_idx.append(i)
        
        # Find swing lows (troughs)
        for i in range(len(self.data)-1):
            if i >= self.swing_period:
                current_low = self.data.Low[i]
                lookback_lows = self.data.Low[i-self.swing_period:i]
                lookforward_lows = self.data.Low[i+1:i+self.swing_period+1]
                
                if len(lookback_lows) > 0 and len(lookforward_lows) > 0:
                    if current_low < min(lookback_lows) and current_low < min(lookforward_lows):
                        if i not in self.swing_low_idx:
                            self.swing_low_idx.append(i)
        
        # Calculate Fibonacci levels between most recent swing low and swing high
        if len(self.swing_low_idx) >= 2 and len(self.swing_high_idx) >= 1:
            # Get the most recent swing low before the most recent swing high
            recent_swing_high_idx = self.swing_high_idx[-1]
            recent_swing_low_idx = None
            
            for low_idx in reversed(self.swing_low_idx):
                if low_idx < recent_swing_high_idx:
                    recent_swing_low_idx = low_idx
                    break
            
            if recent_swing_low_idx is not None:
                swing_low_price = self.data.Low[recent_swing_low_idx]
                swing_high_price = self.data.High[recent_swing_high_idx]
                
                # Calculate Fibonacci retracement levels
                diff = swing_high_price - swing_low_price
                self.fib_levels_array = [
                    swing_high_price - level * diff for level in self.fib_levels
                ]
    
    def check_volatility_contraction(self, idx):
        """Check if ATR is contracting (declining)"""
        if idx < self.atr_period * 2:
            return False
        
        # Check if current ATR is below its SMA (contraction)
        current_atr = self.atr[idx]
        current_atr_sma = self.atr_sma[idx]
        
        # Also check if ATR has been declining
        atr_declining = current_atr < self.atr[idx-1] < self.atr[idx-2]
        
        return current_atr < current_atr_sma or atr_declining
    
    def check_bullish_reversal(self, idx, fib_level):
        """Check for bullish reversal patterns at Fibonacci level"""
        if idx < 2:
            return False
        
        current_close = self.data.Close[idx]
        current_open = self.data.Open[idx]
        prev_close = self.data.Close[idx-1]
        prev_open = self.data.Open[idx-1]
        
        # Bullish engulfing pattern
        bullish_engulfing = (prev_close < prev_open and 
                           current_close > current_open and
                           current_close > prev_open and
                           current_open < prev_close)
        
        # Simple bounce with close above Fib level
        bounce_above = current_close > fib_level
        
        # Confirmation candle
        if idx >= 3:
            touch_candle_low = min(self.data.Low[idx-2:idx])
            confirmation = current_close > touch_candle_low
        
        return bullish_engulfing or (bounce_above and confirmation)
    
    def next(self):
        current_idx = len(self.data) - 1
        
        # 🌙 Update swing points
        self.calculate_swings()
        
        # Check if we're in an uptrend
        uptrend = self.data.Close[current_idx] > self.sma[current_idx]
        
        # Only proceed if in uptrend and not in position
        if uptrend and not self.in_position and len(self.fib_levels_array) > 0:
            
            # Check each Fibonacci level
            for fib_level in self.fib_levels_array:
                current_price = self.data.Close[current_idx]
                price_near_fib = abs(current_price - fib_level) / fib_level < 0.005  # 0.5% tolerance
                
                if price_near_fib:
                    # Check volatility contraction
                    volatility_contracting = self.check_volatility_contraction(current_idx)
                    
                    # Check for bullish reversal
                    bullish_reversal = self.check_bullish_reversal(current_idx, fib_level)
                    
                    if volatility_contracting and bullish_reversal:
                        # 🌙 Moon Dev Entry Signal!
                        print(f"🚀 ENTRY SIGNAL at index {current_idx}")
                        print(f"   Price: {current_price:.2f}, Fib Level: {fib_level:.2f}")
                        print(f"   ATR: {self.atr[current_idx]:.4f}, ATR SMA: {self.atr_sma[current_idx]:.4f}")
                        
                        # Calculate position size based on risk
                        risk_amount = self.equity * self.risk_pct
                        stop_distance = self.atr[current_idx] * self.atr_stop_multiplier
                        self.stop_loss = current_price - stop_distance
                        
                        # Calculate position size (units to buy)
                        position_size = risk_amount / stop_distance
                        position_size = int(round(position_size))
                        
                        # Limit position size
                        max_position = self.position_size_amount / current_price
                        position_size = min(position_size, int(round(max_position)))
                        
                        if position_size > 0:
                            self.buy(size=position_size)
                            self.in_position = True
                            self.entry_price = current_price
                            self.fib_level_hit = fib_level
                            
                            # Set initial stop loss
                            self.stop_loss = max(self.stop_loss, fib_level - stop_distance)
                            
                            # Calculate take profit (2:1 risk/reward)
                            risk = current_price - self.stop_loss
                            self.take_profit = current_price + (risk * 2)
                            
                            print(f"   Entry: {current_price:.2f}, SL: {self.stop_loss:.2f}, TP: {self.take_profit:.2f}")
                            print(f"   Position Size: {position_size} units")
                        break
        
        # Check exit conditions if in position
        elif self.in_position:
            current_price = self.data.Close[current_idx]
            
            # Exit condition 1: Stop loss hit
            if current_price <= self.stop_loss:
                print(f"🛑 STOP LOSS at {current_price:.2f}")
                self.position.close()
                self.in_position = False
            
            # Exit condition 2: Take profit hit
            elif current_price >= self.take_profit:
                print(f"🎯 TAKE PROFIT at {current_price:.2f}")
                self.position.close()
                self.in_position = False
            
            # Exit condition 3: Volatility expansion (ATR rising above SMA)
            elif self.atr[current_idx] > self.atr_sma[current_idx] and self.atr[current_idx] > self.atr[current_idx-1]:
                print(f"📈 VOLATILITY EXPANSION exit at {current_price:.2f}")
                print(f"   ATR: {self.atr[current_idx]:.4f} > SMA: {self.atr_sma[current_idx]:.4f}")
                self.position.close()
                self.in_position = False
            
            # Exit condition 4: Breakout above swing high
            elif len(self.swing_high_idx) > 0:
                recent_swing_high = self.data.High[self.swing_high_idx[-1]]
                if current_price > recent_swing_high:
                    print(f"🏔️ BREAKOUT above swing high at {current_price:.2f}")
                    print(f"   Swing High: {recent_swing_high:.2f}")
                    self.position.close()
                    self.in_position = False
            
            # Update trailing stop (based on highest close)
            if self.in_position:
                # Simple trailing stop: highest close minus 2*ATR
                trailing_stop = self.data.High[current_idx] - (self.atr[current_idx] * 2)
                if trailing_stop > self.stop_loss:
                    self.stop_loss = trailing_stop
                    print(f"📊 Trailing stop updated to {self.stop_loss:.2f}")

# Main execution
if __name__ == "__main__":
    # Get project root and data path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_path = os.path.join(project_root, "src", "data", "rbi", "BTC-USD-15m-train.csv")
    
    print(f"🌙 Loading data from: {data_path}")
    
    # Load and prepare data
    try:
        data = prepare_data(data_path)
        print(f"✨ Data loaded successfully! Shape: {data.shape}")
        print(f"📅 Date range: {data.index[0]} to {data.index[-1]}")
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        # Create sample data for testing if file not found
        print("🔄 Creating sample data for testing...")
        dates = pd.date_range('2023-01-01', periods=1000, freq='15min')
        data = pd.DataFrame({
            'Open': np.random.uniform(16000, 17000, 1000),
            'High': np.random.uniform(16500, 17500, 1000),
            'Low': np.random.uniform(15500, 16500, 1000),
            'Close': np.random.uniform(16000, 17000, 1000),
            'Volume': np.random.uniform(200, 500, 1000)
        }, index=dates)
    
    # Run backtest
    print("🚀 Starting Backtest...")
    bt = Backtest(data, FibroVolContraction, cash=1000000, commission=.002)
    
    # Run with default parameters
    stats = bt.run()
    
    # Print full statistics
    print("\n" + "="*50)
    print("🌙 MOON DEV BACKTEST RESULTS")
    print("="*50)
    print(stats)
    print("\n" + "="*50)
    print("STRATEGY DETAILS")
    print("="*50)
    print(stats._strategy)