"""
Stage 3 & 4: Transform + Load.
Cleans raw data, applies documented business rules for known data-quality
issues, derives SLA/delay fields, and loads a star schema:
  dim_customer, dim_seller, dim_product, dim_date, dim_geography,
  fact_orders (grain: one row per order), fact_order_items (grain: one row per line item).
"""
import pandas as pd
import numpy as np
from db import get_conn

TS_COLS = [
    "order_purchase_timestamp", "order_approved_at",
    "order_delivered_carrier_date", "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def load_raw(conn):
    orders = pd.read_sql("SELECT * FROM raw_orders", conn)
    items = pd.read_sql("SELECT * FROM raw_order_items", conn)
    payments = pd.read_sql("SELECT * FROM raw_order_payments", conn)
    reviews = pd.read_sql("SELECT * FROM raw_order_reviews", conn)
    customers = pd.read_sql("SELECT * FROM raw_customers", conn)
    sellers = pd.read_sql("SELECT * FROM raw_sellers", conn)
    products = pd.read_sql("SELECT * FROM raw_products", conn)
    geoloc = pd.read_sql("SELECT * FROM raw_geolocation", conn)
    cat_translation = pd.read_sql("SELECT * FROM raw_category_translation", conn)
    return orders, items, payments, reviews, customers, sellers, products, geoloc, cat_translation


def build_dim_date(orders):
    all_dates = pd.to_datetime(orders["order_purchase_timestamp"]).dt.date
    date_range = pd.date_range(all_dates.min(), all_dates.max(), freq="D")
    dim_date = pd.DataFrame({"full_date": date_range})
    dim_date["date_key"] = dim_date["full_date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["year"] = dim_date["full_date"].dt.year
    dim_date["month"] = dim_date["full_date"].dt.month
    dim_date["quarter"] = dim_date["full_date"].dt.quarter
    dim_date["day_of_week"] = dim_date["full_date"].dt.day_name()
    dim_date["is_weekend"] = dim_date["full_date"].dt.dayofweek >= 5
    dim_date["year_month"] = dim_date["full_date"].dt.strftime("%Y-%m")
    dim_date = dim_date[["date_key", "full_date", "year", "month", "quarter",
                          "day_of_week", "is_weekend", "year_month"]]
    return dim_date


def build_dim_geography(geoloc):
    # raw geoloc has multiple lat/lng rows per zip prefix, some clearly bad geocodes.
    # using median instead of mean so a couple outlier points don't drag the location off
    g = geoloc.rename(columns={
        "geolocation_zip_code_prefix": "zip_prefix",
        "geolocation_lat": "lat",
        "geolocation_lng": "lng",
        "geolocation_city": "city",
        "geolocation_state": "state",
    })
    agg = g.groupby("zip_prefix").agg(
        lat=("lat", "median"),
        lng=("lng", "median"),
        city=("city", lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0]),
        state=("state", lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0]),
    ).reset_index()
    return agg


def build_dim_customer(customers):
    d = customers.rename(columns={
        "customer_zip_code_prefix": "zip_prefix",
        "customer_city": "city",
        "customer_state": "state",
    })[["customer_id", "customer_unique_id", "zip_prefix", "city", "state"]]
    return d


def build_dim_seller(sellers):
    d = sellers.rename(columns={
        "seller_zip_code_prefix": "zip_prefix",
        "seller_city": "city",
        "seller_state": "state",
    })[["seller_id", "zip_prefix", "city", "state"]]
    return d


def build_dim_product(products, cat_translation):
    p = products.merge(cat_translation, on="product_category_name", how="left")
    p["category_en"] = p["product_category_name_english"].fillna(
        p["product_category_name"]).fillna("unknown")
    d = p[["product_id", "category_en", "product_weight_g",
           "product_length_cm", "product_height_cm", "product_width_cm",
           "product_photos_qty"]].rename(columns={"category_en": "category"})
    return d


def build_fact_order_items(items):
    d = items.rename(columns={"order_item_id": "item_number"}).copy()
    d = d.drop_duplicates(subset=["order_id", "item_number"])
    d["order_item_id"] = d["order_id"] + "-" + d["item_number"].astype(str)
    return d[["order_item_id", "order_id", "item_number", "product_id",
              "seller_id", "price", "freight_value", "shipping_limit_date"]]


def build_fact_orders(orders, items, payments, reviews):
    o = orders.copy()
    for c in TS_COLS:
        o[c] = pd.to_datetime(o[c], errors="coerce")

    # 23 orders have delivered_customer before delivered_carrier, which isn't physically
    # possible -- bad timestamps somewhere upstream. Flagging instead of just dropping the
    # rows, then excluding them from delay math only (they stay in the dataset otherwise)
    o["timestamp_anomaly_flag"] = (
        o["order_delivered_customer_date"].notna()
        & o["order_delivered_carrier_date"].notna()
        & (o["order_delivered_customer_date"] < o["order_delivered_carrier_date"])
    )

    item_agg = items.groupby("order_id").agg(
        item_count=("order_item_id", "count"),
        total_price=("price", "sum"),
        total_freight=("freight_value", "sum"),
        n_sellers=("seller_id", "nunique"),
        primary_seller_id=("seller_id", lambda s: s.value_counts().idxmax()),
    ).reset_index()

    pay_agg = payments.groupby("order_id").agg(
        payment_value=("payment_value", "sum"),
        payment_installments=("payment_installments", "max"),
        payment_type=("payment_type", lambda s: s.value_counts().idxmax() if len(s) else None),
    ).reset_index()

    rev_agg = reviews.groupby("order_id").agg(
        review_score=("review_score", "mean"),
    ).reset_index()

    f = o.merge(item_agg, on="order_id", how="left") \
         .merge(pay_agg, on="order_id", how="left") \
         .merge(rev_agg, on="order_id", how="left")

    valid_delivery = f["order_delivered_customer_date"].notna() & ~f["timestamp_anomaly_flag"]

    f["delivery_delay_days"] = np.where(
        valid_delivery,
        (f["order_delivered_customer_date"] - f["order_estimated_delivery_date"]).dt.total_seconds() / 86400,
        np.nan,
    )
    f["on_time_flag"] = np.where(valid_delivery, f["delivery_delay_days"] <= 0, np.nan)

    f["processing_days"] = np.where(
        f["order_approved_at"].notna(),
        (f["order_approved_at"] - f["order_purchase_timestamp"]).dt.total_seconds() / 86400,
        np.nan,
    )
    f["shipping_days"] = np.where(
        valid_delivery & f["order_delivered_carrier_date"].notna(),
        (f["order_delivered_customer_date"] - f["order_delivered_carrier_date"]).dt.total_seconds() / 86400,
        np.nan,
    )
    f["carrier_pickup_days"] = np.where(
        f["order_delivered_carrier_date"].notna() & f["order_approved_at"].notna(),
        (f["order_delivered_carrier_date"] - f["order_approved_at"]).dt.total_seconds() / 86400,
        np.nan,
    )

    f["date_key"] = f["order_purchase_timestamp"].dt.strftime("%Y%m%d").astype("Int64")

    keep = [
        "order_id", "customer_id", "primary_seller_id", "order_status", "date_key",
        "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date",
        "item_count", "n_sellers", "total_price", "total_freight",
        "payment_value", "payment_installments", "payment_type", "review_score",
        "processing_days", "carrier_pickup_days", "shipping_days",
        "delivery_delay_days", "on_time_flag", "timestamp_anomaly_flag",
    ]
    f = f.rename(columns={"primary_seller_id": "seller_id"})
    keep = [c.replace("primary_seller_id", "seller_id") for c in keep]
    return f[keep]


def run_transform_load(conn=None, verbose=True):
    own_conn = conn is None
    conn = conn or get_conn()

    orders, items, payments, reviews, customers, sellers, products, geoloc, cat_translation = load_raw(conn)

    dim_date = build_dim_date(orders)
    dim_geography = build_dim_geography(geoloc)
    dim_customer = build_dim_customer(customers)
    dim_seller = build_dim_seller(sellers)
    dim_product = build_dim_product(products, cat_translation)
    fact_order_items = build_fact_order_items(items)
    fact_orders = build_fact_orders(orders, items, payments, reviews)

    tables = {
        "dim_date": dim_date,
        "dim_geography": dim_geography,
        "dim_customer": dim_customer,
        "dim_seller": dim_seller,
        "dim_product": dim_product,
        "fact_order_items": fact_order_items,
        "fact_orders": fact_orders,
    }
    for name, df in tables.items():
        df.to_sql(name, conn, if_exists="replace", index=False)
        if verbose:
            print(f"[transform_load] {name:20s} -> {len(df):>8,} rows, {df.shape[1]} cols")

    conn.commit()
    if own_conn:
        conn.close()
    return tables


if __name__ == "__main__":
    run_transform_load()
