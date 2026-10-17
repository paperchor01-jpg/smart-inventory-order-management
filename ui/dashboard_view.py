"""Dashboard Screen (Module A).

Displays 4 prominent neumorphic metric cards, quick action shortcuts,
recent orders table, and urgent low-stock alerts.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from database import get_setting
from services import report_service
from ui.components import (
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_PRIMARY,
    COLOR_WARNING,
    COLOR_SUCCESS,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    FONT_TITLE,
    FONT_SUBTITLE,
    FONT_BODY,
    FONT_BODY_BOLD,
    MetricCard,
    NeuPanel,
    create_styled_table,
)


class DashboardView(tk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        navigate_callback: Optional[Callable[[str], None]] = None,
        *args,
        **kwargs,
    ):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)
        self.navigate_callback = navigate_callback

        self._build_header()
        self._build_metric_cards()
        self._build_quick_actions()
        self._build_split_content()

    def _build_header(self):
        header_frame = tk.Frame(self, bg=COLOR_BG)
        header_frame.pack(fill="x", padx=24, pady=(20, 10))

        title = tk.Label(header_frame, text="Dashboard Overview", font=FONT_TITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_BG)
        title.pack(side="left")

        self.store_label = tk.Label(header_frame, text="", font=FONT_SUBTITLE, fg=COLOR_PRIMARY, bg=COLOR_BG)
        self.store_label.pack(side="right")

    def _build_metric_cards(self):
        cards_frame = tk.Frame(self, bg=COLOR_BG)
        cards_frame.pack(fill="x", padx=24, pady=10)

        # 5 columns with equal weight
        for i in range(5):
            cards_frame.columnconfigure(i, weight=1, uniform="card")

        # 1. Total Products
        self.card_products = MetricCard(
            cards_frame, title="Total Products", value="0", subtitle="Active items in catalog", accent_color=COLOR_PRIMARY
        )
        self.card_products.grid(row=0, column=0, padx=(0, 10), sticky="nsew")

        # 2. Low-Stock Products
        self.card_low_stock = MetricCard(
            cards_frame, title="Low-Stock Alert", value="0", subtitle="Items requiring reorder", accent_color=COLOR_WARNING
        )
        self.card_low_stock.grid(row=0, column=1, padx=(0, 10), sticky="nsew")

        # 3. Today's Sales
        self.card_sales = MetricCard(
            cards_frame, title="Today's Sales", value="₹0.00", subtitle="Completed sales today", accent_color=COLOR_SUCCESS
        )
        self.card_sales.grid(row=0, column=2, padx=(0, 10), sticky="nsew")

        # 4. Orders Today
        self.card_orders = MetricCard(
            cards_frame, title="Orders Today", value="0", subtitle="Total transactions", accent_color="#8b5cf6"
        )
        self.card_orders.grid(row=0, column=3, padx=(0, 10), sticky="nsew")

        self.card_out_stock = MetricCard(
            cards_frame, title="Out of Stock", value="0", subtitle="Active items at zero", accent_color="#dc2626"
        )
        self.card_out_stock.grid(row=0, column=4, padx=0, sticky="nsew")

    def _build_quick_actions(self):
        action_bar = tk.Frame(self, bg=COLOR_BG)
        action_bar.pack(fill="x", padx=24, pady=(10, 15))

        lbl = tk.Label(action_bar, text="Quick Shortcuts:", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MUTED, bg=COLOR_BG)
        lbl.pack(side="left", padx=(0, 12))

        btn_checkout = ttk.Button(
            action_bar,
            text="🛒 Open Checkout",
            style="Primary.TButton",
            command=lambda: self._navigate("checkout"),
        )
        btn_checkout.pack(side="left", padx=(0, 8))

        btn_add_prod = ttk.Button(
            action_bar,
            text="+ Add Product",
            style="Secondary.TButton",
            command=lambda: self._navigate("products"),
        )
        btn_add_prod.pack(side="left", padx=(0, 8))

        btn_restock = ttk.Button(
            action_bar,
            text="📦 Stock Management",
            style="Secondary.TButton",
            command=lambda: self._navigate("stock"),
        )
        btn_restock.pack(side="left")

    def _build_split_content(self):
        split_frame = tk.Frame(self, bg=COLOR_BG)
        split_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        split_frame.columnconfigure(0, weight=1, uniform="split")
        split_frame.columnconfigure(1, weight=1, uniform="split")
        split_frame.rowconfigure(0, weight=1)

        # Left Panel: Recent Completed Orders
        left_panel = NeuPanel(split_frame)
        left_panel.grid(row=0, column=0, padx=(0, 10), sticky="nsew")

        left_title = tk.Label(left_panel, text="Recent Completed Orders", font=FONT_SUBTITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE)
        left_title.pack(anchor="w", pady=(0, 10))

        order_cols = [
            ("order_number", "Order ID", 150, "w"),
            ("created_at", "Date & Time", 140, "center"),
            ("total_amount", "Total", 90, "e"),
        ]
        self.tree_orders, _, order_container = create_styled_table(left_panel, order_cols)
        order_container.pack(fill="both", expand=True)

        # Right Panel: Low Stock Alert Items
        right_panel = NeuPanel(split_frame)
        right_panel.grid(row=0, column=1, padx=(10, 0), sticky="nsew")

        right_title = tk.Label(right_panel, text="⚠️ Low Stock Alert (Needs Restock)", font=FONT_SUBTITLE, fg=COLOR_WARNING, bg=COLOR_SURFACE)
        right_title.pack(anchor="w", pady=(0, 10))

        stock_cols = [
            ("sku", "SKU", 80, "w"),
            ("name", "Product Name", 140, "w"),
            ("stock", "Stock", 60, "center"),
            ("min_threshold", "Min Mark", 70, "center"),
        ]
        self.tree_stock, _, stock_container = create_styled_table(right_panel, stock_cols)
        stock_container.pack(fill="both", expand=True)

    def _navigate(self, screen_name: str):
        if self.navigate_callback:
            self.navigate_callback(screen_name)

    def refresh(self):
        """Fetches live calculated metrics from SQLite database and updates all cards and tables."""
        store_name = get_setting("store_name", "Campus Store")
        self.store_label.config(text=f"🏪 {store_name}")

        metrics = report_service.get_dashboard_metrics()
        currency = metrics["currency_symbol"]

        # Update 4 Cards
        self.card_products.update_value(
            str(metrics["total_products"]),
            f"{metrics['total_units']} total units in stock",
        )

        low_count = metrics["low_stock_count"]
        low_sub = "All items well-stocked" if low_count == 0 else f"{low_count} item(s) below threshold!"
        self.card_low_stock.update_value(str(low_count), low_sub)

        self.card_sales.update_value(
            f"{currency}{metrics['today_sales_revenue']:.2f}",
            f"Retail stock value: {currency}{metrics['total_inventory_value']:.2f}",
        )

        self.card_orders.update_value(
            str(metrics["today_orders_count"]),
            "Completed orders today",
        )
        self.card_out_stock.update_value(str(metrics["out_of_stock_count"]), "Active items at zero stock")

        # Populate Recent Orders
        for item in self.tree_orders.get_children():
            self.tree_orders.delete(item)

        for ord_row in metrics.get("recent_orders", []):
            self.tree_orders.insert(
                "",
                "end",
                values=(
                    ord_row["order_number"],
                    ord_row["created_at"],
                    f"{currency}{ord_row['total_amount']:.2f}",
                ),
            )

        # Populate Low Stock Alert Table
        for item in self.tree_stock.get_children():
            self.tree_stock.delete(item)

        for prod in metrics.get("urgent_restock", []):
            self.tree_stock.insert(
                "",
                "end",
                values=(
                    prod["sku"],
                    prod["name"],
                    prod["stock"],
                    prod["min_threshold"],
                ),
            )
