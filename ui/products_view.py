"""Product Management Screen (Module B).

Provides:
- Product catalog table
- Live search by name or SKU
- Filter by category and active/deactivated status
- Add product modal with comprehensive validation
- Edit product modal
- Safe deactivation / reactivation toggle
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
    COLOR_DANGER,
    COLOR_SUCCESS,
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


class ProductsView(tk.Frame):
    def __init__(self, parent: tk.Widget, *args, **kwargs):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)

        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._build_action_bar()

    def _build_header(self):
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill="x", padx=24, pady=(20, 10))

        title = tk.Label(header, text="Product Catalog Management", font=FONT_TITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_BG)
        title.pack(side="left")

        btn_add = ttk.Button(header, text="+ Add New Product", style="Primary.TButton", command=self._open_add_dialog)
        btn_add.pack(side="right")

    def _build_toolbar(self):
        toolbar = NeuPanel(self, pady=10)
        toolbar.pack(fill="x", padx=24, pady=(0, 12))

        # Search box
        lbl_search = tk.Label(toolbar, text="🔍 Search:", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE)
        lbl_search.pack(side="left", padx=(0, 6))

        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *args: self.refresh_table())
        entry_search = ttk.Entry(toolbar, textvariable=self.var_search, width=22)
        entry_search.pack(side="left", padx=(0, 20))

        # Category dropdown
        lbl_cat = tk.Label(toolbar, text="Category:", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE)
        lbl_cat.pack(side="left", padx=(0, 6))

        self.combo_category = ttk.Combobox(toolbar, state="readonly", width=18)
        self.combo_category.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        self.combo_category.pack(side="left", padx=(0, 20))

        # Active status toggle
        self.var_active_only = tk.BooleanVar(value=True)
        chk_active = ttk.Checkbutton(
            toolbar, text="Active Products Only", variable=self.var_active_only, command=self.refresh_table
        )
        chk_active.pack(side="left")

        # Reset button
        btn_clear = ttk.Button(toolbar, text="Clear Filters", style="Secondary.TButton", command=self._reset_filters)
        btn_clear.pack(side="right")

    def _build_table(self):
        table_panel = NeuPanel(self)
        table_panel.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        cols = [
            ("id", "ID", 45, "center"),
            ("sku", "SKU / Code", 100, "w"),
            ("name", "Product Name", 200, "w"),
            ("category", "Category", 110, "w"),
            ("price", "Unit Price", 90, "e"),
            ("cost_price", "Unit Cost", 85, "e"),
            ("stock", "In Stock", 75, "center"),
            ("min_threshold", "Min Threshold", 95, "center"),
            ("status", "Status", 80, "center"),
        ]

        self.tree, _, container = create_styled_table(table_panel, cols, selectmode="browse")
        self.tree.bind("<Double-1>", lambda e: self._open_edit_dialog())
        container.pack(fill="both", expand=True)

        # Style tags for row colors
        self.tree.tag_configure("low_stock", foreground="#b45309", background="#fffbeb")
        self.tree.tag_configure("out_of_stock", foreground="#b91c1c", background="#fee2e2")
        self.tree.tag_configure("inactive", foreground="#94a3b8")

    def _build_action_bar(self):
        bar = tk.Frame(self, bg=COLOR_BG)
        bar.pack(fill="x", padx=24, pady=(0, 20))

        btn_edit = ttk.Button(bar, text="✏️ Edit Selected", style="Secondary.TButton", command=self._open_edit_dialog)
        btn_edit.pack(side="left", padx=(0, 10))

        self.btn_toggle_active = ttk.Button(
            bar, text="Deactivate / Activate", style="Secondary.TButton", command=self._toggle_active_status
        )
        self.btn_toggle_active.pack(side="left", padx=(0, 10))

        self.lbl_count = tk.Label(bar, text="", font=FONT_SMALL, fg=COLOR_TEXT_MUTED, bg=COLOR_BG)
        self.lbl_count.pack(side="right")

    def _reset_filters(self):
        self.var_search.set("")
        self.combo_category.set("All Categories")
        self.var_active_only.set(True)
        self.refresh_table()

    def _get_selected_product_id(self) -> Optional[int]:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Selection Required", "Please select a product from the table first.")
            return None
        item = self.tree.item(selection[0])
        return int(item["values"][0])

    def _toggle_active_status(self):
        prod_id = self._get_selected_product_id()
        if not prod_id:
            return

        prod = inventory_service.get_product_by_id(prod_id)
        if not prod:
            return

        if prod["is_active"] == 1:
            confirm = messagebox.askyesno(
                "Confirm Deactivation",
                f"Are you sure you want to deactivate '{prod['name']}'?\n\n"
                "Deactivated products are hidden from the checkout screen, but their sales history remains safe.",
            )
            if confirm:
                inventory_service.deactivate_product(prod_id)
                self.refresh()
        else:
            inventory_service.reactivate_product(prod_id)
            self.refresh()

    def _open_add_dialog(self):
        ProductFormDialog(self, title="Add New Product", on_save=self.refresh)

    def _open_edit_dialog(self):
        prod_id = self._get_selected_product_id()
        if not prod_id:
            return
        prod = inventory_service.get_product_by_id(prod_id)
        if prod:
            ProductFormDialog(self, title="Edit Product Details", product=prod, on_save=self.refresh)

    def refresh_table(self):
        query = self.var_search.get().strip()
        cat = self.combo_category.get()
        active_only = self.var_active_only.get()

        selected_cat = None if cat in ("", "All Categories") else cat
        products = inventory_service.list_products(
            active_only=active_only, category=selected_cat, search_query=query
        )

        for item in self.tree.get_children():
            self.tree.delete(item)

        currency = get_setting("currency_symbol", "₹")

        for p in products:
            status = "Active" if p["is_active"] == 1 else "Inactive"
            stock = p["stock"]
            threshold = p["min_threshold"]

            tags = ()
            if p["is_active"] != 1:
                tags = ("inactive",)
            elif stock == 0:
                tags = ("out_of_stock",)
            elif stock <= threshold:
                tags = ("low_stock",)

            self.tree.insert(
                "",
                "end",
                values=(
                    p["id"],
                    p["sku"],
                    p["name"],
                    p["category"],
                    f"{currency}{p['price']:.2f}",
                    "—" if p.get("cost_price") is None else f"{currency}{p['cost_price']:.2f}",
                    stock,
                    threshold,
                    status,
                ),
                tags=tags,
            )

        self.lbl_count.config(text=f"Showing {len(products)} product(s)")

    def refresh(self):
        """Refreshes categories dropdown and table contents."""
        categories = ["All Categories"] + inventory_service.get_categories()
        current_cat = self.combo_category.get()
        self.combo_category["values"] = categories
        if current_cat in categories:
            self.combo_category.set(current_cat)
        else:
            self.combo_category.set("All Categories")

        self.refresh_table()


# ---------------------------------------------------------------------------
# Add / Edit Product Modal Dialog
# ---------------------------------------------------------------------------

class ProductFormDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        product: Optional[Dict[str, Any]] = None,
        on_save: Optional[callable] = None,
    ):
        super().__init__(parent)
        self.title(title)
        self.product = product
        self.on_save = on_save

        self.geometry("480x560")
        self.minsize(440, 520)
        self.configure(bg=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._build_form()
        self._populate_fields()

    def _build_form(self):
        container = NeuPanel(self, padx=20, pady=20)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # SKU
        tk.Label(container, text="SKU / Barcode *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_sku = ttk.Entry(container)
        self.entry_sku.pack(fill="x", pady=(2, 10))

        # Name
        tk.Label(container, text="Product Name *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_name = ttk.Entry(container)
        self.entry_name.pack(fill="x", pady=(2, 10))

        # Category
        tk.Label(container, text="Category", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        existing_cats = inventory_service.get_categories()
        self.combo_cat = ttk.Combobox(container, values=existing_cats)
        self.combo_cat.pack(fill="x", pady=(2, 10))

        # Price and Stock in two columns
        row_frame = tk.Frame(container, bg=COLOR_SURFACE)
        row_frame.pack(fill="x", pady=(0, 10))
        row_frame.columnconfigure(0, weight=1)
        row_frame.columnconfigure(1, weight=1)

        col1 = tk.Frame(row_frame, bg=COLOR_SURFACE)
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        currency = get_setting("currency_symbol", "₹")
        tk.Label(col1, text=f"Unit Selling Price ({currency}) *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_price = ttk.Entry(col1)
        self.entry_price.pack(fill="x", pady=(2, 0))

        col2 = tk.Frame(row_frame, bg=COLOR_SURFACE)
        col2.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        if not self.product:
            tk.Label(col2, text="Initial Stock Qty *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
            self.entry_stock = ttk.Entry(col2)
            self.entry_stock.pack(fill="x", pady=(2, 0))
            self.entry_stock.insert(0, "0")
        else:
            tk.Label(col2, text="Current Stock (Read-only)", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE).pack(anchor="w")
            self.lbl_stock_display = tk.Label(col2, text=str(self.product["stock"]), font=FONT_BODY_BOLD, fg=COLOR_PRIMARY, bg=COLOR_SURFACE)
            self.lbl_stock_display.pack(anchor="w", pady=(4, 0))

        # Optional cost price enables honest inventory valuation and profit estimates.
        tk.Label(container, text=f"Unit Cost Price ({currency}, optional)", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w", pady=(10, 0))
        self.entry_cost = ttk.Entry(container)
        self.entry_cost.pack(fill="x", pady=(2, 10))

        # Threshold
        tk.Label(container, text="Minimum Stock Alert Threshold *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_thresh = ttk.Entry(container)
        self.entry_thresh.pack(fill="x", pady=(2, 10))
        self.entry_thresh.insert(0, "5")

        # Description
        tk.Label(container, text="Description (Optional)", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_desc = ttk.Entry(container)
        self.entry_desc.pack(fill="x", pady=(2, 16))

        # Buttons
        btn_frame = tk.Frame(container, bg=COLOR_SURFACE)
        btn_frame.pack(fill="x", side="bottom")

        btn_cancel = ttk.Button(btn_frame, text="Cancel", style="Secondary.TButton", command=self.destroy)
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_save = ttk.Button(btn_frame, text="Save Product", style="Primary.TButton", command=self._save)
        btn_save.pack(side="right")

    def _populate_fields(self):
        if self.product:
            self.entry_sku.insert(0, self.product["sku"])
            self.entry_name.insert(0, self.product["name"])
            self.combo_cat.set(self.product["category"])
            self.entry_price.insert(0, f"{self.product['price']:.2f}")
            self.entry_thresh.delete(0, tk.END)
            self.entry_thresh.insert(0, str(self.product["min_threshold"]))
            if self.product.get("description"):
                self.entry_desc.insert(0, self.product["description"])
            if self.product.get("cost_price") is not None:
                self.entry_cost.insert(0, f"{self.product['cost_price']:.2f}")

    def _save(self):
        sku = self.entry_sku.get().strip()
        name = self.entry_name.get().strip()
        category = self.combo_cat.get().strip() or "General"
        price_str = self.entry_price.get().strip()
        thresh_str = self.entry_thresh.get().strip()
        desc = self.entry_desc.get().strip()
        cost = self.entry_cost.get().strip() or None

        try:
            if not self.product:
                stock_str = self.entry_stock.get().strip()
                inventory_service.create_product(
                    sku=sku,
                    name=name,
                    price=price_str,
                    stock=stock_str,
                    min_threshold=thresh_str,
                    category=category,
                    description=desc,
                    cost_price=cost,
                )
                messagebox.showinfo("Success", f"Product '{name}' added successfully!")
            else:
                inventory_service.update_product(
                    product_id=self.product["id"],
                    sku=sku,
                    name=name,
                    price=price_str,
                    min_threshold=thresh_str,
                    category=category,
                    description=desc,
                    cost_price=cost,
                )
                messagebox.showinfo("Success", f"Product '{name}' updated successfully!")

            if self.on_save:
                self.on_save()
            self.destroy()

        except inventory_service.InventoryError as err:
            messagebox.showerror("Validation Error", str(err))
        except Exception as err:
            messagebox.showerror("Error", f"Failed to save product: {err}")
