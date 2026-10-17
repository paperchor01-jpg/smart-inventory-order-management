"""Checkout & Order Processing Screen (Module D & E).

Provides:
- Product search & selection with live stock availability
- Interactive shopping cart with quantity modifications & line totals
- Real-time subtotal, discount, and tax calculation
- Atomic transaction checkout with duplicate submission prevention
- Printable text receipt generation and receipt viewer modal
"""

import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, List, Optional

from database import get_setting
from services import inventory_service, checkout_service
from ui.components import (
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
    COLOR_DANGER,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    FONT_TITLE,
    FONT_SUBTITLE,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    FONT_METRIC_VAL,
    NeuPanel,
    create_styled_table,
)


class CheckoutView(tk.Frame):
    def __init__(self, parent: tk.Widget, *args, **kwargs):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)

        # In-memory cart: list of dicts: {"product_id", "sku", "name", "unit_price", "quantity", "stock"}
        self.cart: List[Dict[str, Any]] = []
        self.is_processing = False

        self._build_header()
        self._build_layout()

    def _build_header(self):
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill="x", padx=24, pady=(20, 10))

        title = tk.Label(header, text="Checkout & Order Processing", font=FONT_TITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_BG)
        title.pack(side="left")

        btn_clear = ttk.Button(header, text="Clear Cart", style="Secondary.TButton", command=self._clear_cart)
        btn_clear.pack(side="right")

    def _build_layout(self):
        main_split = tk.Frame(self, bg=COLOR_BG)
        main_split.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        main_split.columnconfigure(0, weight=5, uniform="split")  # Left: Product Picker
        main_split.columnconfigure(1, weight=7, uniform="split")  # Right: Cart & Summary
        main_split.rowconfigure(0, weight=1)

        # ================= LEFT COLUMN: PRODUCT PICKER =================
        left_panel = NeuPanel(main_split)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        lbl_catalog = tk.Label(left_panel, text="Select Products", font=FONT_SUBTITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE)
        lbl_catalog.pack(anchor="w", pady=(0, 8))

        # Search bar
        search_frame = tk.Frame(left_panel, bg=COLOR_SURFACE)
        search_frame.pack(fill="x", pady=(0, 8))

        tk.Label(search_frame, text="🔍", font=FONT_BODY, bg=COLOR_SURFACE).pack(side="left", padx=(0, 4))
        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *args: self._filter_catalog())
        entry_search = ttk.Entry(search_frame, textvariable=self.var_search)
        entry_search.pack(fill="x", expand=True)

        # Products list table
        cat_cols = [
            ("sku", "SKU", 80, "w"),
            ("name", "Product", 150, "w"),
            ("price", "Price", 70, "e"),
            ("stock", "Stock", 50, "center"),
        ]
        self.tree_catalog, _, cat_container = create_styled_table(left_panel, cat_cols, selectmode="browse")
        cat_container.pack(fill="both", expand=True, pady=(0, 10))

        # Quantity and Add button
        add_frame = tk.Frame(left_panel, bg=COLOR_SURFACE)
        add_frame.pack(fill="x")

        tk.Label(add_frame, text="Qty:", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(side="left", padx=(0, 6))
        self.var_qty = tk.StringVar(value="1")
        spin_qty = ttk.Spinbox(add_frame, from_=1, to=999, textvariable=self.var_qty, width=6)
        spin_qty.pack(side="left", padx=(0, 12))

        btn_add_to_cart = ttk.Button(add_frame, text="+ Add to Cart", style="Primary.TButton", command=self._add_selected_to_cart)
        btn_add_to_cart.pack(side="right", fill="x", expand=True)

        # ================= RIGHT COLUMN: CART & SUMMARY =================
        right_panel = NeuPanel(main_split)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        lbl_cart = tk.Label(right_panel, text="Current Cart Items", font=FONT_SUBTITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE)
        lbl_cart.pack(anchor="w", pady=(0, 8))

        cart_cols = [
            ("sku", "SKU", 75, "w"),
            ("name", "Item Name", 160, "w"),
            ("price", "Unit Price", 75, "e"),
            ("qty", "Qty", 55, "center"),
            ("total", "Line Total", 85, "e"),
        ]
        self.tree_cart, _, cart_container = create_styled_table(right_panel, cart_cols, selectmode="browse")
        cart_container.pack(fill="both", expand=True, pady=(0, 8))

        # Cart item actions
        cart_actions = tk.Frame(right_panel, bg=COLOR_SURFACE)
        cart_actions.pack(fill="x", pady=(0, 10))

        btn_remove = ttk.Button(cart_actions, text="Remove Selected", style="Secondary.TButton", command=self._remove_selected_cart_item)
        btn_remove.pack(side="left", padx=(0, 8))

        btn_inc = ttk.Button(cart_actions, text="+ Qty", style="Secondary.TButton", command=lambda: self._adjust_cart_item_qty(1))
        btn_inc.pack(side="left", padx=(0, 4))

        btn_dec = ttk.Button(cart_actions, text="- Qty", style="Secondary.TButton", command=lambda: self._adjust_cart_item_qty(-1))
        btn_dec.pack(side="left")

        # Order calculations panel
        calc_panel = tk.Frame(right_panel, bg=COLOR_SURFACE, highlightbackground=COLOR_BG, highlightthickness=1, padx=12, pady=10)
        calc_panel.pack(fill="x", pady=(0, 10))
        calc_panel.columnconfigure(1, weight=1)

        # 1. Subtotal
        tk.Label(calc_panel, text="Subtotal:", font=FONT_BODY, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE).grid(row=0, column=0, sticky="w", pady=2)
        self.lbl_subtotal = tk.Label(calc_panel, text="₹0.00", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE)
        self.lbl_subtotal.grid(row=0, column=1, sticky="e", pady=2)

        # 2. Discount Input
        currency = get_setting("currency_symbol", "₹")
        tk.Label(calc_panel, text=f"Discount ({currency}):", font=FONT_BODY, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE).grid(row=1, column=0, sticky="w", pady=2)
        self.var_discount = tk.StringVar(value="0.00")
        self.var_discount.trace_add("write", lambda *args: self._update_totals_display())
        entry_discount = ttk.Entry(calc_panel, textvariable=self.var_discount, width=10, justify="right")
        entry_discount.grid(row=1, column=1, sticky="e", pady=2)

        # 3. Tax Display
        self.lbl_tax_title = tk.Label(calc_panel, text="Tax (0.0%):", font=FONT_BODY, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE)
        self.lbl_tax_title.grid(row=2, column=0, sticky="w", pady=2)
        self.lbl_tax_amt = tk.Label(calc_panel, text="₹0.00", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE)
        self.lbl_tax_amt.grid(row=2, column=1, sticky="e", pady=2)

        # Divider
        tk.Frame(calc_panel, bg=COLOR_BG, height=2).grid(row=3, column=0, columnspan=2, sticky="ew", pady=6)

        # 4. Total Payable
        tk.Label(calc_panel, text="TOTAL PAYABLE:", font=FONT_SUBTITLE, fg=COLOR_PRIMARY, bg=COLOR_SURFACE).grid(row=4, column=0, sticky="w")
        self.lbl_total = tk.Label(calc_panel, text="₹0.00", font=FONT_METRIC_VAL, fg=COLOR_PRIMARY, bg=COLOR_SURFACE)
        self.lbl_total.grid(row=4, column=1, sticky="e")

        # Big Checkout Button
        self.btn_checkout = ttk.Button(
            right_panel,
            text="✓ Complete Sale & Issue Receipt",
            style="Primary.TButton",
            command=self._execute_checkout,
        )
        self.btn_checkout.pack(fill="x", ipady=4)

    def _filter_catalog(self):
        query = self.var_search.get().strip()
        products = inventory_service.list_products(active_only=True, search_query=query)

        for item in self.tree_catalog.get_children():
            self.tree_catalog.delete(item)

        currency = get_setting("currency_symbol", "₹")
        for p in products:
            self.tree_catalog.insert(
                "",
                "end",
                iid=str(p["id"]),
                values=(
                    p["sku"],
                    p["name"],
                    f"{currency}{p['price']:.2f}",
                    p["stock"],
                ),
            )

    def _add_selected_to_cart(self):
        selection = self.tree_catalog.selection()
        if not selection:
            messagebox.showinfo("Selection Required", "Please select a product from the catalog on the left.")
            return

        prod_id = int(selection[0])
        prod = inventory_service.get_product_by_id(prod_id)
        if not prod or prod["is_active"] != 1:
            messagebox.showerror("Error", "Product is not available.")
            return

        try:
            qty_to_add = int(self.var_qty.get().strip())
            if qty_to_add <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            messagebox.showerror("Invalid Quantity", "Please enter a valid positive quantity.")
            return

        # Check existing quantity in cart
        existing = next((item for item in self.cart if item["product_id"] == prod_id), None)
        total_requested = (existing["quantity"] if existing else 0) + qty_to_add

        if total_requested > prod["stock"]:
            messagebox.showwarning(
                "Insufficient Stock",
                f"Cannot add {qty_to_add} more. Only {prod['stock']} available in stock.\n"
                f"Currently in cart: {existing['quantity'] if existing else 0}.",
            )
            return

        if existing:
            existing["quantity"] += qty_to_add
        else:
            self.cart.append({
                "product_id": prod["id"],
                "sku": prod["sku"],
                "name": prod["name"],
                "unit_price": prod["price"],
                "quantity": qty_to_add,
                "stock": prod["stock"],
            })

        self.var_qty.set("1")
        self._refresh_cart_table()

    def _remove_selected_cart_item(self):
        selection = self.tree_cart.selection()
        if not selection:
            return
        idx = int(selection[0])
        if 0 <= idx < len(self.cart):
            self.cart.pop(idx)
            self._refresh_cart_table()

    def _adjust_cart_item_qty(self, delta: int):
        selection = self.tree_cart.selection()
        if not selection:
            return
        idx = int(selection[0])
        if 0 <= idx < len(self.cart):
            item = self.cart[idx]
            new_qty = item["quantity"] + delta
            if new_qty <= 0:
                self.cart.pop(idx)
            else:
                # Check live stock limit
                prod = inventory_service.get_product_by_id(item["product_id"])
                if prod and new_qty > prod["stock"]:
                    messagebox.showwarning("Stock Limit", f"Only {prod['stock']} units available in stock.")
                    return
                item["quantity"] = new_qty
            self._refresh_cart_table()

    def _clear_cart(self):
        if not self.cart:
            return
        if messagebox.askyesno("Clear Cart", "Are you sure you want to remove all items from the cart?"):
            self.cart.clear()
            self._refresh_cart_table()

    def _refresh_cart_table(self):
        for it in self.tree_cart.get_children():
            self.tree_cart.delete(it)

        currency = get_setting("currency_symbol", "₹")

        for idx, item in enumerate(self.cart):
            line_tot = item["unit_price"] * item["quantity"]
            self.tree_cart.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    item["sku"],
                    item["name"],
                    f"{currency}{item['unit_price']:.2f}",
                    item["quantity"],
                    f"{currency}{line_tot:.2f}",
                ),
            )

        self._update_totals_display()

    def _get_tax_rate(self) -> float:
        saved = get_setting("tax_rate_percent", "0.0")
        try:
            return float(saved)
        except (ValueError, TypeError):
            return 0.0

    def _update_totals_display(self):
        currency = get_setting("currency_symbol", "₹")
        tax_rate = self._get_tax_rate()
        self.lbl_tax_title.config(text=f"Tax ({tax_rate:.1f}%):")

        if not self.cart:
            self.lbl_subtotal.config(text=f"{currency}0.00")
            self.lbl_tax_amt.config(text=f"{currency}0.00")
            self.lbl_total.config(text=f"{currency}0.00")
            return

        calc_items = [{"unit_price": it["unit_price"], "quantity": it["quantity"]} for it in self.cart]

        disc_str = self.var_discount.get().strip()
        try:
            disc_val = float(disc_str) if disc_str else 0.0
        except ValueError:
            disc_val = 0.0

        try:
            totals = checkout_service.calculate_totals(calc_items, discount_amount=disc_val, tax_rate_percent=tax_rate)
            self.lbl_subtotal.config(text=f"{currency}{totals['subtotal']:.2f}")
            self.lbl_tax_amt.config(text=f"{currency}{totals['tax_amount']:.2f}")
            self.lbl_total.config(text=f"{currency}{totals['total_amount']:.2f}")
        except Exception:
            # If discount is currently being typed and invalid, don't crash
            pass

    def _execute_checkout(self):
        if not self.cart:
            messagebox.showinfo("Empty Cart", "Cannot checkout with an empty cart.")
            return

        if self.is_processing:
            return

        disc_str = self.var_discount.get().strip()
        try:
            disc_val = float(disc_str) if disc_str else 0.0
            if disc_val < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Discount", "Please enter a valid non-negative number for discount.")
            return

        self.is_processing = True
        self.btn_checkout.config(state="disabled")

        try:
            checkout_items = [{"product_id": it["product_id"], "quantity": it["quantity"]} for it in self.cart]
            order = checkout_service.process_checkout(
                cart_items=checkout_items,
                discount_amount=disc_val,
                tax_rate_percent=self._get_tax_rate(),
                notes="Sale through POS checkout",
            )

            # Success! Clear cart
            self.cart.clear()
            self.var_discount.set("0.00")
            self._refresh_cart_table()
            self._filter_catalog()

            # Open Receipt Modal
            ReceiptModalDialog(self, order)

        except (checkout_service.InsufficientStockError, checkout_service.ValidationError) as err:
            messagebox.showerror("Checkout Error", str(err))
            self._filter_catalog()  # refresh catalog to show up-to-date stocks
        except Exception as err:
            messagebox.showerror("Checkout Failed", f"An unexpected error occurred: {err}")
        finally:
            self.is_processing = False
            self.btn_checkout.config(state="normal")

    def refresh(self):
        """Refreshes product list and current totals."""
        self._filter_catalog()
        self._update_totals_display()


# ---------------------------------------------------------------------------
# Order Receipt Modal Dialog
# ---------------------------------------------------------------------------

class ReceiptModalDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, order_data: Dict[str, Any]):
        super().__init__(parent)
        self.order_data = order_data
        self.title(f"Receipt - {order_data['order_number']}")

        self.geometry("500x580")
        self.minsize(460, 520)
        self.configure(bg=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        container = NeuPanel(self, padx=16, pady=16)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        # Success Title
        tk.Label(
            container,
            text="✓ Order Completed Successfully!",
            font=FONT_SUBTITLE,
            fg=COLOR_SUCCESS,
            bg=COLOR_SURFACE,
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            container,
            text=f"Order Number: {self.order_data['order_number']}",
            font=FONT_BODY_BOLD,
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_SURFACE,
        ).pack(anchor="w", pady=(0, 10))

        # Text area for formatted monospace receipt
        txt_frame = tk.Frame(container, bg=COLOR_SURFACE)
        txt_frame.pack(fill="both", expand=True, pady=(0, 14))

        sb = ttk.Scrollbar(txt_frame)
        sb.pack(side="right", fill="y")

        self.txt_receipt = tk.Text(
            txt_frame,
            font=("Consolas", 10),
            bg="#ffffff",
            fg="#0f172a",
            padx=10,
            pady=10,
            yscrollcommand=sb.set,
            relief="solid",
            borderwidth=1,
        )
        self.txt_receipt.pack(side="left", fill="both", expand=True)
        sb.config(command=self.txt_receipt.yview)

        # Populate receipt content
        receipt_text = checkout_service.get_receipt_text(self.order_data["order_number"])
        self.txt_receipt.insert("1.0", receipt_text)
        self.txt_receipt.config(state="disabled")

        # Buttons
        btn_frame = tk.Frame(container, bg=COLOR_SURFACE)
        btn_frame.pack(fill="x", side="bottom")

        btn_close = ttk.Button(btn_frame, text="Done / New Sale", style="Primary.TButton", command=self.destroy)
        btn_close.pack(side="right")

        btn_open = ttk.Button(btn_frame, text="📄 Open Receipt File", style="Secondary.TButton", command=self._open_file)
        btn_open.pack(side="right", padx=(0, 8))

        btn_copy = ttk.Button(btn_frame, text="📋 Copy Text", style="Secondary.TButton", command=self._copy_text)
        btn_copy.pack(side="right", padx=(0, 8))

    def _open_file(self):
        filepath = self.order_data.get("receipt_path")
        if filepath and os.path.exists(filepath):
            try:
                os.startfile(filepath)
            except Exception as e:
                messagebox.showinfo("Receipt Path", f"Receipt saved at:\n{filepath}")
        else:
            messagebox.showinfo("Receipt File", "Receipt text regenerated from database.")

    def _copy_text(self):
        text = checkout_service.get_receipt_text(self.order_data["order_number"])
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Receipt text copied to clipboard!")
