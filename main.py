"""Smart Inventory & Order Management System.

Main Application Entry Point.
Implements a desktop interface with a persistent left sidebar,
restrained Neumorphic styling, and seamless navigation between:
- Dashboard (Module A)
- Product Management (Module B)
- Stock Management (Module C & F)
- Checkout & Orders (Module D & E)
- Reports & Analytics (Module G)
- Settings
"""

import sys
import tkinter as tk
from tkinter import ttk

import database
from ui.components import (
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_BORDER,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    FONT_SUBTITLE,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    setup_theme,
)
from ui.dashboard_view import DashboardView
from ui.products_view import ProductsView
from ui.stock_view import StockView
from ui.checkout_view import CheckoutView
from ui.reports_view import ReportsView
from ui.settings_view import SettingsView


class InventoryApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # Ensure database is initialized before starting UI
        database.init_db()

        self.title("Smart Inventory & Order Management System")
        self.geometry("1180x740")
        self.minsize(1020, 640)
        self.configure(bg=COLOR_BG)

        # Setup Neumorphic theme styles
        self.style = setup_theme(self)

        # Active navigation tracking
        self.current_screen = "dashboard"
        self.nav_buttons = {}

        self._build_shell()
        self._build_views()

        # Display initial screen
        self.show_screen("dashboard")

        # Some Windows launchers start GUI processes in a minimized state.
        # Restore the root after Tk has completed its initial layout.
        self.after_idle(self.deiconify)

    def _build_shell(self):
        # Master container
        self.main_container = tk.Frame(self, bg=COLOR_BG)
        self.main_container.pack(fill="both", expand=True)

        # ---------------- Left Sidebar ----------------
        self.sidebar = tk.Frame(
            self.main_container,
            bg=COLOR_SURFACE,
            width=230,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # App Brand Header
        brand_frame = tk.Frame(self.sidebar, bg=COLOR_SURFACE, padx=18, pady=20)
        brand_frame.pack(fill="x")

        lbl_logo = tk.Label(
            brand_frame,
            text="📦 SMART INVENTORY",
            font=(FONT_SUBTITLE[0], 12, "bold"),
            fg=COLOR_PRIMARY,
            bg=COLOR_SURFACE,
        )
        lbl_logo.pack(anchor="w")

        lbl_sub = tk.Label(
            brand_frame,
            text="Order & Stock System",
            font=FONT_SMALL,
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        lbl_sub.pack(anchor="w", pady=(2, 0))

        # Divider
        tk.Frame(self.sidebar, bg=COLOR_BORDER, height=1).pack(fill="x", padx=14, pady=(0, 15))

        # Navigation Menu Items
        self.nav_frame = tk.Frame(self.sidebar, bg=COLOR_SURFACE)
        self.nav_frame.pack(fill="x", padx=12)

        nav_items = [
            ("dashboard", "📊 Dashboard"),
            ("products", "🏷️ Products"),
            ("stock", "⚡ Stock Management"),
            ("checkout", "🛒 Checkout"),
            ("reports", "📈 Reports"),
            ("settings", "⚙️ Settings"),
        ]

        for key, label in nav_items:
            btn = tk.Button(
                self.nav_frame,
                text=f"  {label}",
                font=FONT_BODY_BOLD,
                fg=COLOR_TEXT_MAIN,
                bg=COLOR_SURFACE,
                activebackground=COLOR_BG,
                activeforeground=COLOR_PRIMARY,
                bd=0,
                relief="flat",
                anchor="w",
                padx=12,
                pady=10,
                cursor="hand2",
                command=lambda k=key: self.show_screen(k),
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        # Sidebar Footer
        footer_frame = tk.Frame(self.sidebar, bg=COLOR_SURFACE, padx=16, pady=16)
        footer_frame.pack(side="bottom", fill="x")

        tk.Label(
            footer_frame,
            text="● Local Offline Database",
            font=FONT_SMALL,
            fg="#16a34a",
            bg=COLOR_SURFACE,
        ).pack(anchor="w")

        tk.Label(
            footer_frame,
            text="v1.0.0 (Hackathon Build)",
            font=FONT_SMALL,
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        ).pack(anchor="w", pady=(2, 0))

        # ---------------- Right Content Area ----------------
        self.content_area = tk.Frame(self.main_container, bg=COLOR_BG)
        self.content_area.pack(side="right", fill="both", expand=True)

    def _build_views(self):
        """Initializes all view frames in the content area."""
        self.views = {
            "dashboard": DashboardView(self.content_area, navigate_callback=self.show_screen),
            "products": ProductsView(self.content_area),
            "stock": StockView(self.content_area),
            "checkout": CheckoutView(self.content_area),
            "reports": ReportsView(self.content_area),
            "settings": SettingsView(self.content_area, on_settings_changed=self._on_settings_updated),
        }

    def _on_settings_updated(self):
        """Called whenever settings are changed to update screens."""
        if "dashboard" in self.views:
            self.views["dashboard"].refresh()
        if "checkout" in self.views:
            self.views["checkout"].refresh()

    def show_screen(self, screen_key: str):
        """Switches the visible screen and highlights the active sidebar button."""
        if screen_key not in self.views:
            return

        # Hide all views
        for v in self.views.values():
            v.pack_forget()

        # Update sidebar active state styling
        for key, btn in self.nav_buttons.items():
            if key == screen_key:
                btn.config(bg=COLOR_BG, fg=COLOR_PRIMARY, relief="groove", bd=1)
            else:
                btn.config(bg=COLOR_SURFACE, fg=COLOR_TEXT_MAIN, relief="flat", bd=0)

        # Show selected view and trigger live data refresh
        view = self.views[screen_key]
        view.pack(fill="both", expand=True)
        if hasattr(view, "refresh"):
            view.refresh()

        self.current_screen = screen_key


def main():
    """Main launcher."""
    app = InventoryApp()
    app.mainloop()


if __name__ == "__main__":
    main()
