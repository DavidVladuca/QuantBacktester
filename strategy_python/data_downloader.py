import yfinance as yf
import pandas as pd
import os

def download_intraday_data(ticker, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"📥 Fetching 1-MINUTE data for {ticker} (Last 7 days)...")
    
    # yfinance -> only 7 days of 1m data available free
    df = yf.download(ticker, period="7d", interval="1m", auto_adjust=True)
    
    if df.empty:
        print(f"❌ Error: No data found for {ticker}")
        return
    
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    
    # flatten multi-index columns if yfinance has Ticker row
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
        
    # standardize timestamp format
    df.index = df.index.strftime('%Y-%m-%d %H:%M:%S')
    df.index.name = 'Datetime'
    
    file_path = os.path.join(output_dir, f"{ticker}_1min.csv")
    df.to_csv(file_path)
    print(f"✅ Saved high-res data to {file_path}")

if __name__ == "__main__":
    tickers_to_fetch = ["IWM", "COIN", "MSTR", "XOM", "ROKU", "PLTR"]
    
    target_folder = os.path.join("..", "backend_java", "backtester", "data")
    
    for ticker in tickers_to_fetch:
        download_intraday_data(ticker, target_folder)