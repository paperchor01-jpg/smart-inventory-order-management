"""Settings Screen.

Allows customization of:
- Store name (displayed on dashboard, receipts, and invoices)
- Currency symbol (default: ₹)
- Default tax percentage (default: 0.0%)
- Receipt footer message
- Settings persistence across application restarts
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable

from database import get_setting, set_setting
from ui.components import (
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    FONT_TITLE,
    FONT_SUBTITLE,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    NeuPanel,
)


class SettingsView(tk.Frame):
    def __init__(self, parent: tk.Widget, on_settings_changed: Optional[Callable[[], None]] = None, *args, **kwargs):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)
        self.on_settings_changed = on_settings_changed

        self._build_header()
        self._build_form()

    def _build_header(self):
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill="x", padx=24, pady=(20, 10))

        title = tk.Label(header, text="Application & Store Settings", font=FONT_TITLE, fg=COLOR_TEXT_MAIN, bg=COLOR_BG)
        title.pack(side="left")

    def _build_form(self):
        form_panel = NeuPanel(self, padx=24, pady=24)
        form_panel.pack(fill="x", padx=24, pady=(0, 20))

        # Store Name
        tk.Label(form_panel, text="Store / Business Name *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_store = ttk.Entry(form_panel, width=40)
        self.entry_store.pack(fill="x", pady=(4, 16))

        # Currency and Tax in two columns
        row_frame = tk.Frame(form_panel, bg=COLOR_SURFACE)
        row_frame.pack(fill="x", pady=(0, 16))
        row_frame.columnconfigure(0, weight=1)
        row_frame.columnconfigure(1, weight=1)

        # Currency Symbol
        col1 = tk.Frame(row_frame, bg=COLOR_SURFACE)
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        tk.Label(col1, text="Currency Symbol *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_currency = ttk.Entry(col1)
        self.entry_currency.pack(fill="x", pady=(4, 0))

        # Tax Percentage
        col2 = tk.Frame(row_frame, bg=COLOR_SURFACE)
        col2.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        tk.Label(col2, text="Default Tax Rate (%) *", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_tax = ttk.Entry(col2)
        self.entry_tax.pack(fill="x", pady=(4, 0))

        # Receipt Footer
        tk.Label(form_panel, text="Receipt Footer Message", font=FONT_BODY_BOLD, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE).pack(anchor="w")
        self.entry_footer = ttk.Entry(form_panel)
        self.entry_footer.pack(fill="x", pady=(4, 24))

        # Action Buttons
        btn_bar = tk.Frame(form_panel, bg=COLOR_SURFACE)
        btn_bar.pack(fill="x")

        btn_save = ttk.Button(btn_bar, text="Save Settings", style="Primary.TButton", command=self._save_settings)
        btn_save.pack(side="left", padx=(0, 10))

        btn_reset = ttk.Button(btn_bar, text="Reset to Defaults", style="Secondary.TButton", command=self._reset_defaults)
        btn_reset.pack(side="left")

        self.lbl_status = tk.Label(btn_bar, text="", font=FONT_BODY, fg=COLOR_SUCCESS, bg=COLOR_SURFACE)
        self.lbl_status.pack(side="right")

    def _save_settings(self):
        store_name = self.entry_store.get().strip()
        currency = self.entry_currency.get().strip()
        tax_str = self.entry_tax.get().strip()
        footer = self.entry_footer.get().strip()

        if not store_name:
            messagebox.showerror("Error", "Store name cannot be empty.")
            return

        if not currency:
            messagebox.showerror("Error", "Currency symbol cannot be empty.")
            return

        try:
            tax_val = float(tax_str)
            if tax_val < 0:
                raise ValueError()
        except (ValueError, TypeError):
            messagebox.showerror("Error", "Tax rate must be a valid non-negative number.")
            return

        set_setting("store_name", store_name)
        set_setting("currency_symbol", currency)
        set_setting("tax_rate_percent", f"{tax_val:.1f}")
        set_setting("receipt_footer", footer or "Thank you for your business!")

        self.lbl_status.config(text="✓ Settings saved successfully!")
        self.after(3000, lambda: self.lbl_status.config(text=""))

        if self.on_settings_changed:
            self.on_settings_changed()

    def _reset_defaults(self):
        if messagebox.askyesno("Reset Settings", "Reset all settings to default values?"):
            set_setting("store_name", "Campus Store")
            set_setting("currency_symbol", "₹")
            set_setting("tax_rate_percent", "0.0")
            set_setting("receipt_footer", "Thank you for your business!")
            self.refresh()
            if self.on_settings_changed:
                self.on_settings_changed()

    def refresh(self):
        """Loads persistent settings from SQLite."""
        self.entry_store.delete(0, tk.END)
        self.entry_store.insert(0, get_setting("store_name", "Campus Store"))

        self.entry_currency.delete(0, tk.END)
        self.entry_currency.insert(0, get_setting("currency_symbol", "₹"))

        self.entry_tax.delete(0, tk.END)
        self.entry_tax.insert(0, get_setting("tax_rate_percent", "0.0"))

        self.entry_footer.delete(0, tk.END)
        self.entry_footer.insert(0, get_setting("receipt_footer", "Thank you for your business!"))
