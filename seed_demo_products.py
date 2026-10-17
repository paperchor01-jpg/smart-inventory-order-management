"""Explicit command for adding marked hackathon demo products."""
import argparse

import database
from services.inventory_service import seed_demo_products


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add marked demo products only if the selected catalog is empty."
    )
    parser.add_argument(
        "--db", metavar="PATH", help="SQLite database path (defaults to data/inventory.db)."
    )
    args = parser.parse_args()

    # Match normal application startup and support an alternate database for demos.
    database.init_db(args.db)
    result = seed_demo_products(args.db)
    if result["seeded"]:
        print(f"Added {result['inserted_count']} clearly marked demo products.")
        print("They are identified by [DEMO] names and DEMO- SKUs.")
    else:
        print(
            "No products added: the catalog already contains "
            f"{result['existing_product_count']} product(s)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
