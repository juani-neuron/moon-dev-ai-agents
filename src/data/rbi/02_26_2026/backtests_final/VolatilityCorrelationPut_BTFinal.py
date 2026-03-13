import pandas as pd
import numpy as np
import talib
from backtesting import Strategy, Backtest
from backtesting.lib import crossover
import warnings
warnings.filterwarnings('ignore')

class VolatilityCorrelationPut(Strategy):
    account_size = 1_000_000
    risk_per_trade = 0.01
    
    def init(self):
        # Calculate daily returns for SPX and VIX
        self.daily_close_spx = self.I(self.resample_daily, self.data.Close, 'close')
        self.daily_close_vix = self.I(self.resample_daily, self.data.vix_close, 'vix_close')
        
        # Calculate percentage changes
        self.pct_change_spx = self.I(self.calculate_pct_change, self.daily_close_spx)
        self.pct_change_vix = self.I(self.calculate_pct_change, self.daily_close_vix)
        
        # Calculate correlation condition
        self.corr_condition = self.I(self.calculate_corr_condition, 
                                     self.pct_change_spx, self.pct_change_vix)
        
        # Calculate daily highs and lows
        self.daily_high = self.I(self.resample_daily, self.data.High, 'high')
        self.daily_low = self.I(self.resample_daily, self.data.Low, 'low')
        
        # Shift to get previous day's high/low and next day's low
        self.prev_day_high = self.I(self.shift_series, self.daily_high, 1)
        self.prev_day_low = self.I(self.shift_series, self.daily_low, 1)
        self.next_day_low = self.I(self.shift_series, self.daily_low, -1)
        
        # Initialize tracking variables
        self.last_trade_date = None
        self.entry_price = None
        self.stop_loss_price = None
        self.take_profit_price = None
        self.entry_date = None
        
    def resample_daily(self, series, name):
        """Resample intraday data to daily frequency"""
        # Create a temporary dataframe with the series
        df = pd.DataFrame({name: series})
        df.index = self.data.index
        
        # Resample to daily
        if name == 'close' or name == 'vix_close':
            daily = df.resample('D').last()
        elif name == 'high':
            daily = df.resample('D').max()
        elif name == 'low':
            daily = df.resample('D').min()
        else:
            daily = df.resample('D').mean()
            
        return daily[name].reindex(df.index, method='ffill')
    
    def calculate_pct_change(self, series):
        """Calculate percentage change"""
        return series.pct_change()
    
    def calculate_corr_condition(self, spx_pct, vix_pct):
        """Calculate correlation condition"""
        return np.abs(spx_pct - vix_pct) <= 0.05
    
    def shift_series(self, series, periods):
        """Shift series by specified periods"""
        return series.shift(periods)
    
    def next(self):
        current_date = self.data.index[-1].date()
        
        # Check if we're in a trade
        if self.position:
            # Check stop loss
            if self.data.Low[-1] <= self.stop_loss_price:
                self.position.close()
                print(f"🌙 MOON DEV STOP LOSS HIT! | Exit: {self.data.Close[-1]:.2f} | "
                      f"PnL: {self.position.pl:.2f} | "
                      f"Return: {(self.position.pl/self.position.value)*100:.2f}%")
                self.last_trade_date = None
                return
            
            # Check take profit (next day's low)
            if self.data.Low[-1] <= self.take_profit_price:
                self.position.close()
                print(f"✨ MOON DEV TAKE PROFIT! | Exit: {self.data.Close[-1]:.2f} | "
                      f"PnL: {self.position.pl:.2f} | "
                      f"Return: {(self.position.pl/self.position.value)*100:.2f}%")
                self.last_trade_date = None
                return
            
            # Exit at end of next day if not already exited
            if current_date != self.entry_date:
                if self.data.index[-1].time() >= pd.Timestamp('15:45').time():
                    self.position.close()
                    print(f"🌙 MOON DEV END OF DAY EXIT | Exit: {self.data.Close[-1]:.2f} | "
                          f"PnL: {self.position.pl:.2f} | "
                          f"Return: {(self.position.pl/self.position.value)*100:.2f}%")
                    self.last_trade_date = None
                return
        
        # Check if we should enter a new trade
        if self.last_trade_date == current_date:
            return
            
        # Check correlation condition (previous day)
        if not self.corr_condition[-1]:
            return
            
        # Check entry condition (price crosses above previous day's high)
        if self.data.High[-2] < self.prev_day_high[-1] and self.data.High[-1] > self.prev_day_high[-1]:
            # Calculate position size based on risk
            entry_price = self.prev_day_high[-1]
            stop_loss_price = self.prev_day_low[-1]
            risk_per_share = entry_price - stop_loss_price
            
            if risk_per_share <= 0:
                return
                
            risk_amount = self.account_size * self.risk_per_trade
            position_size = int(risk_amount / risk_per_share)
            
            if position_size <= 0:
                return
            
            # Enter trade with rounded position size
            self.buy(size=position_size)
            
            # Set trade parameters
            self.entry_price = entry_price
            self.stop_loss_price = stop_loss_price
            self.take_profit_price = self.next_day_low[-1]
            self.entry_date = current_date
            self.last_trade_date = current_date
            
            print(f"🚀 MOON DEV TRADE ENTERED! | "
                  f"Date: {current_date} | "
                  f"Entry: {entry_price:.2f} | "
                  f"Stop: {stop_loss_price:.2f} | "
                  f"Target: {self.take_profit_price:.2f} | "
                  f"Size: {position_size} shares")

# Load and prepare data function
def prepare_data(csv_path):
    df = pd.read_csv(csv_path)
    
    # Clean column names
    df.columns = [col.strip().lower() for col in df.columns]
    
    # Convert datetime
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    
    # Ensure we have required columns
    required_columns = ['open', 'high', 'low', 'close', 'volume', 
                       'vix_open', 'vix_high', 'vix_low', 'vix_close']
    
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"🌙 MOON DEV DEBUG: Missing required column: {col}")
    
    return df

# Main execution
if __name__ == "__main__":
    # Load your data
    data = prepare_data('your_data.csv')
    
    # Run backtest
    bt = Backtest(data, VolatilityCorrelationPut, cash=1_000_000, commission=.002)
    results = bt.run()
    
    print("🌙 MOON DEV BACKTEST COMPLETE! 🌙")
    print("=" * 50)
    print(f"Total Return: {results['Return [%]']:.2f}%")
    print(f"Sharpe Ratio: {results['Sharpe Ratio']:.2f}")
    print(f"Max Drawdown: {results['Max. Drawdown [%]']:.2f}%")
    print(f"Total Trades: {results['# Trades']}")
    print(f"Win Rate: {results['Win Rate [%]']:.2f}%")
    print("=" * 50)
    
    # Plot results
    bt.plot()