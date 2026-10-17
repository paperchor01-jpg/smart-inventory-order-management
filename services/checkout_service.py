"""Checkout & Order Processing Business Logic Service.

Handles:
- Cart line total and order amount calculations using Decimal precision
- Atomic, transaction-safe checkout and stock deduction
- Stock movement audit recording for sales
- Receipt formatting, generation, and regeneration
"""

import os
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional

from database import get_connection, get_current_timestamp, get_setting
from services.inventory_service import InsufficientStockError, ValidationError, ProductNotFoundError


RECEIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "receipts")


def _to_decimal(val: Any) -> Decimal:
    """Converts a number or string to a Decimal."""
    if isinstance(val, Decimal):
        return val
    try:
        number = Decimal(str(val))
        if not number.is_finite():
            raise ValueError("non-finite number")
        return number
    except Exception as e:
        raise ValidationError(f"Invalid monetary value: {val}") from e


def _quantize_currency(val: Decimal) -> Decimal:
    """Rounds currency to exactly two decimal places using standard ROUND_HALF_UP."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_totals(
    cart_items: List[Dict[str, Any]],
    discount_amount: float = 0.0,
    tax_rate_percent: float = 0.0,
) -> Dict[str, Any]:
    """Calculates order totals accurately with Decimal precision.

    Returns dict with Decimal and float representations of subtotal, discount,
    tax_rate, tax_amount, and total_amount.
    """
    subtotal = Decimal("0.00")

    for item in cart_items:
        unit_price = _quantize_currency(_to_decimal(item.get("unit_price", 0)))
        qty_decimal = _to_decimal(item.get("quantity", 0))
        if qty_decimal != qty_decimal.to_integral_value():
            raise ValidationError("Item quantity must be a whole number.")
        qty = int(qty_decimal)
        if qty <= 0:
            raise ValidationError(f"Item quantity must be greater than zero. Got {qty}.")
        if unit_price < Decimal("0.00"):
            raise ValidationError(f"Item price cannot be negative. Got {unit_price}.")
        subtotal += unit_price * qty

    subtotal = _quantize_currency(subtotal)

    disc = _quantize_currency(_to_decimal(discount_amount if discount_amount is not None else 0.0))
    if disc < Decimal("0.00"):
        raise ValidationError("Discount cannot be negative.")
    if disc > subtotal:
        raise ValidationError(f"Discount ({disc}) cannot exceed order subtotal ({subtotal}).")

    discounted_subtotal = subtotal - disc

    tax_rate = _to_decimal(tax_rate_percent if tax_rate_percent is not None else 0.0)
    if tax_rate < Decimal("0.00"):
        raise ValidationError("Tax rate cannot be negative.")

    tax_amount = _quantize_currency(discounted_subtotal * (tax_rate / Decimal("100.0")))
    total_amount = _quantize_currency(discounted_subtotal + tax_amount)

    return {
        "subtotal": float(subtotal),
        "discount_amount": float(disc),
        "tax_rate": float(tax_rate),
        "tax_amount": float(tax_amount),
        "total_amount": float(total_amount),
        "_subtotal_dec": subtotal,
        "_discount_dec": disc,
        "_tax_amount_dec": tax_amount,
        "_total_dec": total_amount,
    }


def generate_order_number() -> str:
    """Generates a human-readable unique order identifier based on timestamp and sequence."""
    from datetime import datetime
    import random
    prefix = datetime.now().strftime("ORD-%Y%m%d-%H%M%S")
    suffix = f"{random.randint(100, 999)}"
    return f"{prefix}-{suffix}"


def process_checkout(
    cart_items: List[Dict[str, Any]],
    discount_amount: float = 0.0,
    tax_rate_percent: Optional[float] = None,
    notes: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Executes atomic checkout transaction.

    Steps in a single transaction:
    1. Validates cart items and quantities.
    2. Checks product existence, active status, and re-verifies sufficient stock.
    3. Calculates line totals, subtotal, discount, tax, and final amount.
    4. Inserts order into 'orders'.
    5. Inserts items into 'order_items' (saving snapshot of name & price).
    6. Deducts inventory stock from 'products'.
    7. Inserts audit records in 'stock_movements' (reason='SALE').
    8. Commits transaction or rolls back completely if anything fails.
    9. Generates and writes text receipt to receipts/ folder.
    """
    if not cart_items:
        raise ValidationError("Cannot checkout with an empty cart.")

    # Determine tax rate
    if tax_rate_percent is None:
        saved_tax = get_setting("tax_rate_percent", "0.0", db_path=db_path)
        try:
            tax_rate_percent = float(saved_tax)
        except (ValueError, TypeError):
            tax_rate_percent = 0.0

    order_number = generate_order_number()
    now = get_current_timestamp()
    conn = get_connection(db_path)

    try:
        with conn:
            cursor = conn.cursor()

            # 1. Fetch, lock, and validate each item in cart
            processed_items = []
            merged_quantities = {}
            for item in cart_items:
                product_id = item.get("product_id")
                req_qty = item.get("quantity")

                if not product_id:
                    raise ValidationError("Cart item missing product ID.")

                try:
                    product_id_decimal = _to_decimal(product_id)
                    qty_decimal = _to_decimal(req_qty)
                    if product_id_decimal != product_id_decimal.to_integral_value() or qty_decimal != qty_decimal.to_integral_value():
                        raise ValueError("fractional value")
                    product_id = int(product_id_decimal)
                    qty = int(qty_decimal)
                except (ValueError, TypeError, OverflowError):
                    raise ValidationError(f"Quantity must be a valid integer. Got {req_qty}.")

                if qty <= 0:
                    raise ValidationError(f"Quantity must be greater than zero. Got {qty}.")

                merged_quantities[product_id] = merged_quantities.get(product_id, 0) + qty

            for product_id, qty in merged_quantities.items():

                cursor.execute(
                    "SELECT id, sku, name, price, cost_price, stock, is_active FROM products WHERE id = ?;",
                    (product_id,),
                )
                product = cursor.fetchone()

                if not product:
                    raise ProductNotFoundError(f"Product ID {product_id} not found in database.")

                if product["is_active"] != 1:
                    raise ValidationError(f"Product '{product['name']}' is deactivated and cannot be sold.")

                current_stock = product["stock"]
                if current_stock < qty:
                    raise InsufficientStockError(
                        f"Insufficient stock for '{product['name']}' (SKU: {product['sku']}). "
                        f"In stock: {current_stock}, Requested: {qty}."
                    )

                unit_price = float(product["price"])
                line_total = float(_quantize_currency(_to_decimal(unit_price) * qty))

                processed_items.append({
                    "product_id": product["id"],
                    "sku": product["sku"],
                    "name": product["name"],
                    "unit_price": unit_price,
                    "unit_cost": product["cost_price"],
                    "quantity": qty,
                    "line_total": line_total,
                    "current_stock": current_stock,
                    "new_stock": current_stock - qty,
                })

            # 2. Calculate totals
            calc_input = [{"unit_price": it["unit_price"], "quantity": it["quantity"]} for it in processed_items]
            totals = calculate_totals(calc_input, discount_amount=discount_amount, tax_rate_percent=tax_rate_percent)

            # 3. Insert order record
            cursor.execute(
                """
                INSERT INTO orders (
                    order_number, created_at, subtotal, discount_amount, tax_rate, tax_amount, total_amount, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    order_number,
                    now,
                    totals["subtotal"],
                    totals["discount_amount"],
                    totals["tax_rate"],
                    totals["tax_amount"],
                    totals["total_amount"],
                    notes.strip() if notes else None,
                ),
            )
            order_id = cursor.lastrowid

            # 4. Insert order items & update inventory stock
            for it in processed_items:
                cursor.execute(
                    """
                    INSERT INTO order_items (
                        order_id, product_id, product_sku, product_name, unit_price, unit_cost, quantity, line_total
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        order_id,
                        it["product_id"],
                        it["sku"],
                        it["name"],
                        it["unit_price"],
                        it["unit_cost"],
                        it["quantity"],
                        it["line_total"],
                    ),
                )

                # Deduct stock
                cursor.execute(
                    "UPDATE products SET stock = ?, updated_at = ? WHERE id = ?;",
                    (it["new_stock"], now, it["product_id"]),
                )

                # Insert stock movement audit log
                cursor.execute(
                    """
                    INSERT INTO stock_movements (
                        product_id, change_quantity, previous_stock, new_stock, reason, reference_id, notes, created_at
                    ) VALUES (?, ?, ?, ?, 'SALE', ?, ?, ?);
                    """,
                    (
                        it["product_id"],
                        -it["quantity"],
                        it["current_stock"],
                        it["new_stock"],
                        order_number,
                        f"Sale checkout - Order {order_number}",
                        now,
                    ),
                )

        # Transaction committed successfully! Now generate receipt
        order_dict = {
            "id": order_id,
            "order_number": order_number,
            "created_at": now,
            "subtotal": totals["subtotal"],
            "discount_amount": totals["discount_amount"],
            "tax_rate": totals["tax_rate"],
            "tax_amount": totals["tax_amount"],
            "total_amount": totals["total_amount"],
            "notes": notes,
            "items": processed_items,
        }

        try:
            receipt_path = save_receipt_file(order_dict, db_path=db_path)
            order_dict["receipt_path"] = receipt_path
        except OSError as err:
            # The SQLite sale is already committed. Keep it successful and let
            # the receipt viewer regenerate text from the saved order.
            order_dict["receipt_path"] = None
            order_dict["receipt_error"] = str(err)

        return order_dict

    finally:
        conn.close()


def format_receipt_text(order_data: Dict[str, Any], db_path: Optional[str] = None) -> str:
    """Formats a clean, monospace printable text receipt."""
    store_name = get_setting("store_name", "Smart Store", db_path=db_path)
    currency = get_setting("currency_symbol", "₹", db_path=db_path)
    footer = get_setting("receipt_footer", "Thank you for your business!", db_path=db_path)

    width = 46
    border = "=" * width
    dash = "-" * width

    lines = []
    lines.append(border)
    lines.append(store_name.center(width))
    lines.append("RECEIPT / SALES INVOICE".center(width))
    lines.append(border)
    lines.append(f"Order No : {order_data.get('order_number', 'N/A')}")
    lines.append(f"Date/Time: {order_data.get('created_at', 'N/A')}")
    if order_data.get("notes"):
        lines.append(f"Notes    : {order_data['notes']}")
    lines.append(dash)

    # Table Header
    lines.append(f"{'Item':<22}{'Qty':>4} {'Price':>8} {'Total':>9}")
    lines.append(dash)

    items = order_data.get("items", [])
    for it in items:
        name = it.get("product_name") or it.get("name") or "Item"
        if len(name) > 21:
            name = name[:19] + ".."
        qty = it.get("quantity", 1)
        price = it.get("unit_price", 0.0)
        line_tot = it.get("line_total", 0.0)

        lines.append(f"{name:<22}{qty:>4} {price:>8.2f} {line_tot:>9.2f}")

    lines.append(dash)

    subtotal = order_data.get("subtotal", 0.0)
    discount = order_data.get("discount_amount", 0.0)
    tax_rate = order_data.get("tax_rate", 0.0)
    tax_amt = order_data.get("tax_amount", 0.0)
    total = order_data.get("total_amount", 0.0)

    lines.append(f"{'Subtotal:':<30}{currency}{subtotal:>14.2f}")
    if discount > 0:
        lines.append(f"{'Discount:':<30}-{currency}{discount:>13.2f}")
    if tax_amt > 0 or tax_rate > 0:
        tax_lbl = f"Tax ({tax_rate:.1f}%):"
        lines.append(f"{tax_lbl:<30}{currency}{tax_amt:>14.2f}")
    lines.append(border)
    lines.append(f"{'TOTAL PAYABLE:':<28}{currency}{total:>16.2f}")
    lines.append(border)
    lines.append(footer.center(width))
    lines.append(border)

    return "\n".join(lines)


def save_receipt_file(order_data: Dict[str, Any], receipts_folder: Optional[str] = None, db_path: Optional[str] = None) -> str:
    """Generates receipt content and writes it safely to receipts/<order_number>.txt."""
    folder = receipts_folder or RECEIPTS_DIR
    os.makedirs(folder, exist_ok=True)

    order_num = order_data.get("order_number", "receipt")
    # Clean filename of unsafe characters
    safe_order_num = "".join(c for c in order_num if c.isalnum() or c in ("-", "_"))
    filepath = os.path.join(folder, f"{safe_order_num}.txt")

    content = format_receipt_text(order_data, db_path=db_path)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def get_receipt_text(order_number: str, db_path: Optional[str] = None) -> str:
    """Retrieves receipt text from disk if it exists; otherwise regenerates it from the database."""
    safe_order_num = "".join(c for c in order_number if c.isalnum() or c in ("-", "_"))
    filepath = os.path.join(RECEIPTS_DIR, f"{safe_order_num}.txt")

    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    # Regenerate from database records
    order = get_order_by_number(order_number, db_path=db_path)
    if not order:
        raise ValidationError(f"Order '{order_number}' not found.")

    return format_receipt_text(order, db_path=db_path)


def get_order_by_id(order_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves an order and its items by order ID."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?;", (order_id,))
        order_row = cursor.fetchone()
        if not order_row:
            return None

        order_dict = dict(order_row)
        cursor.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id ASC;", (order_id,))
        items = [dict(r) for r in cursor.fetchall()]
        order_dict["items"] = items
        return order_dict
    finally:
        conn.close()


def get_order_by_number(order_number: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves an order and its items by order number."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE order_number = ?;", (order_number,))
        order_row = cursor.fetchone()
        if not order_row:
            return None

        order_dict = dict(order_row)
        cursor.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id ASC;", (order_dict["id"],))
        items = [dict(r) for r in cursor.fetchall()]
        order_dict["items"] = items
        return order_dict
    finally:
        conn.close()


def list_orders(
    search_query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Returns order history, optionally filtered by order number or date."""
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM orders WHERE 1=1"
        params = []
        if search_query and search_query.strip():
            query += " AND order_number LIKE ?"
            params.append(f"%{search_query.strip()}%")
        if start_date and start_date.strip():
            query += " AND created_at >= ?"
            params.append(f"{start_date.strip()} 00:00:00")
        if end_date and end_date.strip():
            query += " AND created_at <= ?"
            params.append(f"{end_date.strip()} 23:59:59")
        query += " ORDER BY created_at DESC, id DESC;"
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def cancel_order(order_number: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Cancels a completed order and restores its sold stock exactly once."""
    if not order_number or not str(order_number).strip():
        raise ValidationError("Order number is required.")

    conn = get_connection(db_path)
    now = get_current_timestamp()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        order = conn.execute(
            "SELECT id, status FROM orders WHERE order_number = ?;",
            (str(order_number).strip(),),
        ).fetchone()
        if not order:
            raise ValidationError(f"Order '{order_number}' was not found.")
        if order["status"] == "CANCELLED":
            raise ValidationError(f"Order '{order_number}' is already cancelled.")

        items = conn.execute(
            "SELECT product_id, product_sku, product_name, quantity FROM order_items WHERE order_id = ?;",
            (order["id"],),
        ).fetchall()
        if not items:
            raise ValidationError("This order has no items to restore.")

        for item in items:
            if item["product_id"] is None:
                raise ValidationError(
                    f"Cannot safely restore '{item['product_name']}' because its product record is missing."
                )
            product = conn.execute(
                "SELECT stock FROM products WHERE id = ?;", (item["product_id"],)
            ).fetchone()
            if not product:
                raise ValidationError(
                    f"Cannot safely restore '{item['product_name']}' because its product record is missing."
                )
            previous_stock = product["stock"]
            new_stock = previous_stock + item["quantity"]
            conn.execute(
                "UPDATE products SET stock = ?, updated_at = ? WHERE id = ?;",
                (new_stock, now, item["product_id"]),
            )
            conn.execute(
                """INSERT INTO stock_movements
                   (product_id, change_quantity, previous_stock, new_stock, reason, reference_id, notes, created_at)
                   VALUES (?, ?, ?, ?, 'ORDER_CANCEL', ?, ?, ?);""",
                (
                    item["product_id"], item["quantity"], previous_stock, new_stock,
                    order_number, f"Stock restored for cancelled order {order_number}", now,
                ),
            )

        conn.execute(
            "UPDATE orders SET status = 'CANCELLED', cancelled_at = ? WHERE id = ?;",
            (now, order["id"]),
        )
        conn.commit()
        return get_order_by_number(order_number, db_path=db_path)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
