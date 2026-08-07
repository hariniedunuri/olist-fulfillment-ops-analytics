# Raw data

Download the 9 Olist CSVs from Kaggle: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

Place all 9 CSVs directly in this folder (`data/raw/`), then run:

```bash
python etl/ingest.py
python etl/validate.py
python etl/transform_load.py
python etl/validate_modeled.py
```

or simply: `python orchestration/run_pipeline.py`
