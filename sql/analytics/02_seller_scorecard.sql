-- Business question: which sellers are driving the most delivery risk, and how do they rank?
-- Filters out very low-volume sellers (see config: min_orders_for_seller_analysis) so ranking isn't
-- dominated by a seller with 1 lucky/unlucky order.
SELECT
    s.seller_id,
    s.state AS seller_state,
    COUNT(*) AS order_count,
    ROUND(100.0 * SUM(CASE WHEN f.on_time_flag = 1 THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN f.on_time_flag IS NOT NULL THEN 1 ELSE 0 END), 0), 2) AS on_time_pct,
    ROUND(AVG(f.delivery_delay_days), 2) AS avg_delay_days,
    ROUND(AVG(f.review_score), 2) AS avg_review_score,
    RANK() OVER (ORDER BY
        100.0 * SUM(CASE WHEN f.on_time_flag = 1 THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN f.on_time_flag IS NOT NULL THEN 1 ELSE 0 END), 0) ASC
    ) AS worst_on_time_rank
FROM fact_orders f
JOIN dim_seller s ON f.seller_id = s.seller_id
WHERE f.n_sellers = 1   -- single-seller orders only, so blame is attributable
GROUP BY s.seller_id, s.state
HAVING COUNT(*) >= 5
ORDER BY on_time_pct ASC;
