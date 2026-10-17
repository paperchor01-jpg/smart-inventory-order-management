"""Unit test suite for Report & Analytics Service.

Tests run against isolated temporary SQLite databases to verify:
- Live dashboard metrics calculations
- Sales reporting and date filtering
- Best-selling products aggregation
- Safe CSV export generation for sales, products, and stock movements
"""

import csv
import os
import tempfile
import unittest

import database
from services import inventory_service, checkout_service, report_service


class TestReportService(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        database.init_db(self.db_path)

        # Temporary export directory
        self.exports_temp_dir = tempfile.mkdtemp(prefix="test_exports_")
        self.original_exports_dir = report_service.EXPORTS_DIR
        report_service.EXPORTS_DIR = self.exports_temp_dir

    def tearDown(self):
        report_service.EXPORTS_DIR = self.original_exports_dir
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass
        import shutil
        if os.path.exists(self.exports_temp_dir):
            try:
                shutil.rmtree(self.exports_temp_dir)
            except OSError:
                pass

    def test_dashboard_metrics_empty_database(self):
        """Verifies dashboard metrics on an initial empty database return zeros without errors."""
        metrics = report_service.get_dashboard_metrics(db_path=self.db_path)
        self.assertEqual(metrics["total_products"], 0)
        self.assertEqual(metrics["total_units"], 0)
        self.assertEqual(metrics["total_inventory_value"], 0.0)
        self.assertEqual(metrics["cost_inventory_value"], 0.0)
        self.assertEqual(metrics["low_stock_count"], 0)
        self.assertEqual(metrics["out_of_stock_count"], 0)
        self.assertEqual(metrics["today_orders_count"], 0)
        self.assertEqual(metrics["today_sales_revenue"], 0.0)
        self.assertEqual(len(metrics["recent_orders"]), 0)
        self.assertEqual(len(metrics["urgent_restock"]), 0)
        self.assertEqual(metrics["currency_symbol"], "₹")

    def test_dashboard_metrics_with_active_data(self):
        """Verifies dashboard calculations with real products, low stock, and orders."""
        p1 = inventory_service.create_product(
            sku="SKU-R1", name="Product 1", price=100.0, stock=10, min_threshold=5, db_path=self.db_path
        )
        p2 = inventory_service.create_product(
            sku="SKU-R2", name="Product 2", price=50.0, stock=2, min_threshold=5, db_path=self.db_path
        )

        # Total units = 12. Total value = (10*100) + (2*50) = 1100.0. Low stock = 1 (p2).
        metrics_pre = report_service.get_dashboard_metrics(db_path=self.db_path)
        self.assertEqual(metrics_pre["total_products"], 2)
        self.assertEqual(metrics_pre["total_units"], 12)
        self.assertEqual(metrics_pre["total_inventory_value"], 1100.0)
        self.assertEqual(metrics_pre["low_stock_count"], 1)
        self.assertEqual(metrics_pre["out_of_stock_count"], 0)

        # Make a sale: 2 units of p1 (2 * 100 = 200.0)
        checkout_service.process_checkout([{"product_id": p1["id"], "quantity": 2}], db_path=self.db_path)

        metrics_post = report_service.get_dashboard_metrics(db_path=self.db_path)
        self.assertEqual(metrics_post["today_orders_count"], 1)
        self.assertEqual(metrics_post["today_sales_revenue"], 200.0)
        self.assertEqual(metrics_post["total_units"], 10)  # 12 - 2 = 10
        self.assertEqual(metrics_post["total_inventory_value"], 900.0)  # (8*100) + (2*50) = 900.0
        self.assertEqual(len(metrics_post["recent_orders"]), 1)

    def test_sales_report_and_best_selling(self):
        """Verifies date-filtered sales report and best-selling items ranking."""
        p1 = inventory_service.create_product(sku="SKU-B1", name="Best Seller", price=10.0, stock=50, db_path=self.db_path)
        p2 = inventory_service.create_product(sku="SKU-B2", name="Second Best", price=20.0, stock=30, db_path=self.db_path)

        # Order 1: 5 of p1, 1 of p2
        checkout_service.process_checkout([
            {"product_id": p1["id"], "quantity": 5},
            {"product_id": p2["id"], "quantity": 1},
        ], db_path=self.db_path)

        # Order 2: 3 of p1
        checkout_service.process_checkout([
            {"product_id": p1["id"], "quantity": 3},
        ], db_path=self.db_path)

        # Best sellers
        best_sellers = report_service.get_best_selling_products(db_path=self.db_path)
        self.assertEqual(len(best_sellers), 2)
        # p1 sold 5+3 = 8
        self.assertEqual(best_sellers[0]["product_sku"], "SKU-B1")
        self.assertEqual(best_sellers[0]["total_quantity_sold"], 8)
        self.assertEqual(best_sellers[0]["total_revenue_generated"], 80.0)

        # Sales report
        sales_rep = report_service.get_sales_report(db_path=self.db_path)
        self.assertEqual(sales_rep["total_orders"], 2)
        self.assertEqual(sales_rep["total_revenue"], 100.0)  # (5*10 + 1*20) + (3*10) = 70 + 30 = 100.0
        self.assertEqual(sales_rep["avg_order_value"], 50.0)

    def test_csv_exports(self):
        """Verifies CSV generation for sales, products catalog, and stock movements."""
        p = inventory_service.create_product(sku="SKU-CSV", name="CSV Item", price=25.0, stock=10, db_path=self.db_path)
        inventory_service.create_product(sku="SKU-FORMULA", name="=1+1", price=1, db_path=self.db_path)
        checkout_service.process_checkout([{"product_id": p["id"], "quantity": 2}], db_path=self.db_path)

        # 1. Export Sales
        sales_path = report_service.export_sales_to_csv(db_path=self.db_path)
        self.assertTrue(os.path.exists(sales_path))
        with open(sales_path, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertGreaterEqual(len(reader), 2)  # Header + 1 order
            self.assertIn("Order Number", reader[0])

        # 2. Export Products
        prod_path = report_service.export_products_to_csv(db_path=self.db_path)
        self.assertTrue(os.path.exists(prod_path))
        with open(prod_path, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertGreaterEqual(len(reader), 2)  # Header + 1 product
            self.assertIn("SKU", reader[0])
            self.assertIn("CSV Item", [row[2] for row in reader[1:]])
            formula_row = next(row for row in reader[1:] if row[1] == "SKU-FORMULA")
            self.assertEqual(formula_row[2], "'=1+1")

        # 3. Export Stock Movements
        mov_path = report_service.export_stock_movements_to_csv(db_path=self.db_path)
        self.assertTrue(os.path.exists(mov_path))
        with open(mov_path, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertGreaterEqual(len(reader), 3)  # Header + INITIAL_STOCK + SALE
            self.assertIn("Movement ID", reader[0])

    def test_cost_estimate_and_cancelled_orders_are_reported_correctly(self):
        p = inventory_service.create_product(
            sku="SKU-MARGIN", name="Margin Item", price=20, cost_price=8,
            stock=4, db_path=self.db_path,
        )
        order = checkout_service.process_checkout(
            [{"product_id": p["id"], "quantity": 2}], discount_amount=2, db_path=self.db_path
        )
        report = report_service.get_sales_report(db_path=self.db_path)
        self.assertEqual(report["estimated_cost"], 16.0)
        self.assertEqual(report["revenue_before_tax"], 38.0)
        self.assertEqual(report["estimated_gross_profit"], 22.0)

        checkout_service.cancel_order(order["order_number"], db_path=self.db_path)
        report_after = report_service.get_sales_report(db_path=self.db_path)
        self.assertEqual(report_after["total_orders"], 0)
        self.assertEqual(report_after["estimated_cost"], 0.0)
        self.assertEqual(report_service.get_best_selling_products(db_path=self.db_path), [])
        self.assertEqual(len(checkout_service.list_orders(db_path=self.db_path)), 1)

    def test_uncosted_historical_items_do_not_claim_profit(self):
        p = inventory_service.create_product(
            sku="SKU-NOCOST", name="Uncosted Item", price=20, stock=2, db_path=self.db_path
        )
        checkout_service.process_checkout([{"product_id": p["id"], "quantity": 1}], db_path=self.db_path)
        report = report_service.get_sales_report(db_path=self.db_path)
        self.assertIsNone(report["estimated_cost"])
        self.assertIsNone(report["estimated_gross_profit"])
        self.assertEqual(report["uncosted_lines"], 1)

    def test_inventory_cost_valuation_requires_cost_for_stocked_products(self):
        inventory_service.create_product(
            sku="SKU-STOCK-COST", name="Costed Stock", price=20, cost_price=7,
            stock=3, db_path=self.db_path,
        )
        metrics = report_service.get_dashboard_metrics(db_path=self.db_path)
        self.assertEqual(metrics["cost_inventory_value"], 21.0)
        self.assertEqual(metrics["uncosted_stock_products"], 0)

        inventory_service.create_product(
            sku="SKU-STOCK-UNKNOWN", name="Unknown Cost Stock", price=10,
            stock=2, db_path=self.db_path,
        )
        metrics = report_service.get_dashboard_metrics(db_path=self.db_path)
        self.assertIsNone(metrics["cost_inventory_value"])
        self.assertEqual(metrics["uncosted_stock_products"], 1)

    def test_invalid_report_date_range_rejected(self):
        with self.assertRaises(ValueError):
            report_service.get_sales_report(start_date="not-a-date")
        with self.assertRaises(ValueError):
            report_service.get_sales_report(start_date="2026-02-02", end_date="2026-02-01")


if __name__ == "__main__":
    unittest.main()
