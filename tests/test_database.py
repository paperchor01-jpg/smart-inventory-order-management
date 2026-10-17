"""Database verification test suite.

Tests isolated in-memory SQLite instances to verify:
- Schema initialization and default settings
- Foreign key enforcement
- CHECK constraints (negative price/stock prevention)
- Unique constraints (duplicate SKU prevention)
- Idempotent initialization (never overwrites existing data)
"""

import sqlite3
import unittest
import database


class TestDatabaseFoundation(unittest.TestCase):
    def setUp(self):
        # Use an isolated in-memory database for each test
        self.db_path = ":memory:"
        # Also need a persistent connection for in-memory across calls if needed,
        # but for get_connection(":memory:") each call creates a new DB unless using a URI or shared connection.
        # So we test with an in-memory connection or a temporary file path.
        # Using a dedicated temp file connection allows testing standard db_path behaviors.
        import tempfile
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        database.init_db(self.db_path)

    def tearDown(self):
        import os
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_schema_and_tables_exist(self):
        """Verifies that all required tables are properly created."""
        conn = database.get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        conn.close()

        expected = {"products", "orders", "order_items", "stock_movements", "settings"}
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")

    def test_default_settings(self):
        """Verifies default settings: currency symbol is ₹, tax is 0.0%, store name is set."""
        currency = database.get_setting("currency_symbol", db_path=self.db_path)
        tax_rate = database.get_setting("tax_rate_percent", db_path=self.db_path)
        store_name = database.get_setting("store_name", db_path=self.db_path)

        self.assertEqual(currency, "₹")
        self.assertEqual(tax_rate, "0.0")
        self.assertEqual(store_name, "Campus Store")

    def test_settings_update(self):
        """Verifies updating and retrieving configuration settings."""
        database.set_setting("store_name", "College Canteen", db_path=self.db_path)
        updated = database.get_setting("store_name", db_path=self.db_path)
        self.assertEqual(updated, "College Canteen")

        database.set_setting("tax_rate_percent", "5.0", db_path=self.db_path)
        updated_tax = database.get_setting("tax_rate_percent", db_path=self.db_path)
        self.assertEqual(updated_tax, "5.0")

    def test_foreign_keys_enforced(self):
        """Verifies that foreign key constraints are enforced."""
        conn = database.get_connection(self.db_path)
        cursor = conn.cursor()

        # Attempting to insert an order_item referencing a non-existent order_id (9999) must fail
        with self.assertRaises(sqlite3.IntegrityError):
            with conn:
                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, product_sku, product_name, unit_price, quantity, line_total)
                    VALUES (9999, NULL, 'SKU-001', 'Test Item', 10.0, 1, 10.0);
                """)
        conn.close()

    def test_product_price_and_stock_constraints(self):
        """Verifies CHECK constraints prevent negative prices and negative stock."""
        conn = database.get_connection(self.db_path)
        cursor = conn.cursor()

        now = database.get_current_timestamp()

        # Negative price must be rejected
        with self.assertRaises(sqlite3.IntegrityError):
            with conn:
                cursor.execute("""
                    INSERT INTO products (sku, name, price, stock, created_at, updated_at)
                    VALUES ('SKU-NEG-P', 'Invalid Price Item', -5.0, 10, ?, ?);
                """, (now, now))

        # Negative stock must be rejected
        with self.assertRaises(sqlite3.IntegrityError):
            with conn:
                cursor.execute("""
                    INSERT INTO products (sku, name, price, stock, created_at, updated_at)
                    VALUES ('SKU-NEG-S', 'Invalid Stock Item', 15.0, -2, ?, ?);
                """, (now, now))

        conn.close()

    def test_duplicate_sku_rejected(self):
        """Verifies UNIQUE constraint on product SKU prevents duplicates."""
        conn = database.get_connection(self.db_path)
        cursor = conn.cursor()
        now = database.get_current_timestamp()

        with conn:
            cursor.execute("""
                INSERT INTO products (sku, name, price, stock, created_at, updated_at)
                VALUES ('SKU-DUP', 'Item 1', 20.0, 5, ?, ?);
            """, (now, now))

        with self.assertRaises(sqlite3.IntegrityError):
            with conn:
                cursor.execute("""
                    INSERT INTO products (sku, name, price, stock, created_at, updated_at)
                    VALUES ('SKU-DUP', 'Item 2', 25.0, 10, ?, ?);
                """, (now, now))

        conn.close()

    def test_stock_movement_prevents_negative_new_stock(self):
        """Verifies stock movement check constraint prevents negative new_stock."""
        conn = database.get_connection(self.db_path)
        cursor = conn.cursor()
        now = database.get_current_timestamp()

        # Insert a valid product first
        with conn:
            cursor.execute("""
                INSERT INTO products (sku, name, price, stock, created_at, updated_at)
                VALUES ('SKU-STK', 'Stock Item', 10.0, 5, ?, ?);
            """, (now, now))
            prod_id = cursor.lastrowid

        # Attempt to insert a stock movement with new_stock < 0
        with self.assertRaises(sqlite3.IntegrityError):
            with conn:
                cursor.execute("""
                    INSERT INTO stock_movements (product_id, change_quantity, previous_stock, new_stock, reason, created_at)
                    VALUES (?, -10, 5, -5, 'DAMAGE', ?);
                """, (prod_id, now))

        conn.close()

    def test_init_db_is_idempotent(self):
        """Verifies that calling init_db repeatedly does NOT erase or reset existing data."""
        now = database.get_current_timestamp()
        conn = database.get_connection(self.db_path)
        with conn:
            conn.execute("""
                INSERT INTO products (sku, name, price, stock, created_at, updated_at)
                VALUES ('SKU-KEEP', 'Persistent Item', 50.0, 10, ?, ?);
            """, (now, now))
        conn.close()

        # Re-run init_db on the same database file
        database.init_db(self.db_path)

        # Confirm data is still intact
        conn = database.get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products WHERE sku = 'SKU-KEEP';")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Persistent Item")
        conn.close()

    def test_additive_migration_preserves_legacy_records(self):
        import tempfile
        import glob
        import os
        legacy = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        legacy_path = legacy.name
        legacy.close()
        try:
            conn = sqlite3.connect(legacy_path)
            conn.executescript("""
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'General', price REAL NOT NULL,
                    stock INTEGER NOT NULL DEFAULT 0, min_threshold INTEGER NOT NULL DEFAULT 5,
                    description TEXT, is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY, order_number TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
                    subtotal REAL NOT NULL, discount_amount REAL NOT NULL DEFAULT 0,
                    tax_rate REAL NOT NULL DEFAULT 0, tax_amount REAL NOT NULL DEFAULT 0,
                    total_amount REAL NOT NULL, notes TEXT
                );
                CREATE TABLE order_items (
                    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, product_id INTEGER,
                    product_sku TEXT NOT NULL, product_name TEXT NOT NULL, unit_price REAL NOT NULL,
                    quantity INTEGER NOT NULL, line_total REAL NOT NULL
                );
                INSERT INTO products VALUES (1,'OLD-1','Legacy item','General',10,4,2,NULL,1,'2025-01-01','2025-01-01');
                INSERT INTO orders VALUES (1,'OLD-ORDER','2025-01-01 10:00:00',10,0,0,0,10,NULL);
                INSERT INTO order_items VALUES (1,1,1,'OLD-1','Legacy item',10,1,10);
            """)
            conn.close()

            database.init_db(legacy_path)
            backup_paths = glob.glob(os.path.splitext(legacy_path)[0] + "_pre_migration_*.db")
            self.assertEqual(len(backup_paths), 1)
            backup_conn = sqlite3.connect(backup_paths[0])
            self.assertEqual(backup_conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(backup_conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)
            backup_conn.close()
            conn = database.get_connection(legacy_path)
            product = conn.execute("SELECT cost_price FROM products WHERE id=1").fetchone()
            order = conn.execute("SELECT status, cancelled_at FROM orders WHERE id=1").fetchone()
            item = conn.execute("SELECT unit_cost FROM order_items WHERE id=1").fetchone()
            self.assertIsNone(product["cost_price"])
            self.assertEqual(order["status"], "COMPLETED")
            self.assertIsNone(order["cancelled_at"])
            self.assertIsNone(item["unit_cost"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)
            conn.close()
        finally:
            if os.path.exists(legacy_path):
                os.remove(legacy_path)
            for backup_path in glob.glob(os.path.splitext(legacy_path)[0] + "_pre_migration_*.db"):
                os.remove(backup_path)

if __name__ == "__main__":
    unittest.main()
