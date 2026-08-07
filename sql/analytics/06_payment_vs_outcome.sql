-- Business question: does payment method/installment count relate to delay or satisfaction?
SELECT
    payment_type,
    CASE
        WHEN payment_installments <= 1 THEN '1'
        WHEN payment_installments <= 3 THEN '2-3'
        WHEN payment_installments <= 6 THEN '4-6'
        ELSE '7+'
    END AS installments_bucket,
    COUNT(*) AS order_count,
    ROUND(AVG(delivery_delay_days), 2) AS avg_delay_days,
    ROUND(AVG(review_score), 2) AS avg_review_score
FROM fact_orders
WHERE payment_type IS NOT NULL
GROUP BY payment_type, installments_bucket
ORDER BY order_count DESC;
