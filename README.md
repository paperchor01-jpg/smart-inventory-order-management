# Smart Inventory & Order Management System

A lightweight, robust, and local-first desktop application designed for small shop owners, campus stores, and college canteens. Built with **Python 3.14**, **Tkinter / ttk**, and **SQLite3**, adhering to a restrained **Neumorphic (Soft UI)** visual aesthetic with persistent sidebar navigation and card-based real-time metrics.

---

## 🌟 Key Features

1. **Module A — Live Dashboard Overview:**
   - 5 live metric cards: Total Active Products, Low-Stock Alert Count, Today's Sales Revenue, Orders Completed Today, and Out-of-Stock Products.
   - Live database-calculated metrics (no hardcoded or fake numbers).
   - Real-time lists for recent completed transactions and urgent low-stock alerts.
   - Quick navigation shortcuts.

2. **Module B — Product Management:**
   - Add, edit, search, and filter catalog items by name, SKU, or category.
   - Enforced validation: non-negative selling/cost prices, whole-number stock, and non-negative alert thresholds.
   - Optional cost price is shown in the catalog and included in product exports.
   - Unique SKU enforcement preventing duplicate product codes.
   - Safe soft-deactivation preserving historical sales references.

3. **Module C — Stock Tracking & Audit Trail:**
   - Live inventory level monitoring with colored status badges (`In Stock`, `LOW STOCK`, `OUT OF STOCK`).
   - Transaction-safe stock adjustments: Incoming (Restock, Return) and Outgoing (Damage, Expiry, Loss).
   - Guaranteed prevention of negative stock levels with automatic transaction rollback.
   - Unbroken audit log in `stock_movements` recording previous stock, new stock, reason, reference ID, and timestamp.

4. **Module D — Checkout & POS Ordering:**
   - Product catalog search and selection with live stock checking.
   - Interactive shopping cart with quantity modifications and live line totals.
   - Accurate currency calculations using Python `Decimal` (`ROUND_HALF_UP`) to prevent floating-point rounding errors.
   - Configurable tax rate and optional flat discount support with boundary validation.
   - **Atomic Transaction Safety:** Checkout verifies live stock, merges repeated cart lines, creates order items (with historical name, selling-price, and known cost-price snapshots), deducts inventory, and writes audit movements in one SQLite transaction.
   - Receipt file errors do not make a committed sale appear to fail; receipt text can be regenerated from the database.

5. **Module E — Receipts Generation:**
   - Automatic generation of clean, monospace-aligned text receipts saved to `receipts/<order_number>.txt`.
   - In-app receipt viewer dialog with "Open File", "Copy Text", and "New Sale" options.
   - On-demand receipt regeneration from historical database records if a receipt file is deleted.

6. **Order History and Cancellation:**
   - The Reports order table includes status, selected-order details, and date filtering.
   - Cancelling a completed order restores sold stock exactly once in a transaction and records an `ORDER_CANCEL` audit movement.
   - Cancelled orders remain visible in history and are excluded from sales totals and best-seller reports.

7. **Module F — Low-Stock Alerts:**
   - Automatic detection for active products where `stock <= min_threshold`.
   - Distinct visual warnings on both the Dashboard and Stock Management screens.

8. **Module G — Reports & CSV Exports:**
   - Sales analytics over custom date ranges (Today, Last 7 Days, All Time) displaying gross revenue, total orders, and average order value.
   - Best-selling products ranked by units sold and generated revenue.
   - Estimated cost and gross-profit cards use saved cost-price snapshots. If historical items have unknown cost, the UI shows `N/A` rather than inventing profit.
   - Current inventory value at cost is shown separately and becomes `N/A` when any in-stock product is missing a cost price.
   - Standard CSV exports saved to a user-selected destination:
     - Sales Reports (`sales_report_<timestamp>.csv`)
     - Product Catalog (`products_catalog_<timestamp>.csv`)
     - Stock Audit History (`stock_movements_<timestamp>.csv`)

9. **Settings & Customization:**
   - Persistent store configuration: Store Name, Currency Symbol (Default: **₹** INR), Default Tax Rate (Default: **0.0%**), and Receipt Footer.

---

## 🛠️ Technology Stack & Requirements

- **Python Version:** Python 3.10+ (Tested and verified on **Python 3.14.5** 64-bit).
- **GUI Framework:** Tkinter & ttk (included in the standard Python distribution).
- **Database:** SQLite 3.50+ via Python's built-in `sqlite3` library.
- **External Dependencies:** **Zero (0)**. The application exclusively uses the Python standard library.
- **Network / Cloud Requirements:** None. The application operates 100% offline.

---

## 📁 Project Directory Structure

```text
application/
├── main.py                     # Application entry point, window management, and sidebar
├── database.py                 # SQLite connection manager, foreign keys, and schema DDL
├── README.md                   # Complete documentation and hackathon demo guide
├── .gitignore                  # Excludes *.db, receipts, exports, and caches from git
│
├── services/                   # Pure business logic (completely independent of UI)
│   ├── __init__.py
│   ├── inventory_service.py   # Product CRUD, stock adjustments, and threshold alerts
│   ├── checkout_service.py    # Decimal math, atomic checkout, and receipt formatting
│   └── report_service.py      # Aggregations, date filters, and CSV export utilities
│
├── ui/                         # Desktop UI layer (Neumorphic styling & Tkinter/ttk)
│   ├── __init__.py
│   ├── components.py          # Design tokens, MetricCard, NeuPanel, and table helpers
│   ├── dashboard_view.py      # Module A: Overview cards and alert tables
│   ├── products_view.py       # Module B: Catalog table and Add/Edit modals
│   ├── stock_view.py          # Module C: Inventory levels, restock forms, and audit log
│   ├── checkout_view.py       # Module D & E: Cart, live calculation, and receipt viewer
│   ├── reports_view.py        # Module G: Analytics and CSV export triggers
│   └── settings_view.py       # Store configuration and preferences
│
├── tests/                      # Automated unit test suite (isolated temporary DBs)
│   ├── __init__.py
│   ├── test_database.py       # Schema integrity, foreign keys, constraints, idempotency
│   ├── test_inventory.py      # Product CRUD, duplicate SKU, stock rollback, alerts
│   ├── test_checkout.py       # Checkout calculations, atomic deduction, receipt regen
│   └── test_reports.py        # Metrics, date queries, and CSV generation
│
├── data/                       # Local SQLite database and migration backups (*.db ignored by git)
├── receipts/                   # Generated text receipts (*.txt ignored by git)
│   └── .gitkeep
└── exports/                    # Exported CSV reports (*.csv ignored by git)
    └── .gitkeep
```

---

## 🚀 How to Run the Application on Windows

Open PowerShell or Command Prompt in the `application` folder:

```powershell
# Navigate to the project directory if not already there
cd c:\Users\hp\OneDrive\Desktop\application

# Launch the desktop application
python main.py
```

*Note: On first run, the SQLite database (`data/inventory.db`) is automatically created with all required tables, indexes, and default settings.*

### Optional Streamlit web frontend

The project also includes a simple browser-based frontend that uses the same services and `data/inventory.db` file:

```powershell
python -m pip install streamlit
streamlit run streamlit_app.py
```

This is an additional interface; `python main.py` continues to launch the Tkinter desktop app. Both interfaces use the same local database, so sales and stock updates in either interface are shared.

### Optional hackathon demo products

Demo products are added only when you explicitly run this separate command:

```powershell
python seed_demo_products.py
```

The command adds ten sample products to the existing database. Their names begin with `[DEMO]`, and their SKUs begin with `DEMO-`. It also records opening stock movements for products with stock. It refuses to add anything if even one product is already in the catalog, and it is not run by `python main.py`. To use a separate database file, run `python seed_demo_products.py --db path\to\demo.db`.

After the demonstration, use the **Products** screen to find the `[DEMO]` entries and deactivate them. Deactivation keeps the product and stock history available for past orders and audit records. The application has no permanent-delete action; leave demo rows deactivated if you want to preserve that history.

---

## 🧪 How to Run Automated Tests

The application includes unit tests that run against isolated temporary databases without modifying the user's live database.

```powershell
# Run the entire test suite
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 📋 9-Step College Hackathon Demo Sequence

To demonstrate the application during the 6-hour hackathon, follow this workflow:

1. **Launch the Application:**
   Run `python main.py`. Point out the Neumorphic interface, the persistent left sidebar, and the 4 metric cards initializing at zero on a clean database.
2. **Add a Product:**
   - Click **`🏷️ Products`** in the sidebar.
   - Click **`+ Add New Product`**.
   - Enter: SKU `SKU-NOTEBOOK`, Name `Spiral Notebook`, Category `Stationery`, Price `50.00`, Initial Stock `10`, Threshold `5`. Click **`Save Product`**.
   - Notice the item appears in the catalog and an initial stock movement is logged.
3. **Adjust Stock (Restock):**
   - Click **`⚡ Stock Management`** in the sidebar.
   - Click **`⚡ Adjust Stock`**.
   - Select `Spiral Notebook`, choose `Incoming / Restock (+)`, enter Quantity `15`, Reason `RESTOCK`, Notes `Supplier delivery`.
   - Click **`Apply Adjustment`**. Stock updates from 10 to 25 and appears immediately in the audit trail.
4. **Trigger Low-Stock Condition:**
   - Go to **`Products`** -> **`+ Add New Product`**.
   - Enter: SKU `SKU-PEN`, Name `Blue Gel Pen`, Price `15.00`, Initial Stock `3`, Threshold `5`. Save it.
   - Go to **`📊 Dashboard`**: Observe that the **Low-Stock Alert** card immediately increments to `1`, and `Blue Gel Pen` is listed under the urgent alert panel.
5. **Complete a Valid Checkout:**
   - Click **`🛒 Checkout`** in the sidebar.
   - Select `Spiral Notebook` from the left catalog, enter Qty `2`, click **`+ Add to Cart`**.
   - Select `Blue Gel Pen`, enter Qty `1`, click **`+ Add to Cart`**.
   - Enter Discount `5.00`.
   - Observe live Subtotal (`115.00`), Discount (`5.00`), and Total Payable (`110.00`).
   - Click **`✓ Complete Sale & Issue Receipt`**.
6. **Verify Inventory Deduction:**
   - Switch to **`⚡ Stock Management`**.
   - Verify `Spiral Notebook` stock has decreased from 25 to 23, and `Blue Gel Pen` from 3 to 2.
   - Note the new `SALE` entries in the audit trail linked to the unique order number.
7. **Inspect the Generated Receipt:**
   - Review the receipt displayed in the modal dialog.
   - Click **`📄 Open Receipt File`** to view the saved `.txt` file in `receipts/`.
8. **Review Sales Reports:**
   - Click **`📈 Reports`** in the sidebar.
   - Click **`Today`** preset.
   - Verify Total Revenue (`₹110.00`), Completed Orders (`1`), and that `Spiral Notebook` and `Blue Gel Pen` are displayed in the **Best-Selling Products** table.
9. **Export a CSV Report:**
   - Click **`📥 Export Sales CSV`**.
   - Confirm the success dialog and verify the exported file in the `exports/` folder.

---

## 🔒 Security & Architectural Decisions

- **Data Isolation:** Automated tests always spin up fresh temporary database files, preventing test pollution of production/demo records.
- **Atomic Transactions:** Order creation and inventory deduction are wrapped in a single database transaction (`with conn:`). If any product lacks stock, the entire checkout is rolled back.
- **Historical Snapshots:** Order items snapshot the product name, SKU, and unit selling price at checkout time, so future catalog price changes never distort past receipts.
- **Decimal Precision:** All financial calculations use Python's `Decimal` type to avoid floating-point inaccuracies.
- **Additive Migrations:** New cost and order-status columns are added without replacing existing rows. Before a file-backed database needs a schema migration, startup creates a unique, integrity-checked SQLite backup beside it. Existing orders default to `COMPLETED`; old cost values remain unknown (`NULL`).
- **Order Cancellation:** Restoring stock and changing order status happen in one `BEGIN IMMEDIATE` transaction. A cancelled order cannot be cancelled a second time.
- **CSV Safety:** Text values that spreadsheet software could interpret as formulas are escaped before export.

## 🗃️ Database and Backups

- The live database is `data\inventory.db`; tests use disposable temporary database files.
- Before a required schema migration, the app creates a unique backup named `inventory_pre_migration_<timestamp>.db` in `data`. It does not overwrite an earlier backup.
- A verified pre-enhancement copy is also present as `data\inventory_pre_enhancement_20261015_082525.db`.
- For a manual backup, close the application first, then copy `data\inventory.db` to a different dated filename. Keep backups outside folders that are automatically cleaned.
- Restore is manual: close the app, make a separate copy of the current database, then replace `data\inventory.db` with a known-good copy. Do not restore while the app is running.

## 🧰 Troubleshooting

- **Window appears minimized:** The app restores its main Tk window after the initial layout. If Windows still minimizes it, select it from the taskbar.
- **Python/Tkinter missing:** Install the Windows Python distribution with Tcl/Tk support, then retry `python main.py`.
- **Database locked:** Close other copies of the app and retry. Do not delete the database or its journal files while SQLite is active.
- **CSV export:** Choose a destination and filename in the Save dialog. Cancel closes the dialog without exporting.

## ⚠️ Current Scope Notes

- Products can be safely deactivated/reactivated; there is no permanent-delete action.
- Supplier records, payment processing/method tracking, order search by text, pagination, theme selection, in-app backup/restore, and a global all-screen search are not included.
- Profit estimates require cost prices. Existing orders have no recorded costs, so reports mark the estimate unavailable when any selected sale item is uncosted.
- The interface does not use background loading indicators; current SQLite operations are local and synchronous.
