"""Unit tests for Inventory & Stock Business Logic (Milestone 2).

Tests run against isolated temporary SQLite databases to verify:
- Product creation, validation, and duplicate SKU handling
- Product updates and editing constraints
- Product search and category filtering
- Safe deactivation and reactivation
- Transaction-safe incoming and outgoing stock adjustments
- Negative stock rejection and transaction rollback
- Low-stock alert detection (stock <= min_threshold for active products)
"""

import os
import tempfile
import unittest

import database
from services import inventory_service


class TestInventoryService(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary database file for each test
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        database.init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    # -----------------------------------------------------------------------
    # Product Creation Tests
    # -----------------------------------------------------------------------

    def test_create_product_success(self):
        """Verifies creating a product with valid fields."""
        prod = inventory_service.create_product(
            sku="SKU-NOTEBOOK",
            name="Spiral Notebook",
            price=45.50,
            stock=20,
            min_threshold=5,
            category="Stationery",
            description="200-page notebook",
            db_path=self.db_path,
        )

        self.assertIsNotNone(prod)
        self.assertEqual(prod["sku"], "SKU-NOTEBOOK")
        self.assertEqual(prod["name"], "Spiral Notebook")
        self.assertEqual(prod["price"], 45.50)
        self.assertEqual(prod["stock"], 20)
        self.assertEqual(prod["min_threshold"], 5)
        self.assertEqual(prod["category"], "Stationery")
        self.assertEqual(prod["is_active"], 1)

        # Initial stock > 0 should log an initial stock movement
        movements = inventory_service.get_stock_movements(product_id=prod["id"], db_path=self.db_path)
        self.assertEqual(len(movements), 1)
        self.assertEqual(movements[0]["reason"], "INITIAL_STOCK")
        self.assertEqual(movements[0]["change_quantity"], 20)
        self.assertEqual(movements[0]["new_stock"], 20)

    def test_create_product_zero_stock_no_initial_movement(self):
        """Verifies creating a product with 0 stock doesn't add an initial movement."""
        prod = inventory_service.create_product(
            sku="SKU-PEN",
            name="Blue Gel Pen",
            price=10.0,
            stock=0,
            db_path=self.db_path,
        )
        self.assertEqual(prod["stock"], 0)
        movements = inventory_service.get_stock_movements(product_id=prod["id"], db_path=self.db_path)
        self.assertEqual(len(movements), 0)

    def test_create_product_duplicate_sku_rejected(self):
        """Verifies DuplicateSKUError is raised when trying to use an existing SKU."""
        inventory_service.create_product(
            sku="SKU-UNIQUE",
            name="Original Item",
            price=15.0,
            stock=5,
            db_path=self.db_path,
        )

        with self.assertRaises(inventory_service.DuplicateSKUError):
            inventory_service.create_product(
                sku="SKU-UNIQUE",
                name="Duplicate Item",
                price=20.0,
                stock=1,
                db_path=self.db_path,
            )

    def test_create_product_invalid_values_rejected(self):
        """Verifies validation errors on invalid names, prices, or thresholds."""
        # Empty SKU
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="", name="Item", price=10.0, db_path=self.db_path)

        # Empty Name
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-1", name="   ", price=10.0, db_path=self.db_path)

        # Negative Price
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-2", name="Item", price=-5.0, db_path=self.db_path)

        # Non-numeric Price
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-3", name="Item", price="free", db_path=self.db_path)

        # Negative Stock
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-4", name="Item", price=10.0, stock=-1, db_path=self.db_path)

        # Negative Threshold
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-5", name="Item", price=10.0, min_threshold=-2, db_path=self.db_path)

        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-6", name="Item", price=10.0, stock=1.5, db_path=self.db_path)

        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-7", name="Item", price=10.0, cost_price=-1, db_path=self.db_path)

        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.create_product(sku="SKU-8", name="Item", price=float("inf"), db_path=self.db_path)

    # -----------------------------------------------------------------------
    # Product Update & Retrieval Tests
    # -----------------------------------------------------------------------

    def test_update_product_success(self):
        """Verifies updating product name, category, price, and threshold."""
        prod = inventory_service.create_product(
            sku="SKU-ORIG",
            name="Old Name",
            price=20.0,
            category="Snacks",
            min_threshold=5,
            db_path=self.db_path,
        )

        updated = inventory_service.update_product(
            product_id=prod["id"],
            name="New Name",
            price=25.0,
            category="Beverages",
            min_threshold=8,
            description="Updated description",
            db_path=self.db_path,
        )

        self.assertEqual(updated["name"], "New Name")
        self.assertEqual(updated["price"], 25.0)
        self.assertEqual(updated["category"], "Beverages")
        self.assertEqual(updated["min_threshold"], 8)
        self.assertEqual(updated["description"], "Updated description")

    def test_update_product_validation(self):
        """Verifies invalid values are rejected during update."""
        prod = inventory_service.create_product(
            sku="SKU-UP-VAL",
            name="Item",
            price=10.0,
            db_path=self.db_path,
        )

        # Cannot set empty name
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.update_product(prod["id"], name="  ", db_path=self.db_path)

        # Cannot set negative price
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.update_product(prod["id"], price=-1.0, db_path=self.db_path)

        # Cannot set negative threshold
        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.update_product(prod["id"], min_threshold=-5, db_path=self.db_path)

    def test_update_product_duplicate_sku_rejection(self):
        """Verifies updating SKU to one that already exists raises DuplicateSKUError."""
        inventory_service.create_product(sku="SKU-A", name="Item A", price=10.0, db_path=self.db_path)
        prod_b = inventory_service.create_product(sku="SKU-B", name="Item B", price=12.0, db_path=self.db_path)

        with self.assertRaises(inventory_service.DuplicateSKUError):
            inventory_service.update_product(prod_b["id"], sku="SKU-A", db_path=self.db_path)

    # -----------------------------------------------------------------------
    # Search, Category Filtering, and Deactivation Tests
    # -----------------------------------------------------------------------

    def test_search_and_category_filtering(self):
        """Verifies searching by query and filtering by category."""
        inventory_service.create_product(sku="SKU-TEA", name="Masala Tea", price=15.0, category="Hot Drinks", db_path=self.db_path)
        inventory_service.create_product(sku="SKU-COF", name="Filter Coffee", price=20.0, category="Hot Drinks", db_path=self.db_path)
        inventory_service.create_product(sku="SKU-SAN", name="Veg Sandwich", price=35.0, category="Snacks", db_path=self.db_path)

        # Search by keyword
        tea_results = inventory_service.search_products(query="Tea", db_path=self.db_path)
        self.assertEqual(len(tea_results), 1)
        self.assertEqual(tea_results[0]["sku"], "SKU-TEA")

        # Search by SKU
        cof_results = inventory_service.search_products(query="COF", db_path=self.db_path)
        self.assertEqual(len(cof_results), 1)
        self.assertEqual(cof_results[0]["name"], "Filter Coffee")

        # Filter by category
        hot_drinks = inventory_service.list_products(category="Hot Drinks", db_path=self.db_path)
        self.assertEqual(len(hot_drinks), 2)

        # Distinct categories
        categories = inventory_service.get_categories(db_path=self.db_path)
        self.assertIn("Hot Drinks", categories)
        self.assertIn("Snacks", categories)

    def test_safe_deactivation_and_reactivation(self):
        """Verifies deactivating a product hides it from active listings but preserves it in the DB."""
        prod = inventory_service.create_product(sku="SKU-DEACT", name="Temp Item", price=10.0, db_path=self.db_path)

        # Deactivate
        deactivated = inventory_service.deactivate_product(prod["id"], db_path=self.db_path)
        self.assertEqual(deactivated["is_active"], 0)

        # Should NOT appear in active_only list
        active_list = inventory_service.list_products(active_only=True, db_path=self.db_path)
        self.assertNotIn(prod["id"], [p["id"] for p in active_list])

        # Should appear in all products list
        all_list = inventory_service.list_products(active_only=False, db_path=self.db_path)
        self.assertIn(prod["id"], [p["id"] for p in all_list])

        # Reactivate
        reactivated = inventory_service.reactivate_product(prod["id"], db_path=self.db_path)
        self.assertEqual(reactivated["is_active"], 1)

    # -----------------------------------------------------------------------
    # Stock Adjustments & Transaction Rollback Tests
    # -----------------------------------------------------------------------

    def test_incoming_stock_adjustment_restock(self):
        """Verifies incoming stock adjustment increases quantity and records an audit movement."""
        prod = inventory_service.create_product(sku="SKU-RESTK", name="Milk Bottle", price=30.0, stock=5, db_path=self.db_path)

        movement = inventory_service.adjust_stock(
            product_id=prod["id"],
            change_quantity=15,
            reason="RESTOCK",
            notes="Morning shipment from supplier",
            db_path=self.db_path,
        )

        self.assertEqual(movement["previous_stock"], 5)
        self.assertEqual(movement["new_stock"], 20)
        self.assertEqual(movement["change_quantity"], 15)

        updated_prod = inventory_service.get_product_by_id(prod["id"], db_path=self.db_path)
        self.assertEqual(updated_prod["stock"], 20)

    def test_outgoing_stock_adjustment_damage(self):
        """Verifies outgoing stock adjustment decreases quantity and records reason."""
        prod = inventory_service.create_product(sku="SKU-DMG", name="Glass Bottle", price=50.0, stock=10, db_path=self.db_path)

        movement = inventory_service.adjust_stock(
            product_id=prod["id"],
            change_quantity=-3,
            reason="DAMAGE",
            notes="Broken during shelf arrangement",
            db_path=self.db_path,
        )

        self.assertEqual(movement["previous_stock"], 10)
        self.assertEqual(movement["new_stock"], 7)
        self.assertEqual(movement["change_quantity"], -3)

        updated_prod = inventory_service.get_product_by_id(prod["id"], db_path=self.db_path)
        self.assertEqual(updated_prod["stock"], 7)

    def test_reject_negative_stock_and_rollback(self):
        """Verifies that an adjustment resulting in negative stock is rejected and rolled back completely."""
        prod = inventory_service.create_product(sku="SKU-ROLLBACK", name="Limited Item", price=100.0, stock=4, db_path=self.db_path)

        # Count initial movements (from initial stock)
        initial_movements = inventory_service.get_stock_movements(product_id=prod["id"], db_path=self.db_path)

        # Attempt to subtract 5 when only 4 are in stock -> must raise InsufficientStockError
        with self.assertRaises(inventory_service.InsufficientStockError):
            inventory_service.adjust_stock(
                product_id=prod["id"],
                change_quantity=-5,
                reason="DAMAGE",
                db_path=self.db_path,
            )

        # Verify stock remains completely untouched (still 4)
        prod_after = inventory_service.get_product_by_id(prod["id"], db_path=self.db_path)
        self.assertEqual(prod_after["stock"], 4)

        # Verify NO new stock movement record was added (rolled back)
        movements_after = inventory_service.get_stock_movements(product_id=prod["id"], db_path=self.db_path)
        self.assertEqual(len(movements_after), len(initial_movements))

    def test_adjustment_missing_reason_rejected(self):
        """Verifies adjustment reason is mandatory."""
        prod = inventory_service.create_product(sku="SKU-NOREASON", name="Item", price=10.0, stock=5, db_path=self.db_path)

        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.adjust_stock(product_id=prod["id"], change_quantity=5, reason="", db_path=self.db_path)

        with self.assertRaises(inventory_service.ValidationError):
            inventory_service.adjust_stock(product_id=prod["id"], change_quantity=0, reason="RESTOCK", db_path=self.db_path)

    # -----------------------------------------------------------------------
    # Low-Stock Detection Tests
    # -----------------------------------------------------------------------

    def test_low_stock_detection(self):
        """Verifies low-stock logic: active products where stock <= min_threshold."""
        # 1. Product exactly at threshold (stock=5, min_threshold=5) -> LOW STOCK
        p_at_threshold = inventory_service.create_product(
            sku="SKU-AT-THRESH", name="Item At Threshold", price=10.0, stock=5, min_threshold=5, db_path=self.db_path
        )

        # 2. Product below threshold (stock=2, min_threshold=5) -> LOW STOCK
        p_below_threshold = inventory_service.create_product(
            sku="SKU-BELOW-THRESH", name="Item Below Threshold", price=10.0, stock=2, min_threshold=5, db_path=self.db_path
        )

        # 3. Product above threshold (stock=10, min_threshold=5) -> NOT LOW STOCK
        p_above_threshold = inventory_service.create_product(
            sku="SKU-ABOVE-THRESH", name="Item Above Threshold", price=10.0, stock=10, min_threshold=5, db_path=self.db_path
        )

        # 4. Deactivated product below threshold -> MUST NOT be in alert list
        p_deactivated = inventory_service.create_product(
            sku="SKU-DEACT-LOW", name="Deactivated Low", price=10.0, stock=1, min_threshold=5, db_path=self.db_path
        )
        inventory_service.deactivate_product(p_deactivated["id"], db_path=self.db_path)

        low_stock_items = inventory_service.get_low_stock_products(db_path=self.db_path)
        low_stock_ids = [p["id"] for p in low_stock_items]

        # Verify active items at or below threshold are included
        self.assertIn(p_at_threshold["id"], low_stock_ids)
        self.assertIn(p_below_threshold["id"], low_stock_ids)

        # Verify item above threshold is NOT included
        self.assertNotIn(p_above_threshold["id"], low_stock_ids)

        # Verify deactivated item is NOT included
        self.assertNotIn(p_deactivated["id"], low_stock_ids)

        # Verify is_low_stock helper
        self.assertTrue(inventory_service.is_low_stock(p_at_threshold["id"], db_path=self.db_path))
        self.assertTrue(inventory_service.is_low_stock(p_below_threshold["id"], db_path=self.db_path))
        self.assertFalse(inventory_service.is_low_stock(p_above_threshold["id"], db_path=self.db_path))
        self.assertFalse(inventory_service.is_low_stock(p_deactivated["id"], db_path=self.db_path))


if __name__ == "__main__":
    unittest.main()
