"""Reporting & Analytics Business Logic Service.

Handles:
- Real-time Dashboard metrics calculation (products, inventory value, today's sales, low-stock count)
- Sales aggregation across custom date ranges
- Best-selling products ranking
- Standard CSV report generation into exports/
"""

import csv
import os
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Any, Optional

from database import get_connection, get_setting


EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")


def _validate_date_range(start_date: Optional[str], end_date: Optional[str]) -> None:
    try:
        start = date.fromisoformat(start_date.strip()) if start_date and start_date.strip() else None
        end = date.fromisoformat(end_date.strip()) if end_date and end_date.strip() else None
    except ValueError as err:
        raise ValueError("Dates must use YYYY-MM-DD format.") from err
    if start and end and start > end:
        raise ValueError("Start date must be on or before end date.")


def _safe_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet programs from interpreting exported text as a formula."""
    if isinstance(value, str) and value.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def get_dashboard_metrics(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Calculates all live dashboard summary metrics from SQLite database records."""
    conn = get_connection(db_path)
    today_str = date.today().strftime("%Y-%m-%d")

    try:
        cursor = conn.cursor()

        # 1. Total active products & inventory units & retail valuation
        cursor.execute(
            """
            SELECT 
                COUNT(*) AS total_products,
                COALESCE(SUM(stock), 0) AS total_units,
                COALESCE(SUM(stock * price), 0.0) AS total_inventory_value
            FROM products
            WHERE is_active = 1;
            """
        )
        prod_row = cursor.fetchone()
        total_products = prod_row["total_products"] if prod_row else 0
        total_units = prod_row["total_units"] if prod_row else 0
        total_inv_value = round(float(prod_row["total_inventory_value"]), 2) if prod_row else 0.0

        cursor.execute(
            """SELECT COALESCE(SUM(stock * cost_price), 0.0) AS cost_value,
                      SUM(CASE WHEN stock > 0 AND cost_price IS NULL THEN 1 ELSE 0 END) AS uncosted_stock_products
               FROM products WHERE is_active = 1;"""
        )
        valuation_row = cursor.fetchone()
        uncosted_stock_products = int(valuation_row["uncosted_stock_products"] or 0)
        cost_inventory_value = (
            round(float(valuation_row["cost_value"] or 0), 2)
            if uncosted_stock_products == 0 else None
        )

        # 2. Low-stock count for active products
        cursor.execute(
            """
            SELECT COUNT(*) AS low_stock_count
            FROM products
            WHERE is_active = 1 AND stock <= min_threshold;
            """
        )
        low_row = cursor.fetchone()
        low_stock_count = low_row["low_stock_count"] if low_row else 0

        # 3. Today's sales revenue & order count
        cursor.execute(
            """
            SELECT 
                COUNT(*) AS today_orders_count,
                COALESCE(SUM(total_amount), 0.0) AS today_sales_revenue
            FROM orders
            WHERE created_at LIKE ? AND status = 'COMPLETED';
            """,
            (f"{today_str}%",),
        )
        orders_row = cursor.fetchone()
        today_orders_count = orders_row["today_orders_count"] if orders_row else 0
        today_sales_revenue = round(float(orders_row["today_sales_revenue"]), 2) if orders_row else 0.0

        cursor.execute(
            "SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock = 0;"
        )
        out_of_stock_count = cursor.fetchone()[0]

        # 4. Recent orders (latest 5)
        cursor.execute(
            """
            SELECT id, order_number, created_at, total_amount, 
                   (SELECT COUNT(*) FROM order_items WHERE order_id = orders.id) AS item_count
            FROM orders
            WHERE status = 'COMPLETED'
            ORDER BY created_at DESC, id DESC
            LIMIT 5;
            """
        )
        recent_orders = [dict(r) for r in cursor.fetchall()]

        # 5. Low-stock products list (top 5 urgent)
        cursor.execute(
            """
            SELECT id, sku, name, category, stock, min_threshold
            FROM products
            WHERE is_active = 1 AND stock <= min_threshold
            ORDER BY stock ASC, name ASC
            LIMIT 5;
            """
        )
        urgent_restock = [dict(r) for r in cursor.fetchall()]

        return {
            "total_products": total_products,
            "total_units": total_units,
            "total_inventory_value": total_inv_value,
            "cost_inventory_value": cost_inventory_value,
            "uncosted_stock_products": uncosted_stock_products,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "today_orders_count": today_orders_count,
            "today_sales_revenue": today_sales_revenue,
            "recent_orders": recent_orders,
            "urgent_restock": urgent_restock,
            "currency_symbol": get_setting("currency_symbol", "₹", db_path=db_path),
        }

    finally:
        conn.close()


def get_sales_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates sales totals and transactions for an optional date range (YYYY-MM-DD)."""
    _validate_date_range(start_date, end_date)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM orders WHERE status = 'COMPLETED'"
        params = []

        if start_date and start_date.strip():
            query += " AND created_at >= ?"
            params.append(f"{start_date.strip()} 00:00:00")

        if end_date and end_date.strip():
            query += " AND created_at <= ?"
            params.append(f"{end_date.strip()} 23:59:59")

        query += " ORDER BY created_at DESC;"
        cursor.execute(query, params)
        orders = [dict(r) for r in cursor.fetchall()]

        total_orders = len(orders)
        total_revenue = round(sum(o["total_amount"] for o in orders), 2)
        total_discount = round(sum(o["discount_amount"] for o in orders), 2)
        total_tax = round(sum(o["tax_amount"] for o in orders), 2)
        avg_order_value = round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0

        cost_query = """SELECT
                COALESCE(SUM(oi.unit_cost * oi.quantity), 0.0) AS estimated_cost,
                SUM(CASE WHEN oi.unit_cost IS NULL THEN 1 ELSE 0 END) AS uncosted_lines
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE o.status = 'COMPLETED'"""
        cost_params = []
        if start_date and start_date.strip():
            cost_query += " AND o.created_at >= ?"
            cost_params.append(f"{start_date.strip()} 00:00:00")
        if end_date and end_date.strip():
            cost_query += " AND o.created_at <= ?"
            cost_params.append(f"{end_date.strip()} 23:59:59")
        cost_row = cursor.execute(cost_query, cost_params).fetchone()
        estimated_cost = round(float(cost_row["estimated_cost"] or 0), 2)
        uncosted_lines = int(cost_row["uncosted_lines"] or 0)
        revenue_before_tax = round(sum(o["subtotal"] - o["discount_amount"] for o in orders), 2)
        estimated_gross_profit = (
            round(revenue_before_tax - estimated_cost, 2) if uncosted_lines == 0 else None
        )

        return {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_discount": total_discount,
            "total_tax": total_tax,
            "revenue_before_tax": revenue_before_tax,
            "estimated_cost": estimated_cost if uncosted_lines == 0 else None,
            "estimated_gross_profit": estimated_gross_profit,
            "uncosted_lines": uncosted_lines,
            "avg_order_value": avg_order_value,
            "orders": orders,
            "start_date": start_date,
            "end_date": end_date,
        }
    finally:
        conn.close()


def get_best_selling_products(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Aggregates best-selling products by quantity sold."""
    _validate_date_range(start_date, end_date)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        query = """
            SELECT 
                oi.product_sku,
                oi.product_name,
                SUM(oi.quantity) AS total_quantity_sold,
                ROUND(SUM(oi.line_total), 2) AS total_revenue_generated
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE o.status = 'COMPLETED'
        """
        params = []

        if start_date and start_date.strip():
            query += " AND o.created_at >= ?"
            params.append(f"{start_date.strip()} 00:00:00")

        if end_date and end_date.strip():
            query += " AND o.created_at <= ?"
            params.append(f"{end_date.strip()} 23:59:59")

        query += """
            GROUP BY oi.product_sku, oi.product_name
            ORDER BY total_quantity_sold DESC, total_revenue_generated DESC
            LIMIT ?;
        """
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CSV Export Utilities
# ---------------------------------------------------------------------------

def _ensure_exports_dir(custom_path: Optional[str] = None) -> str:
    """Ensures export destination directory exists."""
    if custom_path:
        parent = os.path.dirname(custom_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return custom_path
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    return EXPORTS_DIR


def export_sales_to_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    file_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Exports sales orders within date range to a CSV file."""
    report = get_sales_report(start_date=start_date, end_date=end_date, db_path=db_path)
    orders = report.get("orders", [])

    if not file_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = os.path.join(EXPORTS_DIR, f"sales_report_{ts}.csv")
    else:
        target_path = file_path

    _ensure_exports_dir(target_path)

    headers = [
        "Order Number",
        "Date and Time",
        "Subtotal",
        "Discount",
        "Tax Rate (%)",
        "Tax Amount",
        "Total Amount",
        "Notes",
    ]

    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for o in orders:
            writer.writerow([
                _safe_csv_cell(o.get("order_number", "")),
                _safe_csv_cell(o.get("created_at", "")),
                f"{o.get('subtotal', 0.0):.2f}",
                f"{o.get('discount_amount', 0.0):.2f}",
                f"{o.get('tax_rate', 0.0):.1f}",
                f"{o.get('tax_amount', 0.0):.2f}",
                f"{o.get('total_amount', 0.0):.2f}",
                _safe_csv_cell(o.get("notes", "") or ""),
            ])

    return target_path


def export_products_to_csv(
    active_only: bool = False,
    file_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Exports inventory product catalog to a CSV file."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM products"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name ASC;"
        cursor.execute(query)
        products = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    if not file_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = os.path.join(EXPORTS_DIR, f"products_catalog_{ts}.csv")
    else:
        target_path = file_path

    _ensure_exports_dir(target_path)

    headers = [
        "ID",
        "SKU",
        "Product Name",
        "Category",
        "Price",
        "Cost Price",
        "Current Stock",
        "Min Threshold",
        "Status",
        "Description",
        "Created At",
        "Updated At",
    ]

    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for p in products:
            status = "Active" if p.get("is_active") == 1 else "Deactivated"
            writer.writerow([
                p.get("id"),
                _safe_csv_cell(p.get("sku", "")),
                _safe_csv_cell(p.get("name", "")),
                _safe_csv_cell(p.get("category", "")),
                f"{p.get('price', 0.0):.2f}",
                "" if p.get("cost_price") is None else f"{p['cost_price']:.2f}",
                p.get("stock", 0),
                p.get("min_threshold", 0),
                status,
                _safe_csv_cell(p.get("description", "") or ""),
                _safe_csv_cell(p.get("created_at", "")),
                _safe_csv_cell(p.get("updated_at", "")),
            ])

    return target_path


def export_stock_movements_to_csv(
    file_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Exports complete stock movement audit history to a CSV file."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sm.*, p.name AS product_name, p.sku AS product_sku
            FROM stock_movements sm
            JOIN products p ON sm.product_id = p.id
            ORDER BY sm.created_at DESC, sm.id DESC;
            """
        )
        movements = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    if not file_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = os.path.join(EXPORTS_DIR, f"stock_movements_{ts}.csv")
    else:
        target_path = file_path

    _ensure_exports_dir(target_path)

    headers = [
        "Movement ID",
        "Date and Time",
        "Product SKU",
        "Product Name",
        "Quantity Change",
        "Previous Stock",
        "New Stock",
        "Reason",
        "Reference ID",
        "Notes",
    ]

    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for m in movements:
            writer.writerow([
                m.get("id"),
                _safe_csv_cell(m.get("created_at", "")),
                _safe_csv_cell(m.get("product_sku", "")),
                _safe_csv_cell(m.get("product_name", "")),
                m.get("change_quantity", 0),
                m.get("previous_stock", 0),
                m.get("new_stock", 0),
                _safe_csv_cell(m.get("reason", "")),
                _safe_csv_cell(m.get("reference_id", "") or ""),
                _safe_csv_cell(m.get("notes", "") or ""),
            ])

    return target_path
