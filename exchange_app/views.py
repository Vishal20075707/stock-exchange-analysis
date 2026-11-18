import json
from decimal import Decimal
from django.shortcuts import render, redirect
from django.urls import reverse

from db_config import get_conn
from module1_matching import place_and_match_order, cancel_order
from module2_fraud import run_fraud_detection


def index(request):
    active_tab = request.GET.get("tab", "dashboard")
    order_banner = request.session.pop("order_banner", None)
    book_banner = request.session.pop("book_banner", None)

    conn = get_conn()
    cur = conn.cursor()

    # 1. KPI Summary & 5 Stock Charts (Tab 1)
    cur.execute("SELECT COUNT(*) FROM orders WHERE status IN ('OPEN', 'PARTIAL')")
    open_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM trades")
    trade_cnt = cur.fetchone()[0]

    cur.execute("SELECT id, symbol, name, current_price FROM stocks")
    stocks_raw = cur.fetchall()

    stocks_list = []
    stock_charts = []
    for sid, symbol, name, price in stocks_raw:
        stocks_list.append({
            "id": sid,
            "symbol": symbol,
            "name": name,
            "price": str(price),
        })
        cur.execute("SELECT label, price FROM stock_history WHERE stock_id = %s ORDER BY id ASC", (sid,))
        rows = cur.fetchall()
        stock_charts.append({
            "id": sid,
            "title": f"{name} ({symbol}) — ₹{price}",
            "labels": [r[0] for r in rows],
            "prices": [float(r[1]) for r in rows],
        })

    # 2. Active Order Book & Trader Wallets (Tab 3)
    cur.execute("""
        SELECT o.id, o.trader_name, o.account_no, s.symbol, o.side, o.price, o.quantity, o.remaining_qty, o.status, o.device_ip
        FROM orders o JOIN stocks s ON o.stock_id = s.id
        WHERE o.status IN ('OPEN', 'PARTIAL') ORDER BY o.created_at DESC
    """)
    open_orders = cur.fetchall()

    cur.execute("SELECT name, account_no, cash_balance FROM traders ORDER BY id ASC")
    wallets = cur.fetchall()

    # 3. Fraud Analysis (Tab 4 — runs when user opens Tab 4 or clicks Scan)
    fraud_report = None
    fraud_chart_json = "{}"
    if active_tab == "analysis" or request.GET.get("scan") == "1":
        fraud_report = run_fraud_detection()
        cat_labels = list(fraud_report["category_counts"].keys())
        cat_counts = list(fraud_report["category_counts"].values())
        cat_colors = ["#10B981" if lbl == "SAFE" else "#DC2626" for lbl in cat_labels]

        trader_names = [t[0] for t in fraud_report["trader_stats"]]
        trader_filled = [t[1] for t in fraud_report["trader_stats"]]
        trader_cancelled = [t[2] for t in fraud_report["trader_stats"]]

        fraud_chart_json = json.dumps({
            "cat_labels": cat_labels,
            "cat_counts": cat_counts,
            "cat_colors": cat_colors,
            "trader_names": trader_names,
            "trader_filled": trader_filled,
            "trader_cancelled": trader_cancelled,
        })

    # 4. Interactive MySQL Query Lab (Tab 5)
    default_sql = "SELECT * FROM fraud_alerts ORDER BY id DESC;"
    sql_query = request.GET.get("sql", default_sql).strip()
    sql_cols = []
    sql_rows = []
    sql_error = None

    if active_tab == "sql":
        try:
            cur.execute(sql_query)
            if cur.description:
                sql_cols = [desc[0] for desc in cur.description]
                sql_rows = cur.fetchall()
            else:
                conn.commit()
        except Exception as e:
            sql_error = str(e)

    conn.close()

    context = {
        "active_tab": active_tab,
        "open_cnt": open_cnt,
        "trade_cnt": trade_cnt,
        "stocks_list": stocks_list,
        "stock_charts_json": json.dumps(stock_charts),
        "stock_charts": stock_charts,
        "open_orders": open_orders,
        "wallets": wallets,
        "order_banner": order_banner,
        "book_banner": book_banner,
        "fraud_report": fraud_report,
        "fraud_chart_json": fraud_chart_json,
        "sql_query": sql_query,
        "sql_cols": sql_cols,
        "sql_rows": sql_rows,
        "sql_error": sql_error,
    }
    return render(request, "exchange_app/index.html", context)


def submit_order(request):
    if request.method == "POST":
        trader_name = request.POST.get("trader_name", "").strip()
        account_no = request.POST.get("account_no", "").strip().upper()
        stock_id = int(request.POST.get("stock_id"))
        side = request.POST.get("side", "BUY")
        ip_addr = request.POST.get("device_ip", "").strip() or "192.168.1.10"

        try:
            qty = int(request.POST.get("quantity"))
            price = Decimal(request.POST.get("price"))
            if qty <= 0 or price <= 0:
                raise ValueError("Quantity and Price must be positive numbers.")

            logs, remaining = place_and_match_order(
                trader_name, account_no, stock_id, side, price, qty, ip_addr
            )
            if logs:
                request.session["order_banner"] = {
                    "type": "success",
                    "text": f"MATCHED & SETTLED: {' | '.join(logs)} (Remaining open: {remaining})",
                }
            else:
                request.session["order_banner"] = {
                    "type": "info",
                    "text": f"QUEUED IN ORDER BOOK: {trader_name} ({account_no}) placed {side} {qty} @ ₹{price}. Waiting for counterparty.",
                }
        except Exception as e:
            request.session["order_banner"] = {
                "type": "error",
                "text": f"ORDER REJECTED: {str(e)}",
            }

    return redirect(f"{reverse('index')}?tab=order")


def cancel_order_view(request, order_id):
    if request.method == "POST":
        try:
            cancel_order(order_id)
            request.session["book_banner"] = {
                "type": "success",
                "text": f"Order #{order_id} cancelled and unfilled funds/shares unlocked.",
            }
        except Exception as e:
            request.session["book_banner"] = {
                "type": "error",
                "text": str(e),
            }
    return redirect(f"{reverse('index')}?tab=book")