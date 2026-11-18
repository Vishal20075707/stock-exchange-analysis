import tkinter as tk
from tkinter import ttk, messagebox
from decimal import Decimal

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MATPLOTLIB = True
except Exception:
    HAS_MATPLOTLIB = False

from db_config import get_conn
from module1_matching import place_and_match_order, cancel_order
from module2_fraud import run_fraud_detection


class StockExchangeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Stock Exchange | Order Matching & SQL Fraud Detection")
        self.root.geometry("1280x800")
        self.root.configure(bg="#F1F5F9")

        self.setup_styles()
        self.build_header()
        self.build_tabs()
        self.refresh_all()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#F1F5F9", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[16, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#FFFFFF")], foreground=[("selected", "#0F172A")])
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#E2E8F0")
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))

    def build_header(self):
        header = tk.Frame(self.root, bg="#0F172A", padx=24, pady=16)
        header.pack(fill="x")

        tk.Label(
            header, text="APEX STOCK EXCHANGE SURVEILLANCE",
            fg="#94A3B8", bg="#0F172A", font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")

        tk.Label(
            header, text="Order Matching & SQL-Based Fraud Detection System",
            fg="#FFFFFF", bg="#0F172A", font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", pady=(2, 2))

        tk.Label(
            header, text="Module 1: Price-Time Priority Matching  |  Module 2: MySQL Fraud Surveillance",
            fg="#CBD5E1", bg="#0F172A", font=("Segoe UI", 9)
        ).pack(anchor="w")

    def build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=12)

        self.tab_dashboard = tk.Frame(self.notebook, bg="#FFFFFF")
        self.tab_order = tk.Frame(self.notebook, bg="#FFFFFF")
        self.tab_book = tk.Frame(self.notebook, bg="#FFFFFF")
        self.tab_analysis = tk.Frame(self.notebook, bg="#FFFFFF")
        self.tab_sql = tk.Frame(self.notebook, bg="#FFFFFF")

        self.notebook.add(self.tab_dashboard, text="1. Market Dashboard (5 Stocks)")
        self.notebook.add(self.tab_order, text="2. Buy / Sell Order")
        self.notebook.add(self.tab_book, text="3. Order Book & Wallets")
        self.notebook.add(self.tab_analysis, text="4. Fraud Analysis (Safe vs Fraud)")
        self.notebook.add(self.tab_sql, text="5. MySQL Query Lab")

        self.init_dashboard_tab()
        self.init_order_tab()
        self.init_book_tab()
        self.init_analysis_tab()
        self.init_sql_tab()

        # Auto-refresh charts, dropdown prices & order book whenever switching tabs
        self.notebook.bind("<<NotebookTabChanged>>", lambda event: self.refresh_all())

    # ---------------------------------------------------------
    # TAB 1: MARKET DASHBOARD (5 STOCK GRAPHS)
    # ---------------------------------------------------------
    def init_dashboard_tab(self):
        top = tk.Frame(self.tab_dashboard, bg="#FFFFFF", padx=16, pady=10)
        top.pack(fill="x")

        self.kpi_label = tk.Label(top, text="Loading...", bg="#FFFFFF", fg="#0F172A", font=("Segoe UI", 11, "bold"))
        self.kpi_label.pack(side="left")

        tk.Button(
            top, text="Refresh Stock Graphs", command=self.render_stock_charts,
            bg="#1D4ED8", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        ).pack(side="right")

        self.charts_container = tk.Frame(self.tab_dashboard, bg="#FFFFFF", padx=10, pady=5)
        self.charts_container.pack(fill="both", expand=True)

    def render_stock_charts(self):
        for w in self.charts_container.winfo_children():
            w.destroy()

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM orders WHERE status IN ('OPEN', 'PARTIAL')")
        open_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM trades")
        trade_cnt = cur.fetchone()[0]
        self.kpi_label.config(
            text=f"Exchange Live Summary   |   Listed Stocks: 5   |   Active Orders: {open_cnt}   |   Settled Trades: {trade_cnt}"
        )

        cur.execute("SELECT id, symbol, name, current_price FROM stocks")
        stocks = cur.fetchall()

        stock_series = []
        for sid, symbol, name, price in stocks:
            cur.execute("SELECT label, price FROM stock_history WHERE stock_id = %s ORDER BY id ASC", (sid,))
            rows = cur.fetchall()
            stock_series.append((symbol, name, price, [r[0] for r in rows], [float(r[1]) for r in rows]))
        conn.close()

        if HAS_MATPLOTLIB:
            fig = Figure(figsize=(12, 5.4), dpi=95)
            fig.patch.set_facecolor("#FFFFFF")
            for idx, (symbol, name, price, labels, prices) in enumerate(stock_series, start=1):
                ax = fig.add_subplot(2, 3, idx)
                ax.plot(labels, prices, marker="o", markersize=3.5, color="#1D4ED8", linewidth=1.8)
                ax.set_title(f"{name} ({symbol}) — ₹{price}", fontsize=9.5, fontweight="bold", color="#0F172A")
                ax.tick_params(axis="x", rotation=30, labelsize=7)
                ax.tick_params(axis="y", labelsize=8)
                ax.grid(True, linestyle="--", alpha=0.4)
            fig.tight_layout(pad=2.0)
            canvas = FigureCanvasTkAgg(fig, master=self.charts_container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            # Native Tkinter Canvas Fallback (100% DLL-free)
            for idx, (symbol, name, price, labels, prices) in enumerate(stock_series):
                r, c = divmod(idx, 3)
                cv = tk.Canvas(
                    self.charts_container, width=380, height=240,
                    bg="#F8FAFC", highlightthickness=1, highlightbackground="#CBD5E1"
                )
                cv.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
                cv.create_text(190, 18, text=f"{name} ({symbol}) — ₹{price}", font=("Segoe UI", 10, "bold"), fill="#0F172A")

                if len(prices) >= 2:
                    x0, y0, x1, y1 = 55, 42, 355, 195
                    cv.create_line(x0, y0, x0, y1, fill="#94A3B8")
                    cv.create_line(x0, y1, x1, y1, fill="#94A3B8")

                    min_p, max_p = min(prices), max(prices)
                    span = (max_p - min_p) or 1.0
                    cv.create_text(x0 - 6, y0 + 5, text=f"₹{max_p:.0f}", anchor="e", font=("Segoe UI", 8), fill="#475569")
                    cv.create_text(x0 - 6, y1 - 5, text=f"₹{min_p:.0f}", anchor="e", font=("Segoe UI", 8), fill="#475569")
                    cv.create_text(x0, y1 + 14, text=labels[0], anchor="w", font=("Segoe UI", 8), fill="#475569")
                    cv.create_text(x1, y1 + 14, text=labels[-1], anchor="e", font=("Segoe UI", 8), fill="#475569")

                    pts = []
                    for i, p in enumerate(prices):
                        px = x0 + (i / (len(prices) - 1)) * (x1 - x0)
                        py = y1 - ((p - min_p) / span) * (y1 - y0)
                        pts.append((px, py))

                    for i in range(len(pts) - 1):
                        cv.create_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], fill="#1D4ED8", width=2)
                    for px, py in pts:
                        cv.create_oval(px - 2.5, py - 2.5, px + 2.5, py + 2.5, fill="#1D4ED8", outline="")

    # ---------------------------------------------------------
    # TAB 2: BUY / SELL ORDER ENTRY (MODULE 1)
    # ---------------------------------------------------------
    def init_order_tab(self):
        wrapper = tk.Frame(self.tab_order, bg="#FFFFFF", padx=24, pady=18)
        wrapper.pack(fill="both", expand=True)

        tk.Label(wrapper, text="Place Buy / Sell Stock Order", bg="#FFFFFF", fg="#0F172A", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(
            wrapper,
            text="Enter Trader Name, Account No., Company Stock, and Buy/Sell action. New accounts start with ₹1,00,000 & 100 shares/stock.",
            bg="#FFFFFF", fg="#64748B", font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(2, 14))

        form = tk.LabelFrame(wrapper, text=" Order Entry Details ", bg="#F8FAFC", fg="#1E293B", font=("Segoe UI", 9, "bold"), padx=20, pady=16)
        form.pack(fill="x")

        tk.Label(form, text="Trader / Client Name", bg="#F8FAFC", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=7, padx=(0, 12))
        self.ent_trader = ttk.Entry(form, width=32)
        self.ent_trader.grid(row=0, column=1, sticky="w", pady=7, padx=(0, 40))

        tk.Label(form, text="Account Number", bg="#F8FAFC", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", pady=7, padx=(0, 12))
        self.ent_account = ttk.Entry(form, width=32)
        self.ent_account.grid(row=0, column=3, sticky="w", pady=7)

        tk.Label(form, text="Company Stock", bg="#F8FAFC", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=7, padx=(0, 12))
        self.cmb_stock = ttk.Combobox(form, width=30, state="readonly")
        self.cmb_stock.grid(row=1, column=1, sticky="w", pady=7, padx=(0, 40))

        tk.Label(form, text="Order Action (BUY / SELL)", bg="#F8FAFC", font=("Segoe UI", 9, "bold")).grid(row=1, column=2, sticky="w", pady=7, padx=(0, 12))
        self.cmb_side = ttk.Combobox(form, values=["BUY", "SELL"], width=30, state="readonly")
        self.cmb_side.set("BUY")
        self.cmb_side.grid(row=1, column=3, sticky="w", pady=7)

        tk.Label(form, text="Quantity (No. of Shares)", bg="#F8FAFC", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=7, padx=(0, 12))
        self.ent_qty = ttk.Entry(form, width=32)
        self.ent_qty.grid(row=2, column=1, sticky="w", pady=7, padx=(0, 40))

        tk.Label(form, text="Price per Share (₹)", bg="#F8FAFC", font=("Segoe UI", 9)).grid(row=2, column=2, sticky="w", pady=7, padx=(0, 12))
        self.ent_price = ttk.Entry(form, width=32)
        self.ent_price.grid(row=2, column=3, sticky="w", pady=7)

        tk.Label(form, text="Device / IP Address", bg="#F8FAFC", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=7, padx=(0, 12))
        self.ent_ip = ttk.Entry(form, width=32)
        self.ent_ip.insert(0, "192.168.1.10")
        self.ent_ip.grid(row=3, column=1, sticky="w", pady=7, padx=(0, 40))

        btn_row = tk.Frame(form, bg="#F8FAFC")
        btn_row.grid(row=4, column=0, columnspan=4, sticky="w", pady=(14, 2))

        tk.Button(
            btn_row, text="Submit & Match Order", command=self.handle_submit_order,
            bg="#1D4ED8", fg="#FFFFFF", font=("Segoe UI", 9, "bold"), relief="flat", padx=18, pady=7, cursor="hand2"
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row, text="Clear Fields", command=self.clear_order_form,
            bg="#E2E8F0", fg="#1E293B", font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=7, cursor="hand2"
        ).pack(side="left")

        self.result_box = tk.Frame(wrapper, bg="#F8FAFC", highlightbackground="#CBD5E1", highlightthickness=1, padx=16, pady=14)
        self.result_box.pack(fill="x", pady=(16, 8))

        self.result_label = tk.Label(
            self.result_box,
            text="Order matching & MySQL settlement status will appear here after submission.",
            bg="#F8FAFC", fg="#1E293B", font=("Segoe UI", 10, "bold"), justify="left"
        )
        self.result_label.pack(anchor="w")

    def load_stock_dropdown(self):
        selected_idx = self.cmb_stock.current()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, symbol, name, current_price FROM stocks")
        self.stock_map = {}
        items = []
        for sid, sym, name, prc in cur.fetchall():
            label = f"{name} ({sym}) — ₹{prc}"
            self.stock_map[label] = sid
            items.append(label)
        self.cmb_stock["values"] = items
        if items:
            self.cmb_stock.set(items[selected_idx] if selected_idx >= 0 else items[0])
        conn.close()

    def clear_order_form(self):
        self.ent_trader.delete(0, tk.END)
        self.ent_account.delete(0, tk.END)
        self.ent_qty.delete(0, tk.END)
        self.ent_price.delete(0, tk.END)
        self.ent_ip.delete(0, tk.END)
        self.ent_ip.insert(0, "192.168.1.10")

    def handle_submit_order(self):
        trader_name = self.ent_trader.get().strip()
        account_no = self.ent_account.get().strip().upper()
        stock_label = self.cmb_stock.get()
        side = self.cmb_side.get()
        ip_addr = self.ent_ip.get().strip() or "192.168.1.10"

        if not trader_name or not account_no or not stock_label:
            messagebox.showwarning("Missing Fields", "Please enter Trader Name, Account Number, and select a Stock.")
            return

        try:
            qty = int(self.ent_qty.get())
            price = Decimal(self.ent_price.get())
            if qty <= 0 or price <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid Input", "Quantity and Price must be positive numbers.")
            return

        try:
            logs, remaining = place_and_match_order(
                trader_name, account_no, self.stock_map[stock_label], side, price, qty, ip_addr
            )
            if logs:
                self.result_box.config(bg="#ECFDF5", highlightbackground="#10B981")
                self.result_label.config(
                    text=f"MATCHED & SETTLED: {' | '.join(logs)} (Remaining open: {remaining})",
                    bg="#ECFDF5", fg="#065F46"
                )
            else:
                self.result_box.config(bg="#EFF6FF", highlightbackground="#3B82F6")
                self.result_label.config(
                    text=f"QUEUED IN ORDER BOOK: {trader_name} ({account_no}) placed {side} {qty} @ ₹{price}. Waiting for counterparty.",
                    bg="#EFF6FF", fg="#1E40AF"
                )
            self.refresh_all()
        except Exception as e:
            messagebox.showerror("Order Rejected", str(e))

    # ---------------------------------------------------------
    # TAB 3: ORDER BOOK, CANCELLATION & WALLETS (MODULE 1)
    # ---------------------------------------------------------
    def init_book_tab(self):
        container = tk.Frame(self.tab_book, bg="#FFFFFF", padx=16, pady=12)
        container.pack(fill="both", expand=True)

        top_bar = tk.Frame(container, bg="#FFFFFF")
        top_bar.pack(fill="x")
        tk.Label(
            top_bar, text="Active Order Book — OPEN & PARTIAL Orders (Select any row to Cancel)",
            bg="#FFFFFF", fg="#0F172A", font=("Segoe UI", 11, "bold")
        ).pack(side="left")
        tk.Button(
            top_bar, text="Cancel Selected Order", command=self.handle_cancel_order,
            bg="#DC2626", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        ).pack(side="right")

        cols_open = ("Order ID", "Trader", "Account No", "Stock", "Side", "Price", "Total Qty", "Remaining", "Status", "Device/IP")
        self.tree_open = ttk.Treeview(container, columns=cols_open, show="headings", height=8)
        for c in cols_open:
            self.tree_open.heading(c, text=c)
            self.tree_open.column(c, width=105, anchor="center")
        self.tree_open.pack(fill="x", pady=(6, 16))

        tk.Label(container, text="Trader Accounts & Available Cash Balances", bg="#FFFFFF", fg="#0F172A", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        cols_w = ("Trader Name", "Account No", "Cash Balance (₹)")
        self.tree_wallets = ttk.Treeview(container, columns=cols_w, show="headings", height=8)
        for c in cols_w:
            self.tree_wallets.heading(c, text=c)
            self.tree_wallets.column(c, width=180, anchor="center")
        self.tree_wallets.pack(fill="both", expand=True, pady=(6, 0))

    def refresh_book_tables(self):
        for tree in (self.tree_open, self.tree_wallets):
            for item in tree.get_children():
                tree.delete(item)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT o.id, o.trader_name, o.account_no, s.symbol, o.side, o.price, o.quantity, o.remaining_qty, o.status, o.device_ip
            FROM orders o JOIN stocks s ON o.stock_id = s.id
            WHERE o.status IN ('OPEN', 'PARTIAL') ORDER BY o.created_at DESC
        """)
        for row in cur.fetchall():
            self.tree_open.insert("", "end", values=row)

        cur.execute("SELECT name, account_no, cash_balance FROM traders ORDER BY id ASC")
        for row in cur.fetchall():
            self.tree_wallets.insert("", "end", values=row)
        conn.close()

    def handle_cancel_order(self):
        selected = self.tree_open.selection()
        if not selected:
            messagebox.showinfo("Select Order", "Click an OPEN or PARTIAL order row first to cancel it.")
            return

        order_id = self.tree_open.item(selected[0])["values"][0]
        try:
            cancel_order(order_id)
            messagebox.showinfo("Cancelled", f"Order #{order_id} cancelled and unfilled funds/shares unlocked.")
            self.refresh_all()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------------------------------------------------------
    # TAB 4: FRAUD ANALYSIS (MODULE 2 — SAFE VS FRAUD + GRAPHS)
    # ---------------------------------------------------------
    def init_analysis_tab(self):
        top = tk.Frame(self.tab_analysis, bg="#FFFFFF", padx=16, pady=10)
        top.pack(fill="x")

        tk.Button(
            top, text="Run SQL Fraud & Safety Analysis", command=self.run_full_analysis,
            bg="#D97706", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", padx=16, pady=6, cursor="hand2"
        ).pack(side="left", padx=(0, 16))

        self.analysis_summary = tk.Label(
            top, text="Click 'Run SQL Fraud & Safety Analysis' to classify all database transactions.",
            bg="#FFFFFF", fg="#0F172A", font=("Segoe UI", 10, "bold")
        )
        self.analysis_summary.pack(side="left")

        body = tk.Frame(self.tab_analysis, bg="#FFFFFF", padx=16, pady=6)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg="#FFFFFF")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        cols = ("Txn ID", "Stock", "Buyer (Acc)", "Seller (Acc)", "Qty", "Price", "Verdict", "Classification / Fraud Type")
        self.tree_analysis = ttk.Treeview(left, columns=cols, show="headings")
        widths = [55, 85, 115, 115, 50, 75, 75, 230]
        for c, w in zip(cols, widths):
            self.tree_analysis.heading(c, text=c)
            self.tree_analysis.column(c, width=w, anchor="center" if w < 100 else "w")

        self.tree_analysis.tag_configure("SAFE", background="#ECFDF5", foreground="#065F46")
        self.tree_analysis.tag_configure("FRAUD", background="#FEF2F2", foreground="#991B1B")
        self.tree_analysis.pack(fill="both", expand=True)

        self.analysis_chart_frame = tk.Frame(body, bg="#FFFFFF", width=440)
        self.analysis_chart_frame.pack(side="right", fill="both", expand=True)

    def run_full_analysis(self):
        for item in self.tree_analysis.get_children():
            self.tree_analysis.delete(item)

        report = run_fraud_detection()

        for row in report["rows"]:
            verdict = row[6]
            self.tree_analysis.insert("", "end", values=row, tags=(verdict,))

        self.analysis_summary.config(
            text=f"Total Trades Analyzed: {report['total']}   |   SAFE: {report['safe_count']}   |   FLAGGED FRAUD: {report['fraud_count']}"
        )

        for w in self.analysis_chart_frame.winfo_children():
            w.destroy()

        labels = list(report["category_counts"].keys())
        counts = list(report["category_counts"].values())

        if HAS_MATPLOTLIB:
            fig = Figure(figsize=(5.2, 5.2), dpi=90)
            fig.patch.set_facecolor("#FFFFFF")

            ax1 = fig.add_subplot(2, 1, 1)
            colors = ["#10B981" if lbl == "SAFE" else "#DC2626" for lbl in labels]
            ax1.barh(labels, counts, color=colors)
            ax1.set_title("Transaction Classification: Safe vs. Fraud Types", fontsize=9.5, fontweight="bold")
            ax1.tick_params(axis="y", labelsize=8)

            if report["trader_stats"]:
                names = [t[0] for t in report["trader_stats"]]
                filled = [t[1] for t in report["trader_stats"]]
                cancelled = [t[2] for t in report["trader_stats"]]

                ax2 = fig.add_subplot(2, 1, 2)
                ax2.bar(names, filled, label="Filled Orders (Safe)", color="#10B981")
                ax2.bar(names, cancelled, bottom=filled, label="Cancelled Orders (Spoofing)", color="#EF4444")
                ax2.set_title("Order Execution vs. Cancellation Pattern by Trader", fontsize=9.5, fontweight="bold")
                ax2.legend(fontsize=8)

            fig.tight_layout(pad=2.0)
            canvas = FigureCanvasTkAgg(fig, master=self.analysis_chart_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            # Native Tkinter Canvas Fallback (100% DLL-free)
            cv = tk.Canvas(
                self.analysis_chart_frame, width=440, height=500,
                bg="#F8FAFC", highlightthickness=1, highlightbackground="#CBD5E1"
            )
            cv.pack(fill="both", expand=True)
            cv.create_text(220, 20, text="Safe vs. Fraud Classification Breakdown", font=("Segoe UI", 10, "bold"), fill="#0F172A")

            max_c = max(counts) if counts and max(counts) > 0 else 1
            for idx, (lbl, cnt) in enumerate(zip(labels, counts)):
                y = 50 + idx * 34
                bar_color = "#10B981" if lbl == "SAFE" else "#DC2626"
                bar_w = int((cnt / max_c) * 180)
                cv.create_text(180, y + 10, text=lbl[:26], anchor="e", font=("Segoe UI", 8, "bold"), fill="#1E293B")
                cv.create_rectangle(190, y, 190 + bar_w, y + 20, fill=bar_color, outline="")
                cv.create_text(196 + bar_w, y + 10, text=str(cnt), anchor="w", font=("Segoe UI", 8, "bold"), fill="#0F172A")

            if report["trader_stats"]:
                base_y = 320
                cv.create_text(220, base_y, text="Order Fills (Green) vs. Cancellations (Red)", font=("Segoe UI", 10, "bold"), fill="#0F172A")
                for idx, (t_name, filled, cancelled) in enumerate(report["trader_stats"]):
                    y = base_y + 25 + idx * 32
                    cv.create_text(120, y + 9, text=t_name, anchor="e", font=("Segoe UI", 8, "bold"), fill="#1E293B")
                    f_w = min(filled * 22, 140)
                    c_w = min(cancelled * 22, 140)
                    cv.create_rectangle(130, y, 130 + f_w, y + 18, fill="#10B981", outline="")
                    cv.create_rectangle(130 + f_w, y, 130 + f_w + c_w, y + 18, fill="#EF4444", outline="")
                    cv.create_text(136 + f_w + c_w, y + 9, text=f"F:{filled} | C:{cancelled}", anchor="w", font=("Segoe UI", 8), fill="#334155")

    # ---------------------------------------------------------
    # TAB 5: INTERACTIVE MYSQL QUERY LAB
    # ---------------------------------------------------------
    def init_sql_tab(self):
        wrapper = tk.Frame(self.tab_sql, bg="#FFFFFF", padx=16, pady=12)
        wrapper.pack(fill="both", expand=True)

        tk.Label(wrapper, text="MySQL Live Query Lab (Inspect Any Table in stock_exchange_db)", bg="#FFFFFF", fg="#0F172A", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        presets = tk.Frame(wrapper, bg="#FFFFFF", pady=6)
        presets.pack(fill="x")

        quick_queries = {
            "All Trades": "SELECT id, stock_id, buy_order_id, sell_order_id, buyer, seller, price, quantity FROM trades ORDER BY id DESC;",
            "All Orders": "SELECT id, trader_name, account_no, side, price, quantity, remaining_qty, status FROM orders ORDER BY id DESC;",
            "Fraud Alerts Table": "SELECT * FROM fraud_alerts ORDER BY id DESC;",
            "Trader Portfolios": "SELECT t.name, t.account_no, s.symbol, p.shares FROM portfolios p JOIN traders t ON p.trader_id=t.id JOIN stocks s ON p.stock_id=s.id;",
        }
        for btn_text, sql in quick_queries.items():
            tk.Button(
                presets, text=btn_text, command=lambda q=sql: self.load_preset_sql(q),
                bg="#E2E8F0", fg="#0F172A", font=("Segoe UI", 8, "bold"), relief="flat", padx=10, pady=4, cursor="hand2"
            ).pack(side="left", padx=(0, 8))

        self.txt_sql = tk.Text(wrapper, height=4, font=("Consolas", 10), bg="#0F172A", fg="#38BDF8", insertbackground="white", padx=10, pady=8)
        self.txt_sql.pack(fill="x", pady=6)
        self.txt_sql.insert("1.0", "SELECT * FROM fraud_alerts ORDER BY id DESC;")

        tk.Button(
            wrapper, text="Run SQL Query", command=self.run_custom_sql,
            bg="#1D4ED8", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5, cursor="hand2"
        ).pack(anchor="w", pady=(0, 8))

        self.sql_tree_frame = tk.Frame(wrapper, bg="#FFFFFF")
        self.sql_tree_frame.pack(fill="both", expand=True)

    def load_preset_sql(self, sql):
        self.txt_sql.delete("1.0", tk.END)
        self.txt_sql.insert("1.0", sql)
        self.run_custom_sql()

    def run_custom_sql(self):
        for w in self.sql_tree_frame.winfo_children():
            w.destroy()

        query = self.txt_sql.get("1.0", tk.END).strip()
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute(query)
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            tree = ttk.Treeview(self.sql_tree_frame, columns=cols, show="headings")
            for c in cols:
                tree.heading(c, text=c)
                tree.column(c, width=125, anchor="center")
            for r in rows:
                tree.insert("", "end", values=r)
            tree.pack(fill="both", expand=True)
        except Exception as e:
            messagebox.showerror("SQL Error", str(e))
        finally:
            conn.close()

    def refresh_all(self):
        self.load_stock_dropdown()
        self.render_stock_charts()
        self.refresh_book_tables()


if __name__ == "__main__":
    root = tk.Tk()
    app = StockExchangeApp(root)
    root.mainloop()