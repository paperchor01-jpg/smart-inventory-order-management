"""Unit test suite for Checkout & Order Processing Service.

Tests run against isolated temporary SQLite databases to verify:
- Decimal precision for monetary calculations
- Atomic transaction checkout and inventory deduction
- Stock movement audit records for sales
- Complete rollback on insufficient stock or failure
- Historical product price & name snapshots in order items
- Receipt file generation and regeneration
"""

import os
import tempfile
import unittest
from decimal import Decimal

import database
from services import inventory_service, checkout_service


class TestCheckoutService(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        database.init_db(self.db_path)

        # Temp folder for receipts
        self.receipts_temp_dir = tempfile.mkdtemp(prefix="test_receipts_")
        self.original_receipts_dir = checkout_service.RECEIPTS_DIR
        checkout_service.RECEIPTS_DIR = self.receipts_temp_dir

    def tearDown(self):
        checkout_service.RECEIPTS_DIR = self.original_receipts_dir
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass
        import shutil
        if os.path.exists(self.receipts_temp_dir):
            try:
                shutil.rmtree(self.receipts_temp_dir)
            except OSError:
                pass

    def test_calculate_totals_basic(self):
        """Verifies calculation of basic subtotal and total without discount or tax."""
        items = [
            {"unit_price": 50.00, "quantity": 2},
            {"unit_price": 25.50, "quantity": 1},
        ]
        res = checkout_service.calculate_totals(items, discount_amount=0.0, tax_rate_percent=0.0)
        self.assertEqual(res["subtotal"], 125.50)
        self.assertEqual(res["discount_amount"], 0.0)
        self.assertEqual(res["tax_amount"], 0.0)
        self.assertEqual(res["total_amount"], 125.50)

    def test_calculate_totals_with_discount_and_tax(self):
        """Verifies Decimal precision discount and percentage tax calculation."""
        items = [
            {"unit_price": 100.00, "quantity": 2},  # 200.00
        ]
        # Subtotal: 200.00, Discount: 20.00 -> Discounted: 180.00. Tax: 5.0% -> 9.00 -> Total: 189.00
        res = checkout_service.calculate_totals(items, discount_amount=20.0, tax_rate_percent=5.0)
        self.assertEqual(res["subtotal"], 200.00)
        self.assertEqual(res["discount_amount"], 20.00)
        self.assertEqual(res["tax_rate"], 5.0)
        self.assertEqual(res["tax_amount"], 9.00)
        self.assertEqual(res["total_amount"], 189.00)

    def test_calculate_totals_invalid_discount_rejected(self):
        """Verifies discount exceeding subtotal or negative discount is rejected."""
        items = [{"unit_price": 50.0, "quantity": 1}]
        # Discount > subtotal
        with self.assertRaises(checkout_service.ValidationError):
            checkout_service.calculate_totals(items, discount_amount=60.0)

        # Negative discount
        with self.assertRaises(checkout_service.ValidationError):
            checkout_service.calculate_totals(items, discount_amount=-5.0)

        with self.assertRaises(checkout_service.ValidationError):
            checkout_service.calculate_totals([{"unit_price": 10, "quantity": 1.5}])

    def test_process_checkout_successful(self):
        """Verifies complete checkout flow: order saved, stock deducted, movement recorded, receipt created."""
        p1 = inventory_service.create_product(
            sku="SKU-CH-1", name="Notebook", price=50.0, stock=10, db_path=self.db_path
        )
        p2 = inventory_service.create_product(
            sku="SKU-CH-2", name="Gel Pen", price=15.0, stock=20, db_path=self.db_path
        )

        cart = [
            {"product_id": p1["id"], "quantity": 2},
            {"product_id": p2["id"], "quantity": 3},
        ]

        order = checkout_service.process_checkout(
            cart_items=cart,
            discount_amount=5.0,
            tax_rate_percent=10.0,
            notes="Student discount applied",
            db_path=self.db_path,
        )

        self.assertIsNotNone(order)
        self.assertTrue(order["order_number"].startswith("ORD-"))
        # Subtotal: (50*2) + (15*3) = 145.0. Discount: 5.0 -> 140.0. Tax 10% -> 14.0. Total -> 154.0
        self.assertEqual(order["subtotal"], 145.0)
        self.assertEqual(order["discount_amount"], 5.0)
        self.assertEqual(order["tax_amount"], 14.0)
        self.assertEqual(order["total_amount"], 154.0)

        # Verify stock deduction
        p1_after = inventory_service.get_product_by_id(p1["id"], db_path=self.db_path)
        p2_after = inventory_service.get_product_by_id(p2["id"], db_path=self.db_path)
        self.assertEqual(p1_after["stock"], 8)
        self.assertEqual(p2_after["stock"], 17)

        # Verify stock movements
        p1_movements = inventory_service.get_stock_movements(p1["id"], db_path=self.db_path)
        # Note: p1 had INITIAL_STOCK(10) then SALE(-2)
        sale_m = [m for m in p1_movements if m["reason"] == "SALE"][0]
        self.assertEqual(sale_m["change_quantity"], -2)
        self.assertEqual(sale_m["previous_stock"], 10)
        self.assertEqual(sale_m["new_stock"], 8)
        self.assertEqual(sale_m["reference_id"], order["order_number"])

        # Verify receipt was written to file
        self.assertTrue(os.path.exists(order["receipt_path"]))
        with open(order["receipt_path"], "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Notebook", content)
        self.assertIn("Gel Pen", content)
        self.assertIn(order["order_number"], content)
        self.assertIn("TOTAL PAYABLE:", content)

    def test_insufficient_stock_rollback(self):
        """Verifies that checkout failure due to insufficient stock rolls back EVERYTHING."""
        p = inventory_service.create_product(
            sku="SKU-LIMITED", name="Limited Book", price=200.0, stock=2, db_path=self.db_path
        )

        cart = [{"product_id": p["id"], "quantity": 5}]  # only 2 available

        with self.assertRaises(checkout_service.InsufficientStockError):
            checkout_service.process_checkout(cart_items=cart, db_path=self.db_path)

        # Verify stock is still 2
        p_check = inventory_service.get_product_by_id(p["id"], db_path=self.db_path)
        self.assertEqual(p_check["stock"], 2)

        # Verify orders table has 0 orders
        conn = database.get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM orders;")
        count = cur.fetchone()["c"]
        conn.close()
        self.assertEqual(count, 0)

    def test_deactivated_product_checkout_rejected(self):
        """Verifies that deactivated products cannot be purchased."""
        p = inventory_service.create_product(sku="SKU-DISC", name="Old Model", price=50.0, stock=10, db_path=self.db_path)
        inventory_service.deactivate_product(p["id"], db_path=self.db_path)

        cart = [{"product_id": p["id"], "quantity": 1}]
        with self.assertRaises(checkout_service.ValidationError):
            checkout_service.process_checkout(cart_items=cart, db_path=self.db_path)

    def test_historical_price_snapshot(self):
        """Verifies order items preserve original price even if product price changes later."""
        p = inventory_service.create_product(sku="SKU-HIST", name="Price Change Item", price=30.0, stock=10, db_path=self.db_path)

        # Buy at 30.0
        order = checkout_service.process_checkout([{"product_id": p["id"], "quantity": 1}], db_path=self.db_path)

        # Change product price in catalog to 50.0
        inventory_service.update_product(p["id"], price=50.0, db_path=self.db_path)

        # Re-fetch order
        saved_order = checkout_service.get_order_by_number(order["order_number"], db_path=self.db_path)
        item_snapshot = saved_order["items"][0]
        self.assertEqual(item_snapshot["unit_price"], 30.0)
        self.assertEqual(item_snapshot["line_total"], 30.0)

    def test_receipt_regeneration_when_file_deleted(self):
        """Verifies receipt can be regenerated from database if the file is deleted."""
        p = inventory_service.create_product(sku="SKU-REGEN", name="Regen Item", price=40.0, stock=5, db_path=self.db_path)
        order = checkout_service.process_checkout([{"product_id": p["id"], "quantity": 1}], db_path=self.db_path)

        # Delete the receipt file
        if os.path.exists(order["receipt_path"]):
            os.remove(order["receipt_path"])

        # Fetch receipt text -> should regenerate from DB
        text = checkout_service.get_receipt_text(order["order_number"], db_path=self.db_path)
        self.assertIn("Regen Item", text)
        self.assertIn(order["order_number"], text)
        self.assertIn("40.00", text)

    def test_duplicate_cart_lines_merge_and_cost_is_snapshotted(self):
        p = inventory_service.create_product(
            sku="SKU-COST", name="Costed Item", price=10, cost_price=4,
            stock=10, db_path=self.db_path,
        )
        order = checkout_service.process_checkout(
            [{"product_id": p["id"], "quantity": 1}, {"product_id": p["id"], "quantity": 2}],
            db_path=self.db_path,
        )
        saved = checkout_service.get_order_by_number(order["order_number"], db_path=self.db_path)
        self.assertEqual(len(saved["items"]), 1)
        self.assertEqual(saved["items"][0]["quantity"], 3)
        self.assertEqual(saved["items"][0]["unit_cost"], 4)
        self.assertEqual(inventory_service.get_product_by_id(p["id"], db_path=self.db_path)["stock"], 7)

    def test_cancel_restores_stock_once(self):
        p = inventory_service.create_product(
            sku="SKU-CANCEL", name="Cancelable Item", price=10, cost_price=3,
            stock=5, db_path=self.db_path,
        )
        order = checkout_service.process_checkout([{"product_id": p["id"], "quantity": 2}], db_path=self.db_path)
        self.assertEqual(inventory_service.get_product_by_id(p["id"], db_path=self.db_path)["stock"], 3)

        cancelled = checkout_service.cancel_order(order["order_number"], db_path=self.db_path)
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(inventory_service.get_product_by_id(p["id"], db_path=self.db_path)["stock"], 5)
        movements = inventory_service.get_stock_movements(product_id=p["id"], db_path=self.db_path)
        self.assertEqual(sum(m["reason"] == "ORDER_CANCEL" for m in movements), 1)
        with self.assertRaises(checkout_service.ValidationError):
            checkout_service.cancel_order(order["order_number"], db_path=self.db_path)
        self.assertEqual(inventory_service.get_product_by_id(p["id"], db_path=self.db_path)["stock"], 5)


if __name__ == "__main__":
    unittest.main()
