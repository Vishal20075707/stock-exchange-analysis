from db_config import get_conn


def run_fraud_detection():
    conn = get_conn()
    cur = conn.cursor()

    # Clear old scan results before running fresh SQL checks
    cur.execute("DELETE FROM fraud_alerts")

    flagged_trades = {}

    def add_flag(trade_id, rule_label, severity, suspect_name, suspect_acc, detail_msg):
        flagged_trades.setdefault(trade_id, [])
        if rule_label not in flagged_trades[trade_id]:
            flagged_trades[trade_id].append(rule_label)
            cur.execute(
                """
                INSERT INTO fraud_alerts (trade_id, fraud_type, severity, suspect_name, suspect_account, details)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (trade_id, rule_label, severity, suspect_name, suspect_acc, detail_msg),
            )

    # RULE 1: Abnormal Trading Volume (> 2x average trade quantity)
    cur.execute("""
        SELECT t.id, t.buyer, t.buyer_account, s.symbol, t.quantity
        FROM trades t
        JOIN stocks s ON t.stock_id = s.id
        WHERE t.quantity > 2.0 * (SELECT COALESCE(AVG(quantity), 0) FROM (SELECT quantity FROM trades) avg_tbl)
    """)
    for tid, buyer, b_acc, sym, qty in cur.fetchall():
        add_flag(tid, "1. Abnormal Volume (>2x)", "MEDIUM", buyer, b_acc, f"Traded {qty} shares of {sym}")

    # RULE 2: Unusual Price Movement (> 5% jump/drop between consecutive trades on same stock)
    cur.execute("""
        SELECT id, buyer, buyer_account, symbol, prev_price, price FROM (
            SELECT t.id, t.buyer, t.buyer_account, s.symbol, t.price,
                   LAG(t.price) OVER (PARTITION BY t.stock_id ORDER BY t.id) AS prev_price
            FROM trades t
            JOIN stocks s ON t.stock_id = s.id
        ) price_seq
        WHERE prev_price IS NOT NULL
          AND ABS(price - prev_price) / prev_price > 0.05
    """)
    for tid, buyer, b_acc, sym, p1, p2 in cur.fetchall():
        add_flag(tid, "2. Price Spike/Drop (>5%)", "HIGH", buyer, b_acc, f"{sym} moved ₹{p1} -> ₹{p2}")

    # RULE 3: Repeated Buy/Sell Transactions (Wash Trading: same pair 3+ times)
    cur.execute("""
        SELECT t.id, t.buyer, t.buyer_account, t.seller, t.seller_account
        FROM trades t
        JOIN (
            SELECT buyer_account, seller_account, stock_id
            FROM trades
            GROUP BY buyer_account, seller_account, stock_id
            HAVING COUNT(*) >= 3
        ) wash
          ON t.buyer_account = wash.buyer_account
         AND t.seller_account = wash.seller_account
         AND t.stock_id = wash.stock_id
    """)
    for tid, b, b_acc, s, s_acc in cur.fetchall():
        add_flag(tid, "3. Repeated Wash Trade", "HIGH", f"{b} & {s}", f"{b_acc}/{s_acc}", "3+ repeated trades between pair")

    # RULE 4: Circular Price Rigging (A -> B -> C chain at escalating prices)
    cur.execute("""
        SELECT
            t1.id,
            t2.id,
            t1.seller,
            t1.seller_account,
            t1.buyer,
            t1.buyer_account,
            t2.buyer,
            t2.buyer_account,
            s.symbol,
            t1.price,
            t2.price
        FROM trades t1
        JOIN trades t2
          ON t1.buyer_account = t2.seller_account
         AND t1.stock_id = t2.stock_id
         AND t2.id > t1.id
        JOIN stocks s ON t1.stock_id = s.id
        WHERE t2.price > t1.price
          AND t1.seller_account <> t1.buyer_account
          AND t2.seller_account <> t2.buyer_account
    """)
    for tid1, tid2, u1, acc1, u2, acc2, u3, acc3, sym, p1, p2 in cur.fetchall():
        ring_names = f"{u1} -> {u2} -> {u3}"
        ring_accs = f"{acc1} -> {acc2} -> {acc3}"
        pct_jump = round(((p2 - p1) / p1) * 100, 2)
        msg = f"Circular price rigging on {sym}: ₹{p1} -> ₹{p2} (+{pct_jump}%)"
        add_flag(tid1, "4. Circular Price Rigging", "CRITICAL", ring_names, ring_accs, msg)
        add_flag(tid2, "4. Circular Price Rigging", "CRITICAL", ring_names, ring_accs, msg)
        
    # RULE 5: Self-Trading / Mirror Account (Same account on both sides)
    cur.execute("""
        SELECT id, buyer, buyer_account
        FROM trades
        WHERE buyer_account = seller_account OR buyer = seller
    """)
    for tid, buyer, b_acc in cur.fetchall():
        add_flag(tid, "5. Self-Trade / Mirror Acc", "HIGH", buyer, b_acc, "Same account acted as buyer & seller")

    # RULE 6: Connected Accounts Collusion (Different accounts sharing same IP/Device)
    cur.execute("""
        SELECT id, buyer, buyer_account, seller, seller_account, buyer_device
        FROM trades
        WHERE buyer_device = seller_device AND buyer_account <> seller_account
    """)
    for tid, b, b_acc, s, s_acc, dev in cur.fetchall():
        add_flag(tid, "6. Connected Accounts (IP)", "HIGH", f"{b} & {s}", f"{b_acc}/{s_acc}", f"Shared IP/Device: {dev}")

    # RULE 7: Suspicious Order Cancellations (Spoofing: 3+ cancelled orders)
    cur.execute("""
        SELECT trader_name, account_no, COUNT(*) AS cancel_cnt
        FROM orders
        WHERE status = 'CANCELLED'
        GROUP BY trader_name, account_no
        HAVING cancel_cnt >= 3
    """)
    spoofers = {}
    for name, acc, cnt in cur.fetchall():
        spoofers[acc] = (name, cnt)
        cur.execute(
            """
            INSERT INTO fraud_alerts (order_id, fraud_type, severity, suspect_name, suspect_account, details)
            SELECT id, '7. Suspicious Cancellations', 'MEDIUM', %s, %s, %s
            FROM orders WHERE account_no = %s AND status = 'CANCELLED' LIMIT 1
            """,
            (name, acc, f"Cancelled {cnt} orders (order-book spoofing)", acc),
        )

    cur.execute("SELECT id, buyer, buyer_account, seller, seller_account FROM trades")
    for tid, b, b_acc, s, s_acc in cur.fetchall():
        if b_acc in spoofers:
            add_flag(tid, "7. Spoofing Trader", "MEDIUM", b, b_acc, f"{spoofers[b_acc][1]} cancelled orders")
        if s_acc in spoofers:
            add_flag(tid, "7. Spoofing Trader", "MEDIUM", s, s_acc, f"{spoofers[s_acc][1]} cancelled orders")

    conn.commit()

    # Build Safe vs. Fraud classification report for UI
    cur.execute("""
        SELECT t.id, s.symbol, t.buyer, t.buyer_account, t.seller, t.seller_account, t.quantity, t.price
        FROM trades t
        JOIN stocks s ON t.stock_id = s.id
        ORDER BY t.id DESC
    """)
    all_trades = cur.fetchall()

    classified_rows = []
    category_counts = {"SAFE": 0}
    safe_cnt = 0
    fraud_cnt = 0

    for tid, sym, b, b_acc, s, s_acc, qty, prc in all_trades:
        if tid in flagged_trades:
            fraud_cnt += 1
            reasons = " | ".join(flagged_trades[tid])
            for r in flagged_trades[tid]:
                category_counts[r] = category_counts.get(r, 0) + 1
            classified_rows.append((tid, sym, f"{b} ({b_acc})", f"{s} ({s_acc})", qty, f"₹{prc}", "FRAUD", reasons))
        else:
            safe_cnt += 1
            category_counts["SAFE"] += 1
            classified_rows.append((tid, sym, f"{b} ({b_acc})", f"{s} ({s_acc})", qty, f"₹{prc}", "SAFE", "Normal Market Transaction"))

    # Add standalone spoofing rows if a spoofer cancelled orders without completing a trade
    for acc, (name, cnt) in spoofers.items():
        classified_rows.append(
            ("ORDER", "ALL", f"{name} ({acc})", "-", "-", "-", "FRAUD", f"7. Suspicious Cancellations ({cnt} cancelled orders)")
        )

    # Fetch per-trader fill vs cancellation counts for bar chart
    cur.execute("SELECT name, account_no FROM traders ORDER BY name")
    trader_stats = []
    for t_name, t_acc in cur.fetchall():
        cur.execute("SELECT COUNT(*) FROM orders WHERE account_no=%s AND status='FILLED'", (t_acc,))
        filled = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orders WHERE account_no=%s AND status='CANCELLED'", (t_acc,))
        cancelled = cur.fetchone()[0]
        trader_stats.append((t_name, filled, cancelled))

    conn.close()
    return {
        "rows": classified_rows,
        "total": len(all_trades),
        "safe_count": safe_cnt,
        "fraud_count": fraud_cnt,
        "category_counts": category_counts,
        "trader_stats": trader_stats,
    }