from decimal import Decimal
import mysql.connector
import yfinance as yf

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",  # <-- Replace with your MySQL password
    "database": "stock_exchange_db",
}

def get_conn():
    return mysql.connector.connect(**DB_CONFIG)

def fetch_and_store_yfinance_data():
    conn = get_conn()
    cur = conn.cursor()

    tickers = [
        ("^NSEI", "Nifty 50"),
        ("RELIANCE.NS", "Reliance Industries"),
        ("TCS.NS", "TCS"),
        ("INFY.NS", "Infosys"),
        ("HDFCBANK.NS", "HDFC Bank"),
    ]

    for symbol, name in tickers:
        print(f"Fetching real data for {name} ({symbol})...")
        df = yf.download(symbol, period="1mo", interval="1d", progress=False)

        if df.empty:
            print(f"  -> Warning: No data returned for {symbol}")
            continue

        # Safely extract 1D Series of closing prices
        close_series = df["Close"]
        if hasattr(close_series, "columns"):
            close_series = close_series.iloc[:, 0]
        close_series = close_series.dropna()

        latest_price = Decimal(str(round(float(close_series.iloc[-1]), 2)))

        # 1. Insert or update the stock's live price in MySQL
        cur.execute(
            """
            INSERT INTO stocks (symbol, name, current_price)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE name = VALUES(name), current_price = VALUES(current_price)
            """,
            (symbol, name, latest_price),
        )

        cur.execute("SELECT id FROM stocks WHERE symbol = %s", (symbol,))
        stock_id = cur.fetchone()[0]

        # 2. Replace old history with real dates & prices from yfinance
        cur.execute("DELETE FROM stock_history WHERE stock_id = %s", (stock_id,))

        history_rows = [
            (stock_id, date_idx.strftime("%d %b"), Decimal(str(round(float(price_val), 2))))
            for date_idx, price_val in close_series.items()
        ]
        cur.executemany(
            "INSERT INTO stock_history (stock_id, label, price) VALUES (%s, %s, %s)",
            history_rows,
        )
        print(f"  -> Saved {len(history_rows)} real trading days | Latest Price: ₹{latest_price}")

    conn.commit()
    conn.close()
    print("\nAll 5 stocks synced with real yfinance data in MySQL!")

if __name__ == "__main__":
    fetch_and_store_yfinance_data()