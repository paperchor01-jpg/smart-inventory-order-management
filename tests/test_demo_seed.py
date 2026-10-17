"""Safety and behavior tests for the explicit demo product seeder."""
import os
import tempfile
import unittest

import database
from services.demo_data import DEMO_PRODUCTS
from services.inventory_service import seed_demo_products


class TestDemoProductSeed(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        database.init_db(self.db_path)

    def tearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_empty_database_gets_marked_products_and_opening_movements(self):
        result = seed_demo_products(self.db_path)
        self.assertTrue(result["seeded"])
        self.assertEqual(result["inserted_count"], 10)
        conn = database.get_connection(self.db_path)
        try:
            products = conn.execute("SELECT * FROM products ORDER BY sku").fetchall()
            movements = conn.execute("SELECT * FROM stock_movements").fetchall()
            self.assertEqual(len(products), len(DEMO_PRODUCTS))
            self.assertEqual(len({row["sku"] for row in products}), 10)
            self.assertTrue(all(row["sku"].startswith("DEMO-") for row in products))
            self.assertTrue(all("[DEMO]" in row["name"] for row in products))
            self.assertTrue(all(row["cost_price"] is not None for row in products))
            self.assertEqual(len({row["category"] for row in products}), 6)
            expected_movements = sum(item["stock"] > 0 for item in DEMO_PRODUCTS)
            self.assertEqual(len(movements), expected_movements)
            self.assertTrue(all(row["reason"] == "INITIAL_STOCK" for row in movements))
        finally:
            conn.close()

    def test_second_run_is_noop(self):
        first = seed_demo_products(self.db_path)
        conn = database.get_connection(self.db_path)
        try:
            before = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("products", "orders", "order_items", "stock_movements", "settings")
            }
        finally:
            conn.close()
        second = seed_demo_products(self.db_path)
        self.assertTrue(first["seeded"])
        self.assertFalse(second["seeded"])
        self.assertEqual(second["reason"], "catalog_not_empty")
        conn = database.get_connection(self.db_path)
        try:
            after = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in before
            }
            self.assertEqual(after, before)
        finally:
            conn.close()

    def test_existing_product_and_related_records_are_preserved(self):
        product = {
            "sku": "REAL-001", "name": "Existing Product", "category": "General",
            "price": 25.0, "cost_price": 10.0, "stock": 3,
            "min_threshold": 1, "description": "Do not alter",
            "is_active": 1, "created_at": "2026-01-01", "updated_at": "2026-01-01",
        }
        conn = database.get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT INTO products
                (sku,name,category,price,cost_price,stock,min_threshold,description,is_active,created_at,updated_at)
                VALUES (:sku,:name,:category,:price,:cost_price,:stock,:min_threshold,:description,:is_active,:created_at,:updated_at)""",
                product,
            )
            conn.execute(
                "INSERT INTO orders (order_number,created_at,subtotal,discount_amount,tax_rate,tax_amount,total_amount) VALUES ('KEEP-ORDER','2026-01-01',25,0,0,0,25)"
            )
            conn.execute(
                "INSERT INTO order_items (order_id,product_id,product_sku,product_name,unit_price,unit_cost,quantity,line_total) VALUES (1,1,'REAL-001','Existing Product',25,10,1,25)"
            )
            conn.execute("UPDATE settings SET value='Keep this setting' WHERE key='store_name'")
            conn.commit()
            before = {
                table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in ("products", "orders", "order_items", "stock_movements", "settings")
            }
        finally:
            conn.close()

        result = seed_demo_products(self.db_path)
        self.assertFalse(result["seeded"])
        self.assertEqual(result["existing_product_count"], 1)
        conn = database.get_connection(self.db_path)
        try:
            after = {
                table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in before
            }
            self.assertEqual(after, before)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

