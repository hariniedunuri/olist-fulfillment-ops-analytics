-- Star schema for the Order Fulfillment & Delivery Performance analytics platform.
-- Grain of fact_orders: one row per order.
-- Grain of fact_order_items: one row per order line item.
-- (Tables are materialized by etl/transform_load.py; this file documents the
--  contract and is also runnable standalone against a fresh SQLite db.)

CREATE TABLE IF NOT EXISTS dim_date (
    date_key      INTEGER PRIMARY KEY,   -- YYYYMMDD
    full_date     TEXT NOT NULL,
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    quarter       INTEGER NOT NULL,
    day_of_week   TEXT NOT NULL,
    is_weekend    INTEGER NOT NULL,
    year_month    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_geography (
    zip_prefix    INTEGER PRIMARY KEY,
    lat           REAL,
    lng           REAL,
    city          TEXT,
    state         TEXT
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id        TEXT PRIMARY KEY,
    customer_unique_id TEXT,
    zip_prefix         INTEGER,
    city               TEXT,
    state              TEXT
);

CREATE TABLE IF NOT EXISTS dim_seller (
    seller_id     TEXT PRIMARY KEY,
    zip_prefix    INTEGER,
    city          TEXT,
    state         TEXT
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_id          TEXT PRIMARY KEY,
    category            TEXT,
    product_weight_g    REAL,
    product_length_cm   REAL,
    product_height_cm   REAL,
    product_width_cm    REAL,
    product_photos_qty  REAL
);

CREATE TABLE IF NOT EXISTS fact_order_items (
    order_item_id       TEXT PRIMARY KEY,
    order_id             TEXT NOT NULL,
    item_number          INTEGER NOT NULL,
    product_id           TEXT REFERENCES dim_product(product_id),
    seller_id            TEXT REFERENCES dim_seller(seller_id),
    price                 REAL,
    freight_value         REAL,
    shipping_limit_date   TEXT
);

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id                       TEXT PRIMARY KEY,
    customer_id                    TEXT REFERENCES dim_customer(customer_id),
    seller_id                      TEXT REFERENCES dim_seller(seller_id),  -- primary seller on the order
    order_status                   TEXT,
    date_key                       INTEGER REFERENCES dim_date(date_key), -- purchase date
    order_purchase_timestamp       TEXT,
    order_approved_at              TEXT,
    order_delivered_carrier_date   TEXT,
    order_delivered_customer_date  TEXT,
    order_estimated_delivery_date  TEXT,
    item_count                     INTEGER,
    n_sellers                      INTEGER,      -- >1 means multi-seller order
    total_price                    REAL,
    total_freight                  REAL,
    payment_value                  REAL,
    payment_installments           INTEGER,
    payment_type                   TEXT,
    review_score                   REAL,
    processing_days                REAL,         -- purchase -> approved
    carrier_pickup_days            REAL,         -- approved -> carrier
    shipping_days                  REAL,         -- carrier -> customer
    delivery_delay_days            REAL,         -- actual - estimated (NULL if undelivered/anomalous ts)
    on_time_flag                   INTEGER,       -- 1/0/NULL
    timestamp_anomaly_flag         INTEGER        -- 1 if source timestamps were physically inconsistent
);

CREATE TABLE IF NOT EXISTS data_quality_results (
    check_name   TEXT,
    category     TEXT,
    passed       INTEGER,
    detail       TEXT,
    run_ts       TEXT
);
