"""Reports & Analytics Screen (Module G).

Provides:
- Date-range filtered sales summaries (Total Orders, Total Revenue, Avg Order Value)
- Best-selling products by quantity and revenue
- Completed orders transactions table
- Instant standard CSV export actions with safe file paths
"""

import os
import tkinter as tk
from datetime import datetime, date, timedelta
from tkinter import ttk, messagebox, filedialog
from typing import Optional

from database import get_setting
from services import report_service, checkout_service
from ui.components import (
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    FONT_TITLE,
    FONT_SUBTITLE,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    FONT_METRIC_VAL,
    NeuPanel,
    MetricCard,
    create_styled_table,
)


class ReportsView(tk.Frame):
    def __init__(self, parent: tk.Widget, *args, **kwargs):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)

        self._build_header()
        self._build_filter_bar()
        self._build_summary_cards()
        self._build_tables_split()

    def _build_header(self):
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill="x", padx=24, pady=(20, 10))

        title = tk.Label(header, text="Sales Reports & Analytics", font=FONT_TITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_BG)
        title.pack(side="left")

        # Export buttons
        btn_frame = tk.Frame(header, bg=COLOR_BG)
        btn_frame.pack(side="right")

        btn_exp_sales = ttk.Button(btn_frame, text="📥 Export Sales CSV", style="Primary.TButton", command=self._export_sales)
        btn_exp_sales.pack(side="left", padx=(0, 8))

        btn_exp_prods = ttk.Button(btn_frame, text="📦 Export Catalog CSV", style="Secondary.TButton", command=self._export_products)
        btn_exp_prods.pack(side="left", padx=(0, 8))

        btn_exp_movs = ttk.Button(btn_frame, text="📋 Export Stock Log CSV", style="Secondary.TButton", command=self._export_movements)
        btn_exp_movs.pack(side="left")

    def _build_filter_bar(self):
        filter_panel = NeuPanel(self, pady=10)
        filter_panel.pack(fill="x", padx=24, pady=(0, 12))

        # Start Date
        tk.Label(filter_panel, text="From Date (YYYY-MM-DD):", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE).pack(side="left", padx=(0, 6))
        self.var_start = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        entry_start = ttk.Entry(filter_panel, textvariable=self.var_start, width=12)
        entry_start.pack(side="left", padx=(0, 16))

        # End Date
        tk.Label(filter_panel, text="To Date (YYYY-MM-DD):", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE).pack(side="left", padx=(0, 6))
        self.var_end = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        entry_end = ttk.Entry(filter_panel, textvariable=self.var_end, width=12)
        entry_end.pack(side="left", padx=(0, 16))

        # Filter Apply Button
        btn_filter = ttk.Button(filter_panel, text="Apply Filter", style="Primary.TButton", command=self.refresh)
        btn_filter.pack(side="left", padx=(0, 12))

        # Quick Preset Buttons
        lbl_presets = tk.Label(filter_panel, text="Presets:", font=FONT_SMALL, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE)
        lbl_presets.pack(side="left", padx=(10, 6))

        btn_today = ttk.Button(filter_panel, text="Today", style="Secondary.TButton", command=self._preset_today)
        btn_today.pack(side="left", padx=(0, 4))

        btn_7days = ttk.Button(filter_panel, text="Last 7 Days", style="Secondary.TButton", command=self._preset_week)
        btn_7days.pack(side="left", padx=(0, 4))

        btn_all = ttk.Button(filter_panel, text="All Time", style="Secondary.TButton", command=self._preset_all)
        btn_all.pack(side="left")

    def _build_summary_cards(self):
        cards_frame = tk.Frame(self, bg=COLOR_BG)
        cards_frame.pack(fill="x", padx=24, pady=(0, 12))
        for i in range(5):
            cards_frame.columnconfigure(i, weight=1, uniform="rep_card")

        self.card_rev = MetricCard(cards_frame, title="Total Revenue", value="₹0.00", subtitle="Period gross sales", accent_color=COLOR_SUCCESS)
        self.card_rev.grid(row=0, column=0, padx=(0, 10), sticky="nsew")

        self.card_orders = MetricCard(cards_frame, title="Completed Orders", value="0", subtitle="Total transactions", accent_color=COLOR_PRIMARY)
        self.card_orders.grid(row=0, column=1, padx=(0, 10), sticky="nsew")

        self.card_avg = MetricCard(cards_frame, title="Average Order Value", value="₹0.00", subtitle="Per-order average", accent_color="#8b5cf6")
        self.card_avg.grid(row=0, column=2, padx=(0, 10), sticky="nsew")

        self.card_cost = MetricCard(cards_frame, title="Estimated Cost", value="—", subtitle="Requires cost prices", accent_color=COLOR_WARNING)
        self.card_cost.grid(row=0, column=3, padx=(0, 10), sticky="nsew")

        self.card_profit = MetricCard(cards_frame, title="Est. Gross Profit", value="—", subtitle="Before tax", accent_color=COLOR_SUCCESS)
        self.card_profit.grid(row=0, column=4, padx=0, sticky="nsew")

        self.lbl_stock_valuation = tk.Label(self, text="", font=FONT_SMALL, fg=COLOR_TEXT_MUTED, bg=COLOR_BG)
        self.lbl_stock_valuation.pack(anchor="w", padx=24, pady=(0, 8))

    def _build_tables_split(self):
        split_frame = tk.Frame(self, bg=COLOR_BG)
        split_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        split_frame.columnconfigure(0, weight=1, uniform="rep_split")
        split_frame.columnconfigure(1, weight=1, uniform="rep_split")
        split_frame.rowconfigure(0, weight=1)

        # Left: Completed Orders Table
        left_panel = NeuPanel(split_frame)
        left_panel.grid(row=0, column=0, padx=(0, 10), sticky="nsew")

        tk.Label(left_panel, text="Order Transactions", font=FONT_SUBTITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w", pady=(0, 8))

        ord_cols = [
            ("order_number", "Order ID", 140, "w"),
            ("created_at", "Date & Time", 140, "center"),
            ("subtotal", "Subtotal", 75, "e"),
            ("discount", "Discount", 70, "e"),
            ("total", "Total", 85, "e"),
            ("status", "Status", 85, "center"),
        ]
        self.tree_orders, _, ord_container = create_styled_table(left_panel, ord_cols)
        self.tree_orders.bind("<Double-1>", lambda _event: self._show_selected_order())
        ord_container.pack(fill="both", expand=True)

        order_actions = tk.Frame(left_panel, bg=COLOR_SURFACE)
        order_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(order_actions, text="View Details", style="Secondary.TButton", command=self._show_selected_order).pack(side="left")
        ttk.Button(order_actions, text="Cancel Selected Order", style="Danger.TButton", command=self._cancel_selected_order).pack(side="right")
        self.tree_orders.tag_configure("cancelled", foreground=COLOR_TEXT_MUTED)

        # Right: Best-Selling Products Table
        right_panel = NeuPanel(split_frame)
        right_panel.grid(row=0, column=1, padx=(10, 0), sticky="nsew")

        tk.Label(right_panel, text="Best-Selling Products", font=FONT_SUBTITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w", pady=(0, 8))

        best_cols = [
            ("sku", "SKU", 85, "w"),
            ("name", "Product Name", 160, "w"),
            ("qty", "Qty Sold", 75, "center"),
            ("revenue", "Revenue", 90, "e"),
        ]
        self.tree_best, _, best_container = create_styled_table(right_panel, best_cols)
        best_container.pack(fill="both", expand=True)

    def _preset_today(self):
        today = date.today().strftime("%Y-%m-%d")
        self.var_start.set(today)
        self.var_end.set(today)
        self.refresh()

    def _preset_week(self):
        today = date.today()
        week_ago = today - timedelta(days=7)
        self.var_start.set(week_ago.strftime("%Y-%m-%d"))
        self.var_end.set(today.strftime("%Y-%m-%d"))
        self.refresh()

    def _preset_all(self):
        self.var_start.set("")
        self.var_end.set("")
        self.refresh()

    def _export_sales(self):
        start = self.var_start.get().strip() or None
        end = self.var_end.get().strip() or None
        path = self._choose_export_path("sales_report")
        if not path:
            return
        try:
            path = report_service.export_sales_to_csv(start_date=start, end_date=end, file_path=path)
            messagebox.showinfo("Export Successful", f"Sales report exported successfully to:\n\n{path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export sales: {e}")

    def _export_products(self):
        path = self._choose_export_path("products_catalog")
        if not path:
            return
        try:
            path = report_service.export_products_to_csv(file_path=path)
            messagebox.showinfo("Export Successful", f"Product catalog exported successfully to:\n\n{path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export products: {e}")

    def _export_movements(self):
        path = self._choose_export_path("stock_movements")
        if not path:
            return
        try:
            path = report_service.export_stock_movements_to_csv(file_path=path)
            messagebox.showinfo("Export Successful", f"Stock movements log exported successfully to:\n\n{path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export stock movements: {e}")

    def _choose_export_path(self, name: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return filedialog.asksaveasfilename(
            parent=self,
            title="Save CSV Report",
            initialdir=report_service.EXPORTS_DIR,
            initialfile=f"{name}_{stamp}.csv",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )

    def _selected_order_number(self) -> Optional[str]:
        selected = self.tree_orders.selection()
        if not selected:
            messagebox.showinfo("Select an Order", "Select an order from the table first.")
            return None
        return str(self.tree_orders.item(selected[0], "values")[0])

    def _show_selected_order(self):
        number = self._selected_order_number()
        if not number:
            return
        order = checkout_service.get_order_by_number(number)
        if not order:
            messagebox.showerror("Order Not Found", f"Order {number} could not be loaded.")
            return
        currency = get_setting("currency_symbol", "₹")
        lines = [
            f"Order: {order['order_number']}",
            f"Date: {order['created_at']}",
            f"Status: {order.get('status', 'COMPLETED')}",
            "",
        ]
        for item in order["items"]:
            lines.append(
                f"{item['product_name']} ({item['product_sku']})  × {item['quantity']}  "
                f"{currency}{item['line_total']:.2f}"
            )
        lines.extend([
            "",
            f"Subtotal: {currency}{order['subtotal']:.2f}",
            f"Discount: {currency}{order['discount_amount']:.2f}",
            f"Tax: {currency}{order['tax_amount']:.2f}",
            f"Total: {currency}{order['total_amount']:.2f}",
        ])
        messagebox.showinfo("Order Details", "\n".join(lines))

    def _cancel_selected_order(self):
        number = self._selected_order_number()
        if not number:
            return
        if not messagebox.askyesno(
            "Cancel Order",
            f"Cancel order {number}? Its sold quantities will be returned to stock and recorded in the stock audit.",
        ):
            return
        try:
            checkout_service.cancel_order(number)
            self.refresh()
            messagebox.showinfo("Order Cancelled", f"Order {number} was cancelled and stock was restored.")
        except checkout_service.ValidationError as err:
            messagebox.showerror("Cannot Cancel Order", str(err))
        except Exception as err:
            messagebox.showerror("Cancellation Failed", f"The order could not be cancelled: {err}")

    def refresh(self):
        """Fetches sales reports and best-selling metrics for the selected date range."""
        start = self.var_start.get().strip() or None
        end = self.var_end.get().strip() or None

        currency = get_setting("currency_symbol", "₹")

        # 1. Fetch Sales Report
        try:
            report = report_service.get_sales_report(start_date=start, end_date=end)
            orders = checkout_service.list_orders(start_date=start, end_date=end)
        except ValueError as err:
            messagebox.showerror("Invalid Date Range", str(err))
            return
        self.card_rev.update_value(f"{currency}{report['total_revenue']:.2f}")
        self.card_orders.update_value(str(report["total_orders"]))
        self.card_avg.update_value(f"{currency}{report['avg_order_value']:.2f}")
        inventory_metrics = report_service.get_dashboard_metrics()
        if inventory_metrics["cost_inventory_value"] is None:
            valuation_text = (
                "Current inventory valuation at cost: N/A — cost price is missing for "
                f"{inventory_metrics['uncosted_stock_products']} in-stock product(s)."
            )
        else:
            valuation_text = (
                f"Current inventory valuation at cost: {currency}"
                f"{inventory_metrics['cost_inventory_value']:.2f}"
            )
        self.lbl_stock_valuation.config(text=valuation_text)
        if report["estimated_cost"] is None:
            self.card_cost.update_value("N/A", "Some items have no cost price")
            self.card_profit.update_value("N/A", "Add costs to estimate profit")
        else:
            self.card_cost.update_value(f"{currency}{report['estimated_cost']:.2f}", "From saved item cost prices")
            self.card_profit.update_value(
                f"{currency}{report['estimated_gross_profit']:.2f}",
                "After discounts, before tax",
            )

        # Populate Orders Table
        for it in self.tree_orders.get_children():
            self.tree_orders.delete(it)

        for o in orders:
            self.tree_orders.insert(
                "",
                "end",
                values=(
                    o["order_number"],
                    o["created_at"],
                    f"{currency}{o['subtotal']:.2f}",
                    f"{currency}{o['discount_amount']:.2f}",
                    f"{currency}{o['total_amount']:.2f}",
                    o.get("status", "COMPLETED"),
                ),
                tags=("cancelled",) if o.get("status") == "CANCELLED" else (),
            )

        # 2. Fetch Best-Selling Products
        for it in self.tree_best.get_children():
            self.tree_best.delete(it)

        best_sellers = report_service.get_best_selling_products(start_date=start, end_date=end)
        for b in best_sellers:
            self.tree_best.insert(
                "",
                "end",
                values=(
                    b["product_sku"],
                    b["product_name"],
                    b["total_quantity_sold"],
                    f"{currency}{b['total_revenue_generated']:.2f}",
                ),
            )
