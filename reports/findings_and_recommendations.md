# Findings & Business Recommendations

*Generated from a real run of the pipeline against the Olist Brazilian E-Commerce dataset (99,441 orders, 2016-09 through 2018-10, with the two trailing partial months excluded from trend/forecast analysis).*

## Headline metrics

- **Overall on-time delivery rate (delivered orders): 91.9%** — average delivery delay of -11.2 days relative to the estimated delivery date (i.e., on average, orders arrive ~11 days *before* the promised date — Olist's estimated delivery dates carry significant built-in buffer).
- On-time performance is volatile month to month (78.6% in March 2018 vs. 98.6% in June 2018), not a stable trend — worth monitoring, not assuming steady-state.
- **135 of 1,217 evaluated sellers (11%)** are statistically anomalous (|z-score| ≥ 1.5) on average delivery delay relative to the seller population.

## Finding 1 — Delivery risk is geographically concentrated in Brazil's North/Northeast

States AL, MA, PI, CE, and SE have the worst on-time rates (76–85%) and the highest average shipping-stage duration (16–21 days), well above the national average. This lines up with geographic distance from São Paulo, where the large majority of sellers are based.

**Evidence:** `sql/analytics/03_state_performance.sql` — state-level on-time % and avg_shipping_days.

**Recommendation:** For orders shipping to AL/MA/PI/CE/SE, either set more accurate (later) estimated delivery dates for those regions specifically, or evaluate regional fulfillment/carrier partnerships to cut the ~17-21 day shipping-stage duration. Setting expectations accurately is the faster fix; improving actual transit time is the higher-value one.

## Finding 2 — A small number of sellers account for a disproportionate share of severe, statistically anomalous delay

135 sellers are flagged anomalous by z-score; the worst (z=5.83) averages 10.3 days of delay against a population mean near zero, concentrated specifically in the shipping stage (29.9 avg days) rather than processing.

**Evidence:** `analysis/delay_analysis.py::seller_zscore_anomalies`, cross-checked against `agent/ops_insight_agent.py` root-cause breakdowns for the top 5.

**Recommendation:** Prioritize a seller performance review for the top 10-15 anomalous sellers by z-score before addressing the broader seller base — this is a Pareto-style concentration of risk, not a uniform problem.

## Finding 3 — Delivery delay is meaningfully (negatively) correlated with customer review score

`delay_vs_review_corr = -0.267` — a moderate negative correlation: as delay increases, review scores drop. Payment installments and freight value show negligible correlation with delay (-0.032 and -0.051), so payment structure is not a meaningful lever here.

**Evidence:** `analysis/delay_analysis.py::payment_delay_correlation`.

**Recommendation:** Treat on-time delivery as a customer-satisfaction lever, not just an ops metric — a delay-reduction initiative should be expected to move review scores, which is a more executive-legible framing than "days late."

## Finding 4 — Order volume forecast supports flat-to-slightly-declining near-term capacity needs

Using a Holt-Winters model on the stable 2017-01–2018-08 window (excluding launch ramp-up and two truncated trailing months), the 3-month forward forecast is 6,191 / 5,997 / 5,803 orders/month — roughly flat to the most recent observed months, not a spike.

**Evidence:** `analysis/forecast.py`.

**Recommendation:** No urgent capacity scale-up signal from volume alone; capacity planning attention is better spent on the seller/region concentration issues above (Findings 1-2), which are the actual drivers of operational risk in this data.

## Data-quality caveat that affects all of the above

Two real source-data issues were found and documented (not hidden): 1,359 orders where the carrier-handoff timestamp precedes the approval timestamp, and 23 orders where the customer-delivery timestamp precedes the carrier-handoff timestamp. These 23 physically-impossible-timestamp orders are excluded from delay/SLA calculations (flagged via `timestamp_anomaly_flag`, not silently dropped from the dataset). 97.0% of orders have a computable SLA delay value; the rest are undelivered or excluded for the reason above.
