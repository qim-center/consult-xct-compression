# %% [markdown]
# # Summary table for the D3A poster
#
# Every DICOM and OME-Zarr test of the 2026-10-05/06 runs, one row per
# configuration and specimen, compiled from the per-test JSON files (the actual
# results; the runners' summary CSVs are per job). Written next to the poster's
# assets as `summary.csv`.

# %%
import json
from pathlib import Path

import numpy as np
import polars as pl

# %%
# A notebook has no __file__, and its working directory is notebooks/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
SUMMARY_FILE = PROJECT_DIR / "docs" / "poster_D3A_4_0" / "assets" / "summary.csv"

# The same runs as the rate-distortion plots. Later runs win on duplicates.
RUNS = {
    "DICOM": [OUTPUT_DIR / "dicom" / "quality_2026-10-05"],
    "OME-Zarr": [
        OUTPUT_DIR / "zarr" / "quality_2026-10-05",
        OUTPUT_DIR / "zarr" / "quality_2026-10-06",
    ],
}

CODECS = {
    "j2k": "JPEG 2000",
    "htj2k": "HTJ2K",
    "jpegls": "JPEG-LS",
    "jpegxl": "JPEG-XL",
    "lerc": "LERC",
    "pcodec": "Pcodec",
    "sperr": "SPERR",
    "sz3": "SZ3",
    "zfp": "ZFP",
}
DATA_TYPES = {"u16": "uint16", "f32": "float32"}
U16_MAX = np.iinfo(np.uint16).max


# %%
def row(test: dict, container: str, run: Path) -> dict:
    config = test["config"]
    runner = test["runner_extra"]
    extra = config.get("extra") or {}
    ssim = test.get("ssim") or {}

    if container == "DICOM":
        data_type = "uint16"
        layout = "slice"
        # The DICOM volume is uint16, so its errors are already in uint16 steps.
        max_abs_error_u16 = runner.get("max_abs_error")
    else:
        data_type = DATA_TYPES[runner["input_variant"].split("_")[0]]
        layout = extra.get("layout")
        max_abs_error_u16 = runner.get("max_abs_error_u16_equivalent")

    cpu = lambda step: test[f"{step}_user_time_seconds"] + test[f"{step}_system_time_seconds"]

    return {
        "dataset": test["dataset_name"],
        "container": container,
        "codec": CODECS[test["series"].split("-")[1]],
        "data_type": data_type,
        "layout": layout,
        "name": test["name"],
        "series": test["series"],
        # Codec parameters; each codec uses one or two of these.
        "tolerance": test["tolerance"],
        "quality": test["quality"],
        "distance": test["distance"],
        "effort": test["effort"],
        "target_ratio": extra.get("target_ratio"),
        "rate_bits_per_value": extra.get("rate_bits_per_value"),
        "declared_lossless": test["lossless"],
        "was_actually_lossless": test["was_actually_lossless"],
        # Sizes and ratios, against the uint16 volume (2 bytes per voxel) for
        # every input, float32 included.
        "uncompressed_size": test["uncompressed_size"],
        "compressed_size": test["compressed_size"],
        "compression_ratio": test["compression_ratio"],
        "bitrate_compressed": test["bitrate_compressed"],
        "space_saving": test["space_saving"],
        # Quality, against the volume the configuration read.
        "psnr_db": runner.get("psnr_db"),
        "rmse": runner.get("rmse"),
        "max_abs_error": runner.get("max_abs_error"),
        "max_abs_error_u16": max_abs_error_u16,
        "linf_normalised": None if max_abs_error_u16 is None else max_abs_error_u16 / U16_MAX,
        "ssim_mean": ssim.get("mean"),
        "ms_ssim": runner.get("ms_ssim"),
        # Timings of the whole volume. CPU is user + system over every thread
        # and worker process.
        "compress_wall_time_seconds": test["compress_wall_time_seconds"],
        "compress_cpu_time_seconds": cpu("compress"),
        "decompress_wall_time_seconds": test["decompress_wall_time_seconds"],
        "decompress_cpu_time_seconds": cpu("decompress"),
        "n_workers": runner.get("n_threads", runner.get("n_workers")),
        "host": test["host"],
        "run": run.name,
        "start_time": test["start_wall_dt"],
    }


rows = []
for container, runs in RUNS.items():
    for run in runs:
        for file in sorted(run.glob("*/test_*.json")):
            rows.append(row(json.loads(file.read_text()), container, run))

summary = (
    pl.DataFrame(rows, infer_schema_length=None)
    # The same configuration in two runs: keep the later.
    .unique(["dataset", "name"], keep="last", maintain_order=True)
    .sort("container", "codec", "data_type", "layout", "dataset", "compression_ratio")
)

SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
summary.write_csv(SUMMARY_FILE)
print(f"{summary.height} rows -> {SUMMARY_FILE}")

# %%
summary.group_by("container", "codec", "data_type", "layout").agg(
    configs=pl.col("name").n_unique(), datasets=pl.col("dataset").n_unique()
).sort("container", "codec", "data_type", "layout")
