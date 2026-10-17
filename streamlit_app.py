"""Simple browser-based frontend for the existing inventory application.

Run from the project folder with: streamlit run streamlit_app.py
This uses the same SQLite database and service layer as the Tkinter app.
"""

from datetime import date, timedelta
import os
import tempfile

import streamlit as st

import database
from services import checkout_service, inventory_service, report_service


st.set_page_config(page_title="Smart Inventory", page_icon="📦", layout="wide")
database.init_db()

if "cart" not in st.session_state:
    st.session_state.cart = []


def money(value):
    symbol = database.get_setting("currency_symbol", "₹")
    return f"{symbol}{float(value or 0):,.2f}"


def show_error(error):
    st.error(str(error))


def make_download(export_function, filename, **kwargs):
    """Create an export in a temporary folder and return its bytes for download."""
    with tempfile.TemporaryDirectory(prefix="inventory_export_") as folder:
        path = os.path.join(folder, filename)
        export_function(file_path=path, **kwargs)
        with open(path, "rb") as exported_file:
            return exported_file.read()


st.title("📦 Smart Inventory & Order Management")
st.caption("A simple web frontend connected to your existing local SQLite database.")

page = st.sidebar.radio(
    "Go to",
    ["Dashboard", "Products", "Stock", "Checkout", "Orders", "Reports", "Settings"],
)


if page == "Dashboard":
    st.header("Dashboard")
    metrics = report_service.get_dashboard_metrics()
    currency = metrics["currency_symbol"]
    cards = st.columns(5)
    cards[0].metric("Products", metrics["total_products"])
    cards[1].metric("Low stock", metrics["low_stock_count"])
    cards[2].metric("Out of stock", metrics["out_of_stock_count"])
    cards[3].metric("Sales today", f"{currency}{metrics['today_sales_revenue']:,.2f}")
    cards[4].metric("Orders today", metrics["today_orders_count"])
    st.subheader("Products needing attention")
    st.dataframe(metrics.get("urgent_restock", []), use_container_width=True, hide_index=True)
    st.subheader("Recent orders")
    st.dataframe(metrics.get("recent_orders", []), use_container_width=True, hide_index=True)


elif page == "Products":
    st.header("Products")
    with st.expander("Add a product", expanded=False):
        with st.form("add_product"):
            col1, col2 = st.columns(2)
            sku = col1.text_input("SKU / code *")
            name = col2.text_input("Product name *")
            col3, col4, col5 = st.columns(3)
            category = col3.text_input("Category", value="General")
            price = col4.number_input("Selling price *", min_value=0.0, step=1.0)
            cost_price = col5.number_input("Cost price", min_value=0.0, step=1.0)
            col6, col7 = st.columns(2)
            stock = col6.number_input("Starting stock", min_value=0, step=1)
            threshold = col7.number_input("Low-stock threshold", min_value=0, value=5, step=1)
            description = st.text_input("Description (optional)")
            submitted = st.form_submit_button("Save product", type="primary")
        if submitted:
            try:
                inventory_service.create_product(
                    sku=sku, name=name, category=category, price=price,
                    cost_price=cost_price, stock=stock, min_threshold=threshold,
                    description=description,
                )
                st.success(f"Added {name}.")
                st.rerun()
            except Exception as error:
                show_error(error)

    products = inventory_service.list_products(active_only=False)
    query = st.text_input("Search by name or SKU")
    active_only = st.checkbox("Show active products only", value=False)
    if query:
        products = inventory_service.list_products(active_only=active_only, search_query=query)
    elif active_only:
        products = inventory_service.list_products(active_only=True)
    st.dataframe(products, use_container_width=True, hide_index=True)

    if products:
        product_by_id = {p["id"]: p for p in products}
        chosen_id = st.selectbox(
            "Choose a product to edit or change its status",
            options=list(product_by_id),
            format_func=lambda product_id: (
                f"{product_by_id[product_id]['sku']} — {product_by_id[product_id]['name']}"
            ),
        )
        chosen = product_by_id[chosen_id]
        with st.expander("Edit selected product"):
            with st.form("edit_product"):
                edit_name = st.text_input("Name", value=chosen["name"])
                edit_category = st.text_input("Category", value=chosen["category"])
                edit_price = st.number_input("Selling price", min_value=0.0, value=float(chosen["price"]), step=1.0)
                edit_cost = st.number_input(
                    "Cost price", min_value=0.0,
                    value=float(chosen["cost_price"] or 0.0), step=1.0,
                )
                edit_threshold = st.number_input(
                    "Low-stock threshold", min_value=0,
                    value=int(chosen["min_threshold"]), step=1,
                )
                edit_description = st.text_input("Description", value=chosen["description"] or "")
                save_edit = st.form_submit_button("Save changes")
            if save_edit:
                try:
                    inventory_service.update_product(
                        chosen_id, name=edit_name, category=edit_category,
                        price=edit_price, cost_price=edit_cost,
                        min_threshold=edit_threshold, description=edit_description,
                    )
                    st.success("Product updated.")
                    st.rerun()
                except Exception as error:
                    show_error(error)
        status_label = "Deactivate" if chosen["is_active"] else "Reactivate"
        if st.button(f"{status_label} selected product"):
            try:
                if chosen["is_active"]:
                    inventory_service.deactivate_product(chosen_id)
                else:
                    inventory_service.reactivate_product(chosen_id)
                st.success(f"Product {status_label.lower()}d.")
                st.rerun()
            except Exception as error:
                show_error(error)


elif page == "Stock":
    st.header("Stock management")
    products = inventory_service.list_products(active_only=True)
    if not products:
        st.info("Add an active product before recording a stock movement.")
    else:
        by_id = {p["id"]: p for p in products}
        with st.form("stock_adjustment"):
            product_id = st.selectbox(
                "Product", options=list(by_id),
                format_func=lambda i: f"{by_id[i]['sku']} — {by_id[i]['name']} (stock: {by_id[i]['stock']})",
            )
            direction = st.radio("Movement", ["Stock in", "Stock out"], horizontal=True)
            quantity = st.number_input("Quantity", min_value=1, step=1)
            reason = st.selectbox(
                "Reason",
                ["RESTOCK", "CUSTOMER_RETURN", "SUPPLIER_SHIPMENT", "DAMAGED_GOODS", "EXPIRY_WASTE", "INVENTORY_CORRECTION", "OTHER"],
            )
            notes = st.text_input("Notes (optional)")
            save_movement = st.form_submit_button("Record stock movement", type="primary")
        if save_movement:
            try:
                signed_quantity = int(quantity) if direction == "Stock in" else -int(quantity)
                movement = inventory_service.adjust_stock(
                    product_id, signed_quantity, reason=reason, notes=notes,
                )
                st.success(f"Stock updated: {movement['previous_stock']} → {movement['new_stock']}.")
                st.rerun()
            except Exception as error:
                show_error(error)
    st.subheader("Recent stock movements")
    st.dataframe(inventory_service.get_stock_movements(limit=100), use_container_width=True, hide_index=True)


elif page == "Checkout":
    st.header("Checkout")
    products = inventory_service.list_products(active_only=True)
    available = [p for p in products if p["stock"] > 0]
    if not available:
        st.info("There are no in-stock products to sell.")
    else:
        by_id = {p["id"]: p for p in available}
        col1, col2 = st.columns([3, 1])
        product_id = col1.selectbox(
            "Product", options=list(by_id),
            format_func=lambda i: f"{by_id[i]['name']} — {money(by_id[i]['price'])} (stock {by_id[i]['stock']})",
        )
        quantity = col2.number_input("Quantity", min_value=1, max_value=by_id[product_id]["stock"], step=1)
        if st.button("Add to cart"):
            existing = next((line for line in st.session_state.cart if line["product_id"] == product_id), None)
            if existing:
                existing["quantity"] += int(quantity)
            else:
                st.session_state.cart.append({"product_id": product_id, "quantity": int(quantity)})

    cart_rows = []
    for line in st.session_state.cart:
        product = inventory_service.get_product_by_id(line["product_id"])
        if product:
            cart_rows.append({
                "Product": product["name"], "SKU": product["sku"],
                "Quantity": line["quantity"], "Unit price": money(product["price"]),
                "Line total": money(product["price"] * line["quantity"]),
            })
    st.subheader("Cart")
    st.dataframe(cart_rows, use_container_width=True, hide_index=True)
    if st.session_state.cart:
        remove_id = st.selectbox(
            "Remove a cart line (optional)",
            options=[line["product_id"] for line in st.session_state.cart],
            format_func=lambda i: next(
                (p["name"] for p in products if p["id"] == i), f"Product {i}"
            ),
        )
        col_a, col_b = st.columns(2)
        if col_a.button("Remove selected line"):
            st.session_state.cart = [line for line in st.session_state.cart if line["product_id"] != remove_id]
            st.rerun()
        if col_b.button("Empty cart"):
            st.session_state.cart = []
            st.rerun()

        discount = st.number_input("Discount", min_value=0.0, step=1.0)
        tax_default = float(database.get_setting("tax_rate_percent", "0.0"))
        tax_rate = st.number_input("Tax rate (%)", min_value=0.0, value=tax_default, step=0.5)
        if st.button("Complete sale", type="primary"):
            try:
                order = checkout_service.process_checkout(
                    st.session_state.cart,
                    discount_amount=discount,
                    tax_rate_percent=tax_rate,
                )
                receipt = checkout_service.format_receipt_text(order)
                st.session_state.cart = []
                st.success(f"Sale complete. Order {order['order_number']} — {money(order['total_amount'])}")
                st.code(receipt, language=None)
                st.download_button("Download receipt", receipt, file_name=f"{order['order_number']}.txt")
            except Exception as error:
                show_error(error)


elif page == "Orders":
    st.header("Orders")
    orders = checkout_service.list_orders()
    st.dataframe(orders, use_container_width=True, hide_index=True)
    if orders:
        by_number = {order["order_number"]: order for order in orders}
        order_number = st.selectbox("Choose an order", list(by_number))
        order = by_number[order_number]
        if st.button("Show receipt"):
            try:
                st.code(checkout_service.get_receipt_text(order_number), language=None)
            except Exception as error:
                show_error(error)
        if order["status"] == "COMPLETED":
            confirm = st.checkbox("I understand cancellation restores the items to stock.")
            if st.button("Cancel this order", disabled=not confirm):
                try:
                    checkout_service.cancel_order(order_number)
                    st.success("Order cancelled and stock restored.")
                    st.rerun()
                except Exception as error:
                    show_error(error)


elif page == "Reports":
    st.header("Reports")
    default_start = date.today() - timedelta(days=6)
    col1, col2 = st.columns(2)
    start = col1.date_input("From", value=default_start)
    end = col2.date_input("To", value=date.today())
    try:
        report = report_service.get_sales_report(start.isoformat(), end.isoformat())
        best_sellers = report_service.get_best_selling_products(start.isoformat(), end.isoformat())
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Revenue", money(report["total_revenue"]))
        col_b.metric("Orders", report["total_orders"])
        profit = report["estimated_gross_profit"]
        col_c.metric("Estimated gross profit", "N/A" if profit is None else money(profit))
        st.subheader("Best sellers")
        st.dataframe(best_sellers, use_container_width=True, hide_index=True)
        st.subheader("Orders in this period")
        st.dataframe(report["orders"], use_container_width=True, hide_index=True)

        exports = st.columns(3)
        exports[0].download_button(
            "Download sales CSV",
            make_download(report_service.export_sales_to_csv, "sales.csv", start_date=start.isoformat(), end_date=end.isoformat()),
            file_name="sales_report.csv", mime="text/csv",
        )
        exports[1].download_button(
            "Download products CSV",
            make_download(report_service.export_products_to_csv, "products.csv"),
            file_name="products_catalog.csv", mime="text/csv",
        )
        exports[2].download_button(
            "Download stock log CSV",
            make_download(report_service.export_stock_movements_to_csv, "stock_movements.csv"),
            file_name="stock_movements.csv", mime="text/csv",
        )
    except Exception as error:
        show_error(error)


elif page == "Settings":
    st.header("Store settings")
    with st.form("settings"):
        store_name = st.text_input("Store name", database.get_setting("store_name", "Campus Store"))
        currency = st.text_input("Currency symbol", database.get_setting("currency_symbol", "₹"))
        tax_rate = st.number_input(
            "Default tax rate (%)", min_value=0.0,
            value=float(database.get_setting("tax_rate_percent", "0.0")), step=0.5,
        )
        footer = st.text_input("Receipt footer", database.get_setting("receipt_footer", "Thank you for your business!"))
        save_settings = st.form_submit_button("Save settings", type="primary")
    if save_settings:
        if not store_name.strip() or not currency.strip():
            st.error("Store name and currency symbol are required.")
        else:
            database.set_setting("store_name", store_name.strip())
            database.set_setting("currency_symbol", currency.strip())
            database.set_setting("tax_rate_percent", f"{tax_rate:.1f}")
            database.set_setting("receipt_footer", footer.strip() or "Thank you for your business!")
            st.success("Settings saved.")

