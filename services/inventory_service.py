"""Inventory & Stock Business Logic Service.

Handles:
- Product creation, validation, updating, and deactivation
- Product search, filtering, and retrieval
- Transaction-safe incoming and outgoing stock adjustments
- Low-stock detection and warning queries
"""

import sqlite3
import math
from typing import Optional, List, Dict, Any

from database import get_connection, get_current_timestamp


# ---------------------------------------------------------------------------
# Custom Exceptions for Clear Error Handling
# ---------------------------------------------------------------------------

class InventoryError(Exception):
    """Base exception for all inventory operations."""
    pass


class ValidationError(InventoryError):
    """Raised when user input violates validation rules (e.g. empty names, negative numbers)."""
    pass


class DuplicateSKUError(InventoryError):
    """Raised when attempting to add or edit a product with an already existing SKU."""
    pass


class ProductNotFoundError(InventoryError):
    """Raised when a requested product ID or SKU does not exist."""
    pass


class InsufficientStockError(InventoryError):
    """Raised when an adjustment or sale would cause stock to fall below zero."""
    pass


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Converts a sqlite3.Row object to a standard Python dictionary."""
    return dict(row) if row else {}


def _whole_number(value: Any, label: str) -> int:
    try:
        number = float(value)
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError
        return int(number)
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f"{label} must be a whole number.")


def _insert_product_in_transaction(
    conn: sqlite3.Connection,
    sku: str,
    name: str,
    category: str,
    price: float,
    cost_price: Optional[float],
    stock: int,
    min_threshold: int,
    description: str,
    now: str,
    movement_notes: str = "Initial inventory on product creation",
) -> int:
    """Insert a product and its opening movement inside the caller's transaction."""
    try:
        cursor = conn.execute(
            """INSERT INTO products
               (sku, name, category, price, cost_price, stock, min_threshold,
                description, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?);""",
            (sku, name, category, price, cost_price, stock, min_threshold, description, now, now),
        )
    except sqlite3.IntegrityError as err:
        if "UNIQUE constraint failed: products.sku" in str(err) or "products.sku" in str(err):
            raise DuplicateSKUError(f"A product with SKU '{sku}' already exists.") from err
        raise ValidationError(f"Database rejected product data: {err}") from err

    product_id = cursor.lastrowid
    if stock > 0:
        conn.execute(
            """INSERT INTO stock_movements
               (product_id, change_quantity, previous_stock, new_stock, reason, notes, created_at)
               VALUES (?, ?, 0, ?, 'INITIAL_STOCK', ?, ?);""",
            (product_id, stock, stock, movement_notes, now),
        )
    return product_id


# ---------------------------------------------------------------------------
# Product Operations (CRUD & Search)
# ---------------------------------------------------------------------------

def create_product(
    sku: str,
    name: str,
    price: float,
    stock: int = 0,
    min_threshold: int = 5,
    category: str = "General",
    description: str = "",
    db_path: Optional[str] = None,
    cost_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Creates a new product with full field validation.

    If initial stock > 0, an initial stock movement record is atomically created.
    """
    # 1. Input sanitization and validation
    clean_sku = str(sku).strip() if sku is not None else ""
    clean_name = str(name).strip() if name is not None else ""
    clean_category = str(category).strip() if category is not None else "General"
    clean_desc = str(description).strip() if description is not None else ""

    if not clean_sku:
        raise ValidationError("Product SKU / Code cannot be empty.")
    if not clean_name:
        raise ValidationError("Product name cannot be empty.")
    if not clean_category:
        clean_category = "General"

    try:
        num_price = round(float(price), 2)
    except (ValueError, TypeError):
        raise ValidationError("Price must be a valid numeric value.")
    if not math.isfinite(num_price) or num_price < 0:
        raise ValidationError("Price must be a finite non-negative number.")

    num_cost = None
    if cost_price not in (None, ""):
        try:
            num_cost = round(float(cost_price), 2)
        except (ValueError, TypeError):
            raise ValidationError("Cost price must be a valid numeric value.")
        if not math.isfinite(num_cost) or num_cost < 0:
            raise ValidationError("Cost price must be a finite non-negative number.")

    num_stock = _whole_number(stock, "Stock quantity")
    if num_stock < 0:
        raise ValidationError("Stock quantity cannot be negative.")

    num_threshold = _whole_number(min_threshold, "Minimum stock threshold")
    if num_threshold < 0:
        raise ValidationError("Minimum stock threshold cannot be negative.")

    # 2. Database Insertion with transaction safety
    conn = get_connection(db_path)
    now = get_current_timestamp()

    try:
        with conn:
            product_id = _insert_product_in_transaction(
                conn, clean_sku, clean_name, clean_category, num_price, num_cost,
                num_stock, num_threshold, clean_desc, now,
            )

        return get_product_by_id(product_id, db_path=db_path)
    finally:
        conn.close()


def seed_demo_products(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Insert the marked demo catalog only when no products exist.

    The entire batch runs under one SQLite write transaction. Repeated calls,
    or calls against any non-empty catalog, are no-ops.
    """
    from services.demo_data import DEMO_PRODUCTS

    conn = get_connection(db_path)
    created = []
    now = get_current_timestamp()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        existing_count = conn.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
        if existing_count:
            conn.rollback()
            return {
                "seeded": False,
                "reason": "catalog_not_empty",
                "existing_product_count": existing_count,
                "products": [],
            }

        for item in DEMO_PRODUCTS:
            _insert_product_in_transaction(
                conn=conn,
                sku=item["sku"],
                name=item["name"],
                category=item["category"],
                price=item["price"],
                cost_price=item["cost_price"],
                stock=item["stock"],
                min_threshold=item["min_threshold"],
                description=item["description"],
                now=now,
                movement_notes="Demo seed initial stock",
            )
            created.append({"sku": item["sku"], "name": item["name"]})

        conn.commit()
        return {"seeded": True, "inserted_count": len(created), "products": created}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_product(
    product_id: int,
    name: Optional[str] = None,
    category: Optional[str] = None,
    price: Optional[float] = None,
    min_threshold: Optional[int] = None,
    description: Optional[str] = None,
    sku: Optional[str] = None,
    is_active: Optional[int] = None,
    db_path: Optional[str] = None,
    cost_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Updates an existing product's details.

    Note: Stock quantities are NOT changed here; stock changes must go through
    adjust_stock() to maintain an unbroken audit trail.
    """
    existing = get_product_by_id(product_id, db_path=db_path)
    if not existing:
        raise ProductNotFoundError(f"Product with ID {product_id} not found.")

    new_sku = existing["sku"]
    if sku is not None:
        clean_sku = str(sku).strip()
        if not clean_sku:
            raise ValidationError("Product SKU cannot be empty.")
        new_sku = clean_sku

    new_name = existing["name"]
    if name is not None:
        clean_name = str(name).strip()
        if not clean_name:
            raise ValidationError("Product name cannot be empty.")
        new_name = clean_name

    new_category = existing["category"]
    if category is not None:
        clean_cat = str(category).strip()
        new_category = clean_cat if clean_cat else "General"

    new_price = existing["price"]
    if price is not None:
        try:
            num_price = round(float(price), 2)
        except (ValueError, TypeError):
            raise ValidationError("Price must be a valid numeric value.")
        if not math.isfinite(num_price) or num_price < 0:
            raise ValidationError("Price must be a finite non-negative number.")
        new_price = num_price

    new_cost = existing.get("cost_price")
    if cost_price is not None:
        if cost_price == "":
            new_cost = None
        else:
            try:
                new_cost = round(float(cost_price), 2)
            except (ValueError, TypeError):
                raise ValidationError("Cost price must be a valid numeric value.")
            if not math.isfinite(new_cost) or new_cost < 0:
                raise ValidationError("Cost price must be a finite non-negative number.")

    new_threshold = existing["min_threshold"]
    if min_threshold is not None:
        num_thresh = _whole_number(min_threshold, "Minimum stock threshold")
        if num_thresh < 0:
            raise ValidationError("Minimum stock threshold cannot be negative.")
        new_threshold = num_thresh

    new_desc = existing["description"]
    if description is not None:
        new_desc = str(description).strip()

    new_active = existing["is_active"]
    if is_active is not None:
        if is_active not in (0, 1):
            raise ValidationError("is_active must be 1 (active) or 0 (deactivated).")
        new_active = int(is_active)

    conn = get_connection(db_path)
    now = get_current_timestamp()

    try:
        with conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE products
                    SET sku = ?, name = ?, category = ?, price = ?, cost_price = ?, min_threshold = ?, description = ?, is_active = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (new_sku, new_name, new_category, new_price, new_cost, new_threshold, new_desc, new_active, now, product_id),
                )
            except sqlite3.IntegrityError as err:
                if "UNIQUE constraint failed: products.sku" in str(err) or "products.sku" in str(err):
                    raise DuplicateSKUError(f"A product with SKU '{new_sku}' already exists.") from err
                raise ValidationError(f"Database error updating product: {err}") from err

        return get_product_by_id(product_id, db_path=db_path)
    finally:
        conn.close()


def get_product_by_id(product_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches a single product by its integer ID."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?;", (product_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_product_by_sku(sku: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches a single product by its unique SKU code."""
    clean_sku = str(sku).strip()
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE sku = ?;", (clean_sku,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_products(
    active_only: bool = False,
    category: Optional[str] = None,
    search_query: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Returns a list of products with optional filtering by active status, category, and text search."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM products WHERE 1=1"
        params: List[Any] = []

        if active_only:
            query += " AND is_active = 1"

        if category and category.strip() and category.strip() != "All Categories":
            query += " AND category = ?"
            params.append(category.strip())

        if search_query and search_query.strip():
            term = f"%{search_query.strip()}%"
            query += " AND (name LIKE ? OR sku LIKE ? OR description LIKE ?)"
            params.extend([term, term, term])

        query += " ORDER BY name ASC;"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def search_products(
    query: str,
    active_only: bool = False,
    category: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convenience alias for searching products."""
    return list_products(active_only=active_only, category=category, search_query=query, db_path=db_path)


def get_categories(db_path: Optional[str] = None) -> List[str]:
    """Retrieves all distinct categories currently assigned to active or inactive products."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC;")
        rows = cursor.fetchall()
        return [row["category"] for row in rows]
    finally:
        conn.close()


def deactivate_product(product_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Safely deactivates a product so historical orders are preserved while hiding it from checkout."""
    return update_product(product_id, is_active=0, db_path=db_path)


def reactivate_product(product_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Reactivates a previously deactivated product."""
    return update_product(product_id, is_active=1, db_path=db_path)


# ---------------------------------------------------------------------------
# Stock Operations (Restock, Adjustments, Audit Trail)
# ---------------------------------------------------------------------------

def adjust_stock(
    product_id: int,
    change_quantity: int,
    reason: str,
    notes: str = "",
    reference_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Adjusts a product's stock within a single atomic SQLite transaction.

    - change_quantity > 0: Incoming stock (e.g. RESTOCK, RETURN)
    - change_quantity < 0: Outgoing stock (e.g. DAMAGE, LOSS, CORRECTION)
    - Rejects any adjustment that would result in new_stock < 0.
    - Creates an audit record in stock_movements.
    - Transaction automatically rolls back on any error.
    """
    clean_reason = str(reason).strip() if reason is not None else ""
    if not clean_reason:
        raise ValidationError("Adjustment reason is required.")

    qty_change = _whole_number(change_quantity, "Change quantity")

    if qty_change == 0:
        raise ValidationError("Change quantity cannot be zero.")

    clean_notes = str(notes).strip() if notes is not None else ""
    clean_ref = str(reference_id).strip() if reference_id is not None else None

    conn = get_connection(db_path)
    now = get_current_timestamp()

    try:
        with conn:
            cursor = conn.cursor()
            # Fetch current stock inside the transaction
            cursor.execute("SELECT id, stock, is_active FROM products WHERE id = ?;", (product_id,))
            product = cursor.fetchone()

            if not product:
                raise ProductNotFoundError(f"Product with ID {product_id} not found.")

            current_stock = product["stock"]
            new_stock = current_stock + qty_change

            # Prevent negative stock
            if new_stock < 0:
                raise InsufficientStockError(
                    f"Cannot reduce stock by {abs(qty_change)}. Current stock is {current_stock}, "
                    f"which would result in {new_stock} (negative stock is not allowed)."
                )

            # Update product stock
            cursor.execute(
                "UPDATE products SET stock = ?, updated_at = ? WHERE id = ?;",
                (new_stock, now, product_id),
            )

            # Insert stock movement audit log
            cursor.execute(
                """
                INSERT INTO stock_movements (
                    product_id, change_quantity, previous_stock, new_stock, reason, reference_id, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (product_id, qty_change, current_stock, new_stock, clean_reason, clean_ref, clean_notes, now),
            )
            movement_id = cursor.lastrowid

        return {
            "movement_id": movement_id,
            "product_id": product_id,
            "previous_stock": current_stock,
            "new_stock": new_stock,
            "change_quantity": qty_change,
            "reason": clean_reason,
            "reference_id": clean_ref,
            "notes": clean_notes,
            "created_at": now,
        }
    finally:
        conn.close()


def get_stock_movements(
    product_id: Optional[int] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieves stock movement audit records, optionally filtered by product_id."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        if product_id is not None:
            cursor.execute(
                """
                SELECT sm.*, p.name AS product_name, p.sku AS product_sku
                FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                WHERE sm.product_id = ?
                ORDER BY sm.created_at DESC, sm.id DESC
                LIMIT ?;
                """,
                (product_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT sm.*, p.name AS product_name, p.sku AS product_sku
                FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                ORDER BY sm.created_at DESC, sm.id DESC
                LIMIT ?;
                """,
                (limit,),
            )
        rows = cursor.fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Low-Stock Detection & Alerts
# ---------------------------------------------------------------------------

def get_low_stock_products(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all ACTIVE products whose current stock is at or below their minimum threshold.

    Condition: is_active = 1 AND stock <= min_threshold
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM products
            WHERE is_active = 1 AND stock <= min_threshold
            ORDER BY stock ASC, name ASC;
            """
        )
        rows = cursor.fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def is_low_stock(product_id: int, db_path: Optional[str] = None) -> bool:
    """Checks whether a single active product is at or below its low stock threshold."""
    prod = get_product_by_id(product_id, db_path=db_path)
    if not prod or prod.get("is_active") != 1:
        return False
    return prod["stock"] <= prod["min_threshold"]
