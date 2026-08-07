-- Business question: which sellers are anomalous THIS month vs. their own rolling baseline?
-- Method: for each seller-month, compare avg delay to that seller's trailing 3-month average
-- (excluding the current month) and flag deviations beyond a threshold (config: anomaly_zscore_threshold
-- approximated here with a simple deviation-from-rolling-mean rule, computed in Python for the
-- z-score version — see analysis/anomaly_detection.py for the statistically rigorous version).
WITH seller_month AS (
    SELECT
        f.seller_id,
        d.year_month,
        COUNT(*) AS order_count,
        AVG(f.delivery_delay_days) AS avg_delay_days
    FROM fact_orders f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE f.n_sellers = 1 AND f.delivery_delay_days IS NOT NULL
    GROUP BY f.seller_id, d.year_month
    HAVING COUNT(*) >= 3
),
with_baseline AS (
    SELECT
        *,
        AVG(avg_delay_days) OVER (
            PARTITION BY seller_id ORDER BY year_month
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ) AS rolling_baseline_delay
    FROM seller_month
)
SELECT
    seller_id, year_month, order_count,
    ROUND(avg_delay_days, 2) AS avg_delay_days,
    ROUND(rolling_baseline_delay, 2) AS rolling_baseline_delay,
    ROUND(avg_delay_days - rolling_baseline_delay, 2) AS delay_deviation
FROM with_baseline
WHERE rolling_baseline_delay IS NOT NULL
  AND (avg_delay_days - rolling_baseline_delay) > 2.0
ORDER BY delay_deviation DESC;
