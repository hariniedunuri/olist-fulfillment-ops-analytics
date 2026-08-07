"""
Simple monthly order-volume forecast to support fulfillment capacity planning.
Uses Holt-Winters exponential smoothing (statsmodels) — deliberately simple and
explainable rather than a black-box model, appropriate for ~2 years of monthly data.
"""
import os
import sys
import warnings
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))
from db import get_conn  # noqa: E402

warnings.filterwarnings("ignore")


def monthly_volume(conn=None):
    own = conn is None
    conn = conn or get_conn()
    df = pd.read_sql("""
        SELECT d.year_month, COUNT(*) AS order_count
        FROM fact_orders f JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY d.year_month ORDER BY d.year_month
    """, conn)
    if own:
        conn.close()
    return df


def forecast_next_n_months(n=3):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    df = monthly_volume()
    # Documented, inspected trim (not a blind positional slice):
    # - 2016-09 through 2016-12 are the store's launch ramp-up (a handful of orders/month) --
    #   not representative of steady-state demand.
    # - 2018-09 and 2018-10 are partial/truncated months in the raw extract (16 and 4 orders) --
    #   including them would make the model think demand collapsed.
    # Stable window used for the model: 2017-01 through 2018-08.
    series = df.set_index("year_month")["order_count"]
    series = series.loc["2017-01":"2018-08"]
    series.index = pd.PeriodIndex(series.index, freq="M").to_timestamp()

    model = ExponentialSmoothing(series, trend="add", seasonal=None)
    fit = model.fit()
    forecast = fit.forecast(n)

    result = pd.DataFrame({
        "year_month": forecast.index.strftime("%Y-%m"),
        "forecasted_order_count": forecast.values.round(0).astype(int),
    })
    return series, result


if __name__ == "__main__":
    history, forecast = forecast_next_n_months(3)
    print("=== Historical monthly order volume (trimmed) ===")
    print(history.tail(6))
    print("\n=== 3-month forward forecast ===")
    print(forecast.to_string(index=False))
