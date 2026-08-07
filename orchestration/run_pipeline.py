"""
Automated pipeline entrypoint — this is what a scheduler (cron, Airflow, etc.)
would call on a recurring basis. Idempotent: safe to re-run, since each stage
does a full replace of its target tables rather than blind appends.

Usage:
    python orchestration/run_pipeline.py
    # or on a schedule, e.g. crontab: 0 6 * * * cd /path/to/repo && python orchestration/run_pipeline.py

A real deployment would wrap this in an Airflow DAG (one task per stage, with
retries/alerting on failure) -- see docs/architecture.md for that design.
"""
import os
import sys
import time
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "pipeline_runs.log")


def log(stage, status, detail=""):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        "detail": detail,
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[pipeline] {stage:20s} {status:8s} {detail}")


def main():
    start = time.time()
    try:
        from ingest import ingest_all
        t0 = time.time()
        summary = ingest_all(verbose=False)
        log("ingest", "OK", f"{sum(summary.values()):,} raw rows in {time.time()-t0:.1f}s")

        from validate import run_validation
        t0 = time.time()
        raw_dq = run_validation(verbose=False)
        n_flag = (raw_dq.passed == 0).sum()
        log("validate_raw", "OK", f"{len(raw_dq)} checks, {n_flag} flagged, {time.time()-t0:.1f}s")

        from transform_load import run_transform_load
        t0 = time.time()
        tables = run_transform_load(verbose=False)
        log("transform_load", "OK", f"{sum(len(v) for v in tables.values()):,} rows loaded, {time.time()-t0:.1f}s")

        from validate_modeled import run_modeled_validation
        t0 = time.time()
        modeled_dq = run_modeled_validation(verbose=False)
        n_fail = (modeled_dq.passed == 0).sum()
        status = "OK" if n_fail == 0 else "DEGRADED"
        log("validate_modeled", status, f"{len(modeled_dq)} checks, {n_fail} failed, {time.time()-t0:.1f}s")

        log("pipeline", "SUCCESS", f"total {time.time()-start:.1f}s")
        return 0
    except Exception as e:
        log("pipeline", "FAILED", str(e))
        raise


if __name__ == "__main__":
    sys.exit(main())
