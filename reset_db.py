from db_config import get_conn, fetch_and_store_yfinance_data


def flush_and_reset_database():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    tables = [
        "fraud_alerts",
        "trades",
        "orders",
        "portfolios",
        "traders",
        "stock_history",
        "stocks",
    ]
    for table in tables:
        cur.execute(f"TRUNCATE TABLE {table}")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    conn.commit()
    conn.close()
    print("Database flushed! All tables cleared and IDs reset to 1.")

    # Re-fetch clean real prices for all 5 stocks
    fetch_and_store_yfinance_data()


if __name__ == "__main__":
    flush_and_reset_database()