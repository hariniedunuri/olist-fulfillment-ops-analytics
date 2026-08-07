"""
Python statistical analysis layer: outlier detection on delivery delay,
correlation checks, and a per-seller z-score anomaly view (more rigorous
than the flat 2-day SQL threshold — normalizes by each seller's own volatility).
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))
from db import get_conn  # noqa: E402


def load_fact_orders(conn=None):
    own = conn is None
    conn = conn or get_conn()
    df = pd.read_sql("SELECT * FROM fact_orders", conn)
    if own:
        conn.close()
    return df


def iqr_outliers(df, col="delivery_delay_days"):
    s = df[col].dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = df[(df[col] < lower) | (df[col] > upper)]
    return {
        "q1": q1, "q3": q3, "iqr": iqr, "lower_bound": lower, "upper_bound": upper,
        "n_outliers": len(outliers), "pct_outliers": round(100 * len(outliers) / len(s), 2),
    }, outliers


def seller_zscore_anomalies(df, min_orders=10, z_threshold=1.5):
    """Per-seller z-score of avg delay vs. the overall seller population —
    answers 'which sellers are statistically unusual', not just 'which are slow'."""
    single_seller = df[(df["n_sellers"] == 1) & df["delivery_delay_days"].notna()]
    agg = single_seller.groupby("seller_id").agg(
        order_count=("order_id", "count"),
        avg_delay=("delivery_delay_days", "mean"),
        avg_review=("review_score", "mean"),
    ).reset_index()
    agg = agg[agg["order_count"] >= min_orders]
    mu, sigma = agg["avg_delay"].mean(), agg["avg_delay"].std()
    agg["z_score"] = (agg["avg_delay"] - mu) / sigma
    agg["is_anomalous"] = agg["z_score"].abs() >= z_threshold
    return agg.sort_values("z_score", ascending=False)


def payment_delay_correlation(df):
    d = df.dropna(subset=["delivery_delay_days", "payment_installments", "total_freight", "review_score"])
    return {
        "installments_vs_delay_corr": round(d["payment_installments"].corr(d["delivery_delay_days"]), 3),
        "freight_vs_delay_corr": round(d["total_freight"].corr(d["delivery_delay_days"]), 3),
        "delay_vs_review_corr": round(d["delivery_delay_days"].corr(d["review_score"]), 3),
    }


def summary_report():
    df = load_fact_orders()
    outlier_stats, _ = iqr_outliers(df)
    anomalies = seller_zscore_anomalies(df)
    corr = payment_delay_correlation(df)

    print("=== Delivery Delay — IQR Outlier Analysis ===")
    for k, v in outlier_stats.items():
        print(f"  {k}: {v}")

    print(f"\n=== Seller Z-Score Anomalies (|z| >= 1.5, min 10 orders) ===")
    print(f"  Sellers evaluated: {len(anomalies)}")
    print(f"  Flagged anomalous: {anomalies['is_anomalous'].sum()}")
    print(anomalies.head(10).to_string(index=False))

    print(f"\n=== Correlations ===")
    for k, v in corr.items():
        print(f"  {k}: {v}")

    return {"outlier_stats": outlier_stats, "anomalies": anomalies, "correlations": corr}


if __name__ == "__main__":
    summary_report()
