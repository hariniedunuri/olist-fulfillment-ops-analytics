"""
Stage 1: Ingestion.
Loads the 9 raw Olist CSVs into `raw_*` tables in SQLite, preserving raw
values as-is (no cleaning here) so validation runs against true source data.
"""
import os
import sys
import pandas as pd
from db import get_conn

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

TABLE_FILE_MAP = {
    "raw_orders": "olist_orders_dataset.csv",
    "raw_order_items": "olist_order_items_dataset.csv",
    "raw_order_payments": "olist_order_payments_dataset.csv",
    "raw_order_reviews": "olist_order_reviews_dataset.csv",
    "raw_customers": "olist_customers_dataset.csv",
    "raw_sellers": "olist_sellers_dataset.csv",
    "raw_products": "olist_products_dataset.csv",
    "raw_geolocation": "olist_geolocation_dataset.csv",
    "raw_category_translation": "product_category_name_translation.csv",
}


def ingest_all(raw_dir=RAW_DIR, verbose=True):
    conn = get_conn()
    summary = {}
    for table, filename in TABLE_FILE_MAP.items():
        path = os.path.join(raw_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing raw source file: {path}")
        df = pd.read_csv(path)
        df.to_sql(table, conn, if_exists="replace", index=False)
        summary[table] = len(df)
        if verbose:
            print(f"[ingest] {table:28s} <- {filename:40s} {len(df):>8,} rows")
    conn.commit()
    conn.close()
    return summary


if __name__ == "__main__":
    result = ingest_all()
    total = sum(result.values())
    print(f"\n[ingest] Done. {len(result)} tables loaded, {total:,} total raw rows.")
