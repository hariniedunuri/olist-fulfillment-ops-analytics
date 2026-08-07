-- Given a flagged seller, localize WHERE in the fulfillment chain the delay originates:
-- processing (purchase->approval), carrier pickup (approval->carrier), or shipping (carrier->customer).
-- Parameterize seller_id at query time (:seller_id).
SELECT
    seller_id,
    COUNT(*) AS order_count,
    ROUND(AVG(processing_days), 2) AS avg_processing_days,
    ROUND(AVG(carrier_pickup_days), 2) AS avg_carrier_pickup_days,
    ROUND(AVG(shipping_days), 2) AS avg_shipping_days,
    ROUND(AVG(delivery_delay_days), 2) AS avg_delay_days
FROM fact_orders
WHERE seller_id = :seller_id AND n_sellers = 1
GROUP BY seller_id;
