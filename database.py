"""Database Foundation for Smart Inventory & Order Management System.

Handles SQLite connection management, foreign key enforcement,
schema creation, and application configuration settings.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, Any

# Default path for persistent SQLite database in the application/data directory
DEFAULT_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "inventory.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Creates and returns an SQLite database connection.

    - Sets row_factory to sqlite3.Row for dict-like column access.
    - Explicitly turns ON foreign key constraint enforcement.
    - Automatically ensures parent directories exist if saving to a file.
    """
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH

    # If it's a real file path (not in-memory), make sure the parent folder exists
    if target_path != ":memory:":
        parent_dir = os.path.dirname(target_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _pending_migrations(conn: sqlite3.Connection) -> bool:
    required = {
        "products": {"cost_price"},
        "orders": {"status", "cancelled_at"},
        "order_items": {"unit_cost"},
    }
    tables = {
        row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table';"
        )
    }
    for table, required_columns in required.items():
        if table in tables:
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table});")}
            if required_columns - columns:
                return True
    return False


def _backup_before_migration(db_path: str) -> str:
    """Creates and verifies a unique SQLite backup before altering a file DB."""
    folder = os.path.dirname(os.path.abspath(db_path))
    base = os.path.splitext(os.path.basename(db_path))[0]
    while True:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = os.path.join(folder, f"{base}_pre_migration_{stamp}.db")
        try:
            descriptor = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descriptor)
            break
        except FileExistsError:
            continue
    source = sqlite3.connect(db_path)
    target = None
    try:
        target = sqlite3.connect(backup_path)
        source.backup(target)
        result = target.execute("PRAGMA integrity_check;").fetchone()[0]
        if result != "ok":
            raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")
    finally:
        source.close()
        if target is not None:
            target.close()
    return backup_path


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes all database tables, indexes, and default settings.

    Uses CREATE TABLE IF NOT EXISTS so existing data is never overwritten or reset.
    """
    conn = get_connection(db_path)
    try:
        target_path = db_path if db_path is not None else DEFAULT_DB_PATH
        if target_path != ":memory:" and _pending_migrations(conn):
            _backup_before_migration(target_path)
        with conn:
            # 1. Products Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'General',
                    price REAL NOT NULL CHECK(price >= 0),
                    cost_price REAL CHECK(cost_price IS NULL OR cost_price >= 0),
                    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
                    min_threshold INTEGER NOT NULL DEFAULT 5 CHECK(min_threshold >= 0),
                    description TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active);")

            # 2. Orders Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    subtotal REAL NOT NULL CHECK(subtotal >= 0),
                    discount_amount REAL NOT NULL DEFAULT 0.0 CHECK(discount_amount >= 0),
                    tax_rate REAL NOT NULL DEFAULT 0.0 CHECK(tax_rate >= 0),
                    tax_amount REAL NOT NULL DEFAULT 0.0 CHECK(tax_amount >= 0),
                    total_amount REAL NOT NULL CHECK(total_amount >= 0),
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'COMPLETED' CHECK(status IN ('COMPLETED', 'CANCELLED')),
                    cancelled_at TEXT
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_order_number ON orders(order_number);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);")

            # 3. Order Items Table (Historical Snapshot)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    product_id INTEGER,
                    product_sku TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    unit_price REAL NOT NULL CHECK(unit_price >= 0),
                    unit_cost REAL CHECK(unit_cost IS NULL OR unit_cost >= 0),
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    line_total REAL NOT NULL CHECK(line_total >= 0),
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);")

            # Additive migrations keep existing SQLite files and records intact.
            # Existing products/orders receive NULL cost and COMPLETED status defaults.
            migrations = {
                "products": [
                    ("cost_price", "REAL CHECK(cost_price IS NULL OR cost_price >= 0)"),
                ],
                "orders": [
                    ("status", "TEXT NOT NULL DEFAULT 'COMPLETED' CHECK(status IN ('COMPLETED', 'CANCELLED'))"),
                    ("cancelled_at", "TEXT"),
                ],
                "order_items": [
                    ("unit_cost", "REAL CHECK(unit_cost IS NULL OR unit_cost >= 0)"),
                ],
            }
            for table, columns in migrations.items():
                existing_columns = {
                    row["name"] for row in conn.execute(f"PRAGMA table_info({table});")
                }
                for column, definition in columns:
                    if column not in existing_columns:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")

            # 4. Stock Movements Table (Audit Trail)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    change_quantity INTEGER NOT NULL,
                    previous_stock INTEGER NOT NULL,
                    new_stock INTEGER NOT NULL CHECK(new_stock >= 0),
                    reason TEXT NOT NULL,
                    reference_id TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_product_id ON stock_movements(product_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_created_at ON stock_movements(created_at);")

            # 5. Application Settings Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            # Seed default settings if not already present
            default_settings = [
                ("store_name", "Campus Store"),
                ("tax_rate_percent", "0.0"),  # 0% initial demo default as requested
                ("currency_symbol", "₹"),     # ₹ (INR) default as requested
                ("receipt_footer", "Thank you for your business!"),
            ]

            for key, val in default_settings:
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);",
                    (key, val),
                )
    finally:
        conn.close()


def get_setting(key: str, default: Any = None, db_path: Optional[str] = None) -> Any:
    """Retrieves a configuration value by key from the settings table."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: Any, db_path: Optional[str] = None) -> None:
    """Sets or updates a configuration value in the settings table."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
                (key, str(value)),
            )
    finally:
        conn.close()


def get_current_timestamp() -> str:
    """Returns the current timestamp in 'YYYY-MM-DD HH:MM:SS' format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
