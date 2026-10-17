"""Neumorphic UI Component & Style System.

Provides consistent styling, colors, typography, soft raised/inset cards,
and enhanced widgets for Tkinter and ttk.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Any, Dict, List


# ---------------------------------------------------------------------------
# Neumorphic Color Palette & Design Tokens
# ---------------------------------------------------------------------------

COLOR_BG = "#e8edf2"             # Main soft grey-blue surface
COLOR_SURFACE = "#e8edf2"        # Flat elevated surface
COLOR_SURFACE_LIGHT = "#f5f8fc"  # Highlight edge
COLOR_SURFACE_DARK = "#cdd6e0"   # Shadow edge
COLOR_INSET = "#dfe5ec"          # Sunken/inset fields & search bars
COLOR_BORDER = "#cad3df"         # Subtle separator border

COLOR_PRIMARY = "#2563eb"        # Vibrant soft blue
COLOR_PRIMARY_HOVER = "#1d4ed8"
COLOR_PRIMARY_FG = "#ffffff"

COLOR_SUCCESS = "#16a34a"        # Soft forest green
COLOR_WARNING = "#d97706"        # Amber
COLOR_DANGER = "#dc2626"         # Crimson red
COLOR_DANGER_HOVER = "#b91c1c"

COLOR_TEXT_MAIN = "#1e293b"      # Deep slate for high contrast
COLOR_TEXT_MUTED = "#64748b"     # Slate grey for secondary info
COLOR_TEXT_LIGHT = "#94a3b8"

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 16, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 12, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_METRIC_VAL = (FONT_FAMILY, 22, "bold")
FONT_BUTTON = (FONT_FAMILY, 10, "bold")


def setup_theme(root: tk.Tk) -> ttk.Style:
    """Configures global ttk styling to match the neumorphic visual direction."""
    style = ttk.Style(root)
    style.theme_use("clam")

    # Global Frame background
    style.configure("TFrame", background=COLOR_BG)
    style.configure("Card.TFrame", background=COLOR_SURFACE, relief="solid", borderwidth=1)

    # Labels
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT_MAIN, font=FONT_BODY)
    style.configure("Title.TLabel", font=FONT_TITLE, foreground=COLOR_TEXT_MAIN, background=COLOR_BG)
    style.configure("Subtitle.TLabel", font=FONT_SUBTITLE, foreground=COLOR_TEXT_MUTED, background=COLOR_BG)
    style.configure("Muted.TLabel", font=FONT_SMALL, foreground=COLOR_TEXT_MUTED, background=COLOR_BG)
    style.configure("Bold.TLabel", font=FONT_BODY_BOLD, foreground=COLOR_TEXT_MAIN, background=COLOR_BG)

    # Metric Card specific labels
    style.configure("MetricVal.TLabel", font=FONT_METRIC_VAL, foreground=COLOR_TEXT_MAIN, background=COLOR_SURFACE)
    style.configure("MetricTitle.TLabel", font=FONT_SMALL, foreground=COLOR_TEXT_MUTED, background=COLOR_SURFACE)
    style.configure("MetricSub.TLabel", font=FONT_SMALL, foreground=COLOR_TEXT_MUTED, background=COLOR_SURFACE)

    # Buttons
    style.configure(
        "Primary.TButton",
        background=COLOR_PRIMARY,
        foreground=COLOR_PRIMARY_FG,
        font=FONT_BUTTON,
        borderwidth=0,
        padding=(14, 8),
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLOR_PRIMARY_HOVER), ("disabled", "#94a3b8")],
        foreground=[("disabled", "#cbd5e1")],
    )

    style.configure(
        "Secondary.TButton",
        background=COLOR_SURFACE,
        foreground=COLOR_TEXT_MAIN,
        font=FONT_BUTTON,
        borderwidth=1,
        relief="raised",
        padding=(12, 6),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", COLOR_INSET)],
    )

    style.configure(
        "Danger.TButton",
        background=COLOR_DANGER,
        foreground="#ffffff",
        font=FONT_BUTTON,
        borderwidth=0,
        padding=(12, 6),
    )
    style.map("Danger.TButton", background=[("active", COLOR_DANGER_HOVER)])

    # Entry & Combobox
    style.configure(
        "TEntry",
        fieldbackground="#ffffff",
        foreground=COLOR_TEXT_MAIN,
        padding=6,
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "TCombobox",
        fieldbackground="#ffffff",
        background=COLOR_SURFACE,
        foreground=COLOR_TEXT_MAIN,
        padding=4,
    )

    # Treeview (Tables)
    style.configure(
        "Treeview",
        background="#ffffff",
        foreground=COLOR_TEXT_MAIN,
        fieldbackground="#ffffff",
        font=FONT_BODY,
        rowheight=28,
        borderwidth=0,
    )
    style.map(
        "Treeview",
        background=[("selected", "#dbeafe")],
        foreground=[("selected", "#1e3a8a")],
    )
    style.configure(
        "Treeview.Heading",
        background=COLOR_SURFACE_DARK,
        foreground=COLOR_TEXT_MAIN,
        font=FONT_BODY_BOLD,
        padding=(6, 6),
        relief="flat",
    )
    style.map("Treeview.Heading", background=[("active", COLOR_BORDER)])

    return style


# ---------------------------------------------------------------------------
# Neumorphic Card Widget
# ---------------------------------------------------------------------------

class MetricCard(tk.Frame):
    """Raised card displaying a key metric with soft neumorphic borders."""

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        value: str,
        subtitle: str = "",
        accent_color: str = COLOR_PRIMARY,
        *args,
        **kwargs,
    ):
        super().__init__(
            parent,
            bg=COLOR_SURFACE,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=16,
            pady=14,
            *args,
            **kwargs,
        )
        self.accent_color = accent_color

        # Top Accent indicator line
        accent_bar = tk.Frame(self, bg=accent_color, height=3)
        accent_bar.pack(fill="x", side="top", pady=(0, 8))

        # Title
        self.title_label = tk.Label(
            self, text=title.upper(), font=FONT_SMALL, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE, anchor="w"
        )
        self.title_label.pack(fill="x")

        # Value
        self.value_label = tk.Label(
            self, text=value, font=FONT_METRIC_VAL, fg=COLOR_TEXT_MAIN, bg=COLOR_SURFACE, anchor="w"
        )
        self.value_label.pack(fill="x", pady=(2, 4))

        # Subtitle
        self.sub_label = tk.Label(
            self, text=subtitle, font=FONT_SMALL, fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE, anchor="w"
        )
        self.sub_label.pack(fill="x")

    def update_value(self, new_val: str, new_sub: Optional[str] = None):
        """Updates the card value dynamically."""
        self.value_label.config(text=new_val)
        if new_sub is not None:
            self.sub_label.config(text=new_sub)


# ---------------------------------------------------------------------------
# Soft Raised Surface Panel
# ---------------------------------------------------------------------------

class NeuPanel(tk.Frame):
    """A clean elevated container frame with soft border and uniform padding."""

    def __init__(self, parent: tk.Widget, *args, **kwargs):
        pad_x = kwargs.pop("padx", 14)
        pad_y = kwargs.pop("pady", 14)
        super().__init__(
            parent,
            bg=COLOR_SURFACE,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=pad_x,
            pady=pad_y,
            *args,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Table Helper with Scrollbars
# ---------------------------------------------------------------------------

def create_styled_table(
    parent: tk.Widget,
    columns: List[tuple],  # List of (column_id, header_text, width, anchor)
    selectmode: str = "browse",
) -> tuple[ttk.Treeview, ttk.Scrollbar, tk.Frame]:
    """Creates a configured Treeview with vertical scrollbar inside a container frame."""
    container = tk.Frame(parent, bg=COLOR_BG)

    col_ids = [c[0] for c in columns]
    tree = ttk.Treeview(container, columns=col_ids, show="headings", selectmode=selectmode)

    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)

    for cid, heading, width, anchor in columns:
        tree.heading(cid, text=heading)
        tree.column(cid, width=width, anchor=anchor)

    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    return tree, vsb, container
