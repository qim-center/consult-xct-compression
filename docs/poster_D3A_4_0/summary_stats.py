"""Average selected rows of assets/summary.csv and write mean/std to JSON for Typst."""

import json
from pathlib import Path

import polars as pl

HERE = Path(__file__).parent
SUMMARY = HERE / "assets" / "summary.csv"
OUT = HERE / "summary_stats.json"

FILTERS = {"codec": "JPEG-XL", "distance": 0.5}
METRICS = [
    "compression_ratio",
    "bitrate_compressed",
    "space_saving",
    "psnr_db",
    "ssim_mean",
    "ms_ssim",
    "max_abs_error_u16",
    "linf_normalised",
    "compress_wall_time_seconds",
    "decompress_wall_time_seconds",
]

# Full-file schema inference: codec-specific columns are empty in the first rows.
df = pl.read_csv(SUMMARY, infer_schema_length=None).filter(**FILTERS)

stats = {
    "filters": FILTERS,
    "n": df.height,
    "rows": df.select("dataset", "data_type").to_dicts(),
    "metrics": {
        m: {"mean": df[m].mean(), "std": df[m].std()}  # std is sample std (ddof=1)
        for m in METRICS
    },
}

OUT.write_text(json.dumps(stats, indent=2))
print(json.dumps(stats, indent=2))
