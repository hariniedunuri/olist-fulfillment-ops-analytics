# Order Fulfillment & Delivery Performance Operations Analytics Platform

An end-to-end operational analytics platform that monitors e-commerce order fulfillment, detects delivery-SLA anomalies by seller and region, localizes root causes, forecasts order volume for capacity planning, and uses a lightweight rules-based AI agent to draft human-reviewed root-cause summaries — built on 99,441 real orders from the Olist Brazilian E-Commerce dataset.

Built as a project submission for a Data Analyst role: designed to demonstrate SQL, Python, data modeling, ETL, data quality, automation, operational analytics, testing, and an AI-enabled workflow applied to a real operational business problem — not a single-notebook Kaggle exercise.

## Business problem

Marketplace operations teams need to know, continuously, which sellers and regions are failing to meet delivery commitments, why, and where to intervene first. This project builds that workflow end to end: raw order data -> validated, modeled data -> SQL/Python analytics -> statistical anomaly detection -> an AI-assisted root-cause draft -> a decision-focused dashboard -> evidence-backed recommendations.

## Key findings (from a real run — see `reports/findings_and_recommendations.md` for full detail)

- **Overall on-time delivery rate: 91.9%** across 96,478 delivered orders with a computable SLA outcome, but the monthly rate swings from 78.6% to 98.6% — volatile, not stable.
- **135 of 1,217 evaluated sellers (11%)** are statistically anomalous on delivery delay (z-score >= 1.5 vs. the seller population); risk is concentrated in a small subset of sellers, not spread evenly.
- Brazil's North/Northeast states (AL, MA, PI, CE, SE) have the worst on-time rates (76-85%) and the longest shipping-stage duration (16-21 days) — a geographic, not seller-quality, driver.
- Delivery delay is negatively correlated with review score (r = -0.267); payment installments and freight value show negligible correlation with delay.
- A 3-month Holt-Winters forecast on stabilized volume projects ~5,800-6,200 orders/month — roughly flat, not a capacity-scaling signal.

## Architecture

```
Raw CSVs -> Ingestion -> Raw-layer Validation -> Transform/Load -> Star Schema (SQLite)
   -> Modeled-layer Validation -> SQL Analytics Layer -> Dashboard (Streamlit)
   -> Automated Pipeline (orchestration/run_pipeline.py) -> Data-Quality Report
   -> Ops Insight Agent (anomaly -> SQL retrieval -> root-cause draft -> groundedness check)
```

Full architecture detail in `docs/architecture.md`; data dictionary in `docs/data_dictionary.md`.

## Dataset

[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — 99,441 real orders, 2016-2018, 9 relational tables (orders, order items, payments, reviews, customers, sellers, products, geolocation, category translation). Genuine referential-integrity and timestamp data-quality issues exist in this data and are documented and handled (not hidden) in `etl/validate.py` and `docs/data_dictionary.md`.

## Data model

Star schema: `fact_orders` (grain: one row per order — Olist delivery timestamps are order-level, not item-level, a deliberate modeling decision explained in `docs/architecture.md`) and `fact_order_items` (grain: one row per line item), joined to `dim_customer`, `dim_seller`, `dim_product`, `dim_date`, `dim_geography`.

## What's in this repo

| Folder | Contents |
|---|---|
| `etl/` | `ingest.py`, `validate.py`, `transform_load.py`, `validate_modeled.py`, `db.py` |
| `sql/ddl/` | Star-schema DDL (`schema.sql`) |
| `sql/analytics/` | 6 KPI/anomaly/root-cause SQL queries, each documenting the business question it answers |
| `sql/data_quality/` | Pure-SQL data-quality checks |
| `sql/run_analytics.py` | Executes the .sql files above against the live db — the dashboard, agent, and tests all import this, so there's no drift between the SQL in the repo and the SQL actually run |
| `analysis/` | `delay_analysis.py` (IQR + z-score anomaly detection, correlations), `forecast.py` (Holt-Winters volume forecast), `01_exploration.ipynb` (executed notebook) |
| `agent/` | `ops_insight_agent.py` — rules-based Ops Insight Agent |
| `dashboard/` | `streamlit_app.py` — operational dashboard |
| `orchestration/` | `run_pipeline.py` — automated, idempotent pipeline entrypoint with JSON run logging |
| `tests/` | 18 pytest tests: ETL, data quality, SQL outputs, agent output |
| `reports/` | `findings_and_recommendations.md` — real numbers, not placeholders |
| `docs/` | `architecture.md`, `data_dictionary.md` |

## How to run it

```bash
git clone <repo-url>
cd olist-fulfillment-ops-analytics
pip install -r requirements.txt

# Download the 9 Olist CSVs from Kaggle into data/raw/ — see data/raw/README.md
python orchestration/run_pipeline.py    # ingest -> validate -> transform -> validate (idempotent)

pytest -v                                # 18 tests, all should pass
streamlit run dashboard/streamlit_app.py # opens the operational dashboard
python agent/ops_insight_agent.py        # runs the Ops Insight Agent on top-5 flagged sellers
jupyter execute analysis/01_exploration.ipynb  # re-run the exploration notebook
```

## Business recommendations

1. **Prioritize the ~135 statistically anomalous sellers for a performance review**, starting with the worst z-scores — this is a concentrated risk, not a broad one. Root cause for the top offenders localizes to the shipping stage (carrier-related), not order processing — see agent output.
2. **Set region-specific delivery-date expectations for AL/MA/PI/CE/SE**, or invest in regional carrier/fulfillment partnerships — these states show 16-21 day shipping stages vs. a national average well below that.
3. **Frame delivery-time improvement as a customer-satisfaction initiative**, not just an ops metric — the -0.267 correlation with review score makes the business case executive-legible.
4. **No urgent capacity scale-up is indicated by volume forecast alone** — near-term planning attention is better spent on the seller/region concentration issues above.

Full evidence trail for each recommendation is in `reports/findings_and_recommendations.md`.

## Tech stack and why

- **Python + SQL (SQLite)** — core ETL and analytics. SQLite was chosen deliberately over Postgres/Snowflake for this submission: at ~370K modeled rows, it needs zero setup, is a single portable file, and every SQL query is standard enough to port to a warehouse with only a connection-string change (see `docs/architecture.md`).
- **No PySpark/Kafka/Flink/EKS/EMR in this submission** — explicitly not claimed. At this data volume they'd add complexity without a real performance justification; see `docs/architecture.md` for the honest "when I'd reach for these" discussion instead of forced, unexplainable usage.
- **Streamlit** — dashboard lives in the same codebase as the pipeline, runs from one command.
- **Rules-based Ops Insight Agent** — a deliberately deterministic, fully explainable multi-step agent (retrieve -> classify -> draft -> validate-groundedness) rather than an LLM call, for this submission. The LLM-upgrade path is designed for (swap one function) and documented in `agent/ops_insight_agent.py`, not silently skipped.
- **pytest** — 18 tests covering ETL correctness, data-quality-check correctness (including a test that the groundedness validator actually catches fabricated numbers), SQL output sanity, and agent output.

## Testing

`pytest -v` — 18 tests across `tests/test_etl.py`, `tests/test_data_quality.py`, `tests/test_sql_outputs.py`, `tests/test_agent_output.py`. All pass against a full pipeline run.

## Limitations and future work

- Batch pipeline (not streaming); a Kafka/Flink-based near-real-time version is a natural extension, not implemented here.
- Forecast model is intentionally simple (Holt-Winters exponential smoothing, no seasonality term given ~20 months of history); a production version would backtest multiple models.
- Agent is a single-step retrieval + reasoning loop, not a multi-tool autonomous agent, and is rules-based rather than LLM-backed in this submission — scoped intentionally for reliability, zero external dependency, and full explainability within the project timeline.
