# Architecture

```
Raw CSVs (9 Olist tables)
      |
      v
[etl/ingest.py]        --> raw_* tables in SQLite (data/processed/olist.db), values untouched
      |
      v
[etl/validate.py]      --> data-quality checks against RAW layer (12 checks: null, duplicate,
      |                     range, referential integrity, business-rule, schema, freshness)
      v
[etl/transform_load.py]--> cleans, deduplicates, derives SLA fields, builds star schema:
      |                     dim_date, dim_geography, dim_customer, dim_seller, dim_product,
      |                     fact_orders (grain: 1 row/order), fact_order_items (grain: 1 row/line item)
      v
[etl/validate_modeled.py] --> data-quality checks against MODELED layer (7 checks) -- catches
      |                        issues introduced by the transform step itself
      v
[sql/analytics/*.sql]  --> KPI, seller scorecard, state performance, anomaly detection,
      |                     root-cause breakdown, payment-vs-outcome views
      |
      +--> [analysis/delay_analysis.py]  statistical outlier + z-score anomaly detection
      +--> [analysis/forecast.py]        Holt-Winters order-volume forecast
      +--> [agent/ops_insight_agent.py]  rules-based root-cause narrative agent (see below)
      |
      v
[dashboard/streamlit_app.py] --> operational dashboard (KPIs, trends, scorecard, anomaly
                                   panel with agent integration, forecast, data-health panel)

[orchestration/run_pipeline.py] --> automation entrypoint: runs ingest -> validate -> transform
                                     -> validate_modeled end-to-end, idempotently, with a
                                     JSON run log (data/processed/pipeline_runs.log). Intended
                                     to be triggered by cron or an Airflow DAG on a schedule.
```

## Key architecture decisions and why

- **SQLite, not Postgres/Snowflake.** At ~1.5M raw rows / ~370K modeled rows, SQLite is the right-sized choice: zero setup, single portable file, full SQL (CTEs, window functions) support. The star schema and every query in `sql/` are standard ANSI-ish SQL that would port to Postgres/Snowflake with no logic changes -- only the connection layer (`etl/db.py`) would change.
- **fact_orders grain is one row per order, not per line item.** Olist's delivery timestamps are recorded at the order level, not per item, so an item-grain fact table would either duplicate delivery data across items or require an arbitrary allocation rule. `fact_order_items` exists separately for item/product-level analysis (pricing, category mix) where that grain is the correct one. This is a deliberate data-modeling decision, documented here rather than defaulted into.
- **No PySpark in the delivered version.** At this data volume, Spark adds operational complexity without a performance justification. Documented explicitly (not silently omitted) as a "would use it at 100M+ rows" judgment call -- see README "Tech stack and why".
- **No streaming (Kafka/Flink).** This is a batch, daily/on-demand analytics use case; a streaming version is out of scope and noted as future work, not implemented as a stub.
- **Ops Insight Agent is rules-based, not an LLM call, in this submission.** See `agent/ops_insight_agent.py` module docstring for the full reasoning -- it's a deliberate reliability/explainability choice, with the LLM upgrade path (swap `draft_narrative()`) documented rather than hand-waved.
