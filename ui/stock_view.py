"""Stock Management Screen (Module C & F).

Provides:
- Current inventory view with low-stock / critical alerts
- Transaction-safe stock adjustments (Incoming Restock, Damage, Loss, Returns)
- Comprehensive stock movement audit history table
- Reason and notes tracking for all movements
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any

from database import get_setting
from services import inventory_service
from ui.components import (
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_DANGER,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    FONT_TITLE,
    FONT_SUBTITLE,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    NeuPanel,
    create_styled_table,
)


class StockView(tk.Frame):
    def __init__(self, parent: tk.Widget, *args, **kwargs):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)

        self._build_header()
        self._build_split_tables()

    def _build_header(self):
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill="x", padx=24, pady=(20, 10))

        title = tk.Label(header, text="Stock & Inventory Tracking", font=FONT_TITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_BG)
        title.pack(side="left")

        btn_adjust = ttk.Button(
            header,
            text="⚡ Adjust Stock (Restock / Damage)",
            style="Primary.TButton",
            command=self._open_adjust_dialog,
        )
        btn_adjust.pack(side="right")

    def _build_split_tables(self):
        main_split = tk.Frame(self, bg=COLOR_BG)
        main_split.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        main_split.rowconfigure(0, weight=1)
        main_split.rowconfigure(1, weight=1)
        main_split.columnconfigure(0, weight=1)

        # ---------------- Top: Current Inventory Table ----------------
        top_panel = NeuPanel(main_split)
        top_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        top_header = tk.Frame(top_panel, bg=COLOR_SURFACE)
        top_header.pack(fill="x", pady=(0, 8))

        lbl_inv = tk.Label(top_header, text="Current Stock Levels", font=FONT_SUBTITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE)
        lbl_inv.pack(side="left")

        lbl_hint = tk.Label(
            top_header,
            text="(Double-click an item to adjust stock)",
            font=FONT_SMALL,
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        lbl_hint.pack(side="left", padx=(10, 0))

        inv_cols = [
            ("id", "ID", 45, "center"),
            ("sku", "SKU", 90, "w"),
            ("name", "Product Name", 220, "w"),
            ("category", "Category", 110, "w"),
            ("stock", "Current Stock", 90, "center"),
            ("min_threshold", "Min Threshold", 95, "center"),
            ("stock_status", "Stock Status", 110, "center"),
        ]

        self.tree_inv, _, inv_container = create_styled_table(top_panel, inv_cols, selectmode="browse")
        self.tree_inv.bind("<Double-1>", lambda e: self._open_adjust_dialog())
        inv_container.pack(fill="both", expand=True)

        self.tree_inv.tag_configure("ok", foreground="#16a34a")
        self.tree_inv.tag_configure("low", foreground="#b45309", background="#fffbeb")
        self.tree_inv.tag_configure("out", foreground="#b91c1c", background="#fee2e2")

        # ---------------- Bottom: Stock Movement Audit Log ----------------
        bot_panel = NeuPanel(main_split)
        bot_panel.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        bot_header = tk.Frame(bot_panel, bg=COLOR_SURFACE)
        bot_header.pack(fill="x", pady=(0, 8))

        lbl_hist = tk.Label(bot_header, text="Audit Trail: Recent Stock Movements", font=FONT_SUBTITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE)
        lbl_hist.pack(side="left")

        hist_cols = [
            ("created_at", "Date & Time", 140, "center"),
            ("product_sku", "SKU", 85, "w"),
            ("product_name", "Product Name", 180, "w"),
            ("change_quantity", "Change Qty", 85, "center"),
            ("previous_stock", "Prev Stock", 80, "center"),
            ("new_stock", "New Stock", 80, "center"),
            ("reason", "Reason", 100, "w"),
            ("notes", "Notes / Ref", 180, "w"),
        ]

        self.tree_hist, _, hist_container = create_styled_table(bot_panel, hist_cols, selectmode="browse")
        hist_container.pack(fill="both", expand=True)

        self.tree_hist.tag_configure("in", foreground="#16a34a")
        self.tree_hist.tag_configure("out", foreground="#dc2626")

    def _open_adjust_dialog(self):
        selection = self.tree_inv.selection()
        selected_prod = None
        if selection:
            item = self.tree_inv.item(selection[0])
            prod_id = int(item["values"][0])
            selected_prod = inventory_service.get_product_by_id(prod_id)

        StockAdjustmentDialog(self, product=selected_prod, on_success=self.refresh)

    def refresh(self):
        """Refreshes both the inventory table and the movement audit table."""
        # 1. Populate Inventory
        for it in self.tree_inv.get_children():
            self.tree_inv.delete(it)

        products = inventory_service.list_products(active_only=False)
        for p in products:
            stock = p["stock"]
            threshold = p["min_threshold"]
            if stock == 0:
                status_text = "OUT OF STOCK"
                tag = "out"
            elif stock <= threshold:
                status_text = "LOW STOCK"
                tag = "low"
            else:
                status_text = "In Stock"
                tag = "ok"

            self.tree_inv.insert(
                "",
                "end",
                values=(
                    p["id"],
                    p["sku"],
                    p["name"],
                    p["category"],
                    stock,
                    threshold,
                    status_text,
                ),
                tags=(tag,),
            )

        # 2. Populate Stock Movements History
        for it in self.tree_hist.get_children():
            self.tree_hist.delete(it)

        movements = inventory_service.get_stock_movements(limit=50)
        for m in movements:
            chg = m["change_quantity"]
            chg_str = f"+{chg}" if chg > 0 else str(chg)
            tag = "in" if chg > 0 else "out"

            notes_str = m["notes"] or ""
            if m.get("reference_id"):
                notes_str = f"[{m['reference_id']}] {notes_str}".strip()

            self.tree_hist.insert(
                "",
                "end",
                values=(
                    m["created_at"],
                    m.get("product_sku", "N/A"),
                    m.get("product_name", "N/A"),
                    chg_str,
                    m["previous_stock"],
                    m["new_stock"],
                    m["reason"],
                    notes_str,
                ),
                tags=(tag,),
            )


# ---------------------------------------------------------------------------
# Stock Adjustment Modal Dialog
# ---------------------------------------------------------------------------

class StockAdjustmentDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        product: Optional[Dict[str, Any]] = None,
        on_success: Optional[callable] = None,
    ):
        super().__init__(parent)
        self.title("Adjust Product Stock")
        self.product = product
        self.on_success = on_success

        self.geometry("450x460")
        self.minsize(420, 420)
        self.configure(bg=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._build_form()

    def _build_form(self):
        container = NeuPanel(self, padx=20, pady=20)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Product selection
        tk.Label(container, text="Select Product *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")

        self.products = inventory_service.list_products(active_only=True)
        prod_options = [f"[{p['sku']}] {p['name']} (Current Stock: {p['stock']})" for p in self.products]

        self.combo_product = ttk.Combobox(container, values=prod_options, state="readonly")
        self.combo_product.pack(fill="x", pady=(2, 12))

        # Select preselected product if provided
        if self.product:
            for idx, p in enumerate(self.products):
                if p["id"] == self.product["id"]:
                    self.combo_product.current(idx)
                    break
        elif prod_options:
            self.combo_product.current(0)

        # Adjustment Type (Incoming / Outgoing)
        tk.Label(container, text="Action Type *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.var_type = tk.StringVar(value="RESTOCK")
        type_frame = tk.Frame(container, bg=COLOR_SURFACE)
        type_frame.pack(fill="x", pady=(2, 12))

        rb_in = ttk.Radiobutton(type_frame, text="Incoming / Restock (+)", variable=self.var_type, value="RESTOCK")
        rb_in.pack(side="left", padx=(0, 16))
        rb_out = ttk.Radiobutton(type_frame, text="Outgoing / Damage (-)", variable=self.var_type, value="OUTGOING")
        rb_out.pack(side="left")

        # Quantity
        tk.Label(container, text="Quantity *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_qty = ttk.Entry(container)
        self.entry_qty.pack(fill="x", pady=(2, 12))
        self.entry_qty.insert(0, "1")

        # Specific Reason
        tk.Label(container, text="Reason *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.reasons = [
            "RESTOCK",
            "CUSTOMER_RETURN",
            "SUPPLIER_SHIPMENT",
            "DAMAGED_GOODS",
            "EXPIRY_WASTE",
            "INVENTORY_CORRECTION",
            "OTHER",
        ]
        self.combo_reason = ttk.Combobox(container, values=self.reasons)
        self.combo_reason.pack(fill="x", pady=(2, 12))
        self.combo_reason.set("RESTOCK")

        # Notes
        tk.Label(container, text="Notes (Optional)", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_notes = ttk.Entry(container)
        self.entry_notes.pack(fill="x", pady=(2, 20))

        # Buttons
        btn_frame = tk.Frame(container, bg=COLOR_SURFACE)
        btn_frame.pack(fill="x", side="bottom")

        btn_cancel = ttk.Button(btn_frame, text="Cancel", style="Secondary.TButton", command=self.destroy)
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_save = ttk.Button(btn_frame, text="Apply Adjustment", style="Primary.TButton", command=self._apply_adjustment)
        btn_save.pack(side="right")

    def _apply_adjustment(self):
        sel_idx = self.combo_product.current()
        if sel_idx < 0 or sel_idx >= len(self.products):
            messagebox.showerror("Selection Error", "Please select a valid product.")
            return

        prod = self.products[sel_idx]
        prod_id = prod["id"]

        qty_str = self.entry_qty.get().strip()
        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            messagebox.showerror("Invalid Quantity", "Please enter a positive whole number for quantity.")
            return

        action_type = self.var_type.get()
        change_quantity = qty if action_type == "RESTOCK" else -qty
        reason = self.combo_reason.get().strip() or "ADJUSTMENT"
        notes = self.entry_notes.get().strip()

        try:
            res = inventory_service.adjust_stock(
                product_id=prod_id,
                change_quantity=change_quantity,
                reason=reason,
                notes=notes,
            )

            messagebox.showinfo(
                "Adjustment Applied",
                f"Stock updated for '{prod['name']}'.\n\n"
                f"Previous: {res['previous_stock']} units\n"
                f"Change: {res['change_quantity']:+d} units\n"
                f"New Stock: {res['new_stock']} units",
            )

            if self.on_success:
                self.on_success()
            self.destroy()

        except inventory_service.InsufficientStockError as err:
            messagebox.showerror("Insufficient Stock", str(err))
        except inventory_service.InventoryError as err:
            messagebox.showerror("Validation Error", str(err))
        except Exception as err:
            messagebox.showerror("Error", f"Failed to apply stock adjustment: {err}")
