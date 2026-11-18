from decimal import Decimal
from datetime import datetime
from db_config import get_conn


def place_and_match_order(trader_name, account_no, stock_id, side, price, quantity, device_ip):
    conn = get_conn()
    cur = conn.cursor()

    try:
        conn.start_transaction()

        # 1. Fetch or auto-create trader wallet & initial 100 shares per stock
        cur.execute(
            "SELECT id, name, cash_balance FROM traders WHERE account_no = %s FOR UPDATE",
            (account_no,),
        )
        row = cur.fetchone()

        if not row:
            cur.execute(
                "INSERT INTO traders (name, account_no, cash_balance) VALUES (%s, %s, 100000.00)",
                (trader_name, account_no),
            )
            trader_id = cur.lastrowid
            cash_bal = Decimal("100000.00")

            cur.execute("SELECT id FROM stocks")
            for (s_id,) in cur.fetchall():
                cur.execute(
                    "INSERT INTO portfolios (trader_id, stock_id, shares) VALUES (%s, %s, 100)",
                    (trader_id, s_id),
                )
        else:
            trader_id, existing_name, cash_bal = row
            trader_name = existing_name

        cur.execute(
            "SELECT shares FROM portfolios WHERE trader_id = %s AND stock_id = %s FOR UPDATE",
            (trader_id, stock_id),
        )
        shares_owned = cur.fetchone()[0]

        # 2. Validate & escrow funds (BUY) or shares (SELL)
        if side == "BUY":
            total_cost = price * quantity
            if cash_bal < total_cost:
                raise Exception(
                    f"Insufficient balance! {trader_name} ({account_no}) has ₹{cash_bal}, needs ₹{total_cost}."
                )
            cur.execute(
                "UPDATE traders SET cash_balance = cash_balance - %s WHERE id = %s",
                (total_cost, trader_id),
            )
        else:
            if shares_owned < quantity:
                raise Exception(
                    f"Insufficient shares! {trader_name} ({account_no}) owns {shares_owned} shares."
                )
            cur.execute(
                "UPDATE portfolios SET shares = shares - %s WHERE trader_id = %s AND stock_id = %s",
                (quantity, trader_id, stock_id),
            )

        # 3. Insert incoming order into MySQL order book
        cur.execute(
            """
            INSERT INTO orders (trader_name, account_no, stock_id, side, price, quantity, remaining_qty, status, device_ip)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN', %s)
            """,
            (trader_name, account_no, stock_id, side, price, quantity, quantity, device_ip),
        )
        incoming_id = cur.lastrowid
        remaining = quantity
        match_logs = []

        # 4. Query opposite side using Price-Time Priority (FIFO)
        if side == "BUY":
            cur.execute(
                """
                SELECT id, trader_name, account_no, price, quantity, remaining_qty, device_ip
                FROM orders
                WHERE stock_id = %s AND side = 'SELL' AND status IN ('OPEN', 'PARTIAL') AND price <= %s
                ORDER BY price ASC, created_at ASC FOR UPDATE
                """,
                (stock_id, price),
            )
        else:
            cur.execute(
                """
                SELECT id, trader_name, account_no, price, quantity, remaining_qty, device_ip
                FROM orders
                WHERE stock_id = %s AND side = 'BUY' AND status IN ('OPEN', 'PARTIAL') AND price >= %s
                ORDER BY price DESC, created_at ASC FOR UPDATE
                """,
                (stock_id, price),
            )

        for rest_id, rest_trader, rest_acc, rest_price, rest_total_qty, rest_rem, rest_ip in cur.fetchall():
            if remaining == 0:
                break

            exec_qty = min(remaining, rest_rem)
            exec_price = rest_price  # Resting order sets execution price

            if side == "BUY":
                buy_ord_id, sell_ord_id = incoming_id, rest_id
                buyer, b_acc, b_ip = trader_name, account_no, device_ip
                seller, s_acc, s_ip = rest_trader, rest_acc, rest_ip
            else:
                buy_ord_id, sell_ord_id = rest_id, incoming_id
                buyer, b_acc, b_ip = rest_trader, rest_acc, rest_ip
                seller, s_acc, s_ip = trader_name, account_no, device_ip

            # 5. Record executed trade in MySQL
            cur.execute(
                """
                INSERT INTO trades (
                    stock_id, buy_order_id, sell_order_id,
                    buyer, buyer_account, seller, seller_account,
                    price, quantity, buyer_device, seller_device
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (stock_id, buy_ord_id, sell_ord_id, buyer, b_acc, seller, s_acc, exec_price, exec_qty, b_ip, s_ip),
            )

            # Settle Buyer (credit shares + refund any price difference)
            cur.execute("SELECT id FROM traders WHERE account_no = %s", (b_acc,))
            buyer_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE portfolios SET shares = shares + %s WHERE trader_id = %s AND stock_id = %s",
                (exec_qty, buyer_id, stock_id),
            )
            if side == "BUY" and price > exec_price:
                refund = (price - exec_price) * exec_qty
                cur.execute(
                    "UPDATE traders SET cash_balance = cash_balance + %s WHERE id = %s",
                    (refund, buyer_id),
                )

            # Settle Seller (credit cash)
            cur.execute(
                "UPDATE traders SET cash_balance = cash_balance + %s WHERE account_no = %s",
                (exec_price * exec_qty, s_acc),
            )

            # Update Resting Order Status (FILLED or PARTIAL)
            new_rest_rem = rest_rem - exec_qty
            rest_status = "FILLED" if new_rest_rem == 0 else "PARTIAL"
            cur.execute(
                "UPDATE orders SET remaining_qty = %s, status = %s WHERE id = %s",
                (new_rest_rem, rest_status, rest_id),
            )

            # Update Incoming Order Status (FILLED or PARTIAL)
            remaining -= exec_qty
            inc_status = "FILLED" if remaining == 0 else "PARTIAL"
            cur.execute(
                "UPDATE orders SET remaining_qty = %s, status = %s WHERE id = %s",
                (remaining, inc_status, incoming_id),
            )

            # Update Stock LTP & append point to history chart
            cur.execute("UPDATE stocks SET current_price = %s WHERE id = %s", (exec_price, stock_id))
            cur.execute(
                "INSERT INTO stock_history (stock_id, label, price) VALUES (%s, %s, %s)",
                (stock_id, datetime.now().strftime("%H:%M:%S"), exec_price),
            )

            match_logs.append(
                f"Matched {exec_qty} shares @ ₹{exec_price} ({buyer} [{b_acc}] <- {seller} [{s_acc}])"
            )

        conn.commit()
        return match_logs, remaining

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def cancel_order(order_id):
    conn = get_conn()
    cur = conn.cursor()

    try:
        conn.start_transaction()
        cur.execute(
            "SELECT account_no, stock_id, side, price, remaining_qty, status FROM orders WHERE id = %s FOR UPDATE",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise Exception("Order not found.")

        account_no, stock_id, side, price, rem_qty, status = row
        if status not in ("OPEN", "PARTIAL"):
            raise Exception("Only OPEN or PARTIAL orders can be cancelled.")

        # Unlock only the unexecuted remaining_qty
        if side == "BUY":
            cur.execute(
                "UPDATE traders SET cash_balance = cash_balance + %s WHERE account_no = %s",
                (price * rem_qty, account_no),
            )
        else:
            cur.execute(
                """
                UPDATE portfolios p JOIN traders t ON p.trader_id = t.id
                SET p.shares = p.shares + %s
                WHERE t.account_no = %s AND p.stock_id = %s
                """,
                (rem_qty, account_no, stock_id),
            )

        cur.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = %s", (order_id,))
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()