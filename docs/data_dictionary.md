# Data Dictionary

## fact_orders (grain: one row per order_id)

| Column | Type | Meaning |
|---|---|---|
| order_id | TEXT PK | Unique order identifier |
| customer_id | TEXT FK -> dim_customer | |
| seller_id | TEXT FK -> dim_seller | Primary seller on the order (see n_sellers) |
| order_status | TEXT | delivered / shipped / canceled / etc. |
| date_key | INT FK -> dim_date | Order purchase date |
| order_purchase_timestamp | TEXT | |
| order_approved_at | TEXT | Payment approval timestamp |
| order_delivered_carrier_date | TEXT | Handoff to carrier |
| order_delivered_customer_date | TEXT | Actual delivery to customer |
| order_estimated_delivery_date | TEXT | Promised delivery date shown to customer |
| item_count | INT | Number of line items on the order |
| n_sellers | INT | Distinct sellers on the order (>1 = multi-seller; excluded from seller-attribution analyses) |
| total_price, total_freight | REAL | Summed from fact_order_items |
| payment_value, payment_installments, payment_type | | Summed/aggregated from payments |
| review_score | REAL | Mean of review scores for the order |
| processing_days | REAL | purchase -> approval |
| carrier_pickup_days | REAL | approval -> carrier handoff |
| shipping_days | REAL | carrier handoff -> customer delivery |
| delivery_delay_days | REAL | actual delivery - estimated delivery (negative = early). NULL if undelivered or timestamp_anomaly_flag=1 |
| on_time_flag | INT (0/1/NULL) | delivery_delay_days <= 0 |
| timestamp_anomaly_flag | INT | 1 if source timestamps were physically inconsistent (see docs/architecture.md) |

## fact_order_items (grain: one row per order line item)

order_item_id (PK), order_id, item_number, product_id, seller_id, price, freight_value, shipping_limit_date.

## Dimensions

- **dim_customer**: customer_id (PK), customer_unique_id, zip_prefix, city, state
- **dim_seller**: seller_id (PK), zip_prefix, city, state
- **dim_product**: product_id (PK), category (English, translated), weight/dimensions, photo count
- **dim_date**: date_key (PK, YYYYMMDD), full_date, year, month, quarter, day_of_week, is_weekend, year_month
- **dim_geography**: zip_prefix (PK), lat/lng (median of raw multi-row geolocation data), city, state

## Known data-quality issues (documented, not hidden)

- 1,359 orders: carrier-handoff timestamp precedes approval timestamp.
- 23 orders: customer-delivery timestamp precedes carrier-handoff timestamp (excluded from delay math via timestamp_anomaly_flag).
- 8 orders marked `delivered` with no delivered_customer_date.
- Raw geolocation data has multiple lat/lng rows per zip_prefix; deduplicated to one row via median (documented in etl/transform_load.py).
