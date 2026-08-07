import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
for sub in ["etl", "sql", "analysis", "agent"]:
    sys.path.insert(0, os.path.join(ROOT, sub))
