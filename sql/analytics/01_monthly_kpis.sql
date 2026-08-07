-- Business question: Is on-time delivery performance improving or degrading month over month?
SELECT
    d.year_month,
    COUNT(*)                                                   AS total_orders,
    SUM(CASE WHEN f.order_status = 'delivered' THEN 1 ELSE 0 END)        AS delivered_orders,
    ROUND(100.0 * SUM(CASE WHEN f.on_time_flag = 1 THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN f.on_time_flag IS NOT NULL THEN 1 ELSE 0 END), 0), 2) AS on_time_pct,
    ROUND(AVG(f.delivery_delay_days), 2)                        AS avg_delay_days,
    ROUND(AVG(f.review_score), 2)                               AS avg_review_score,
    ROUND(SUM(f.payment_value), 2)                              AS total_revenue
FROM fact_orders f
JOIN dim_date d ON f.date_key = d.date_key
GROUP BY d.year_month
ORDER BY d.year_month;
