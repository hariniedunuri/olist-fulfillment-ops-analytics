-- Pure-SQL versions of the core data-quality checks (mirrors etl/validate.py logic,
-- provided here for portability / running directly against the warehouse).

-- Referential integrity: fact_orders -> dim_customer
SELECT COUNT(*) AS orphaned_customer_fk
FROM fact_orders f LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- Referential integrity: fact_order_items -> dim_product
SELECT COUNT(*) AS orphaned_product_fk
FROM fact_order_items f LEFT JOIN dim_product p ON f.product_id = p.product_id
WHERE p.product_id IS NULL;

-- Range check: delivery_delay_days within a sane bound (catches data errors, not just slow orders)
SELECT COUNT(*) AS extreme_delay_outliers
FROM fact_orders
WHERE delivery_delay_days IS NOT NULL AND ABS(delivery_delay_days) > 200;

-- Business rule: on_time_flag must be consistent with delivery_delay_days sign
SELECT COUNT(*) AS inconsistent_on_time_flag
FROM fact_orders
WHERE delivery_delay_days IS NOT NULL
  AND ((on_time_flag = 1 AND delivery_delay_days > 0)
    OR (on_time_flag = 0 AND delivery_delay_days <= 0));

-- Duplicate check: fact_orders PK
SELECT COUNT(*) AS duplicate_order_pk
FROM (SELECT order_id FROM fact_orders GROUP BY order_id HAVING COUNT(*) > 1);
