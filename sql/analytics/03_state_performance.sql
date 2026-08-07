-- Business question: where geographically is delivery risk concentrated?
SELECT
    c.state AS customer_state,
    COUNT(*) AS order_count,
    ROUND(100.0 * SUM(CASE WHEN f.on_time_flag = 1 THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN f.on_time_flag IS NOT NULL THEN 1 ELSE 0 END), 0), 2) AS on_time_pct,
    ROUND(AVG(f.delivery_delay_days), 2) AS avg_delay_days,
    ROUND(AVG(f.shipping_days), 2) AS avg_shipping_days
FROM fact_orders f
JOIN dim_customer c ON f.customer_id = c.customer_id
GROUP BY c.state
HAVING COUNT(*) >= 20
ORDER BY on_time_pct ASC;
