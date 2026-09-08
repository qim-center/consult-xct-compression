# %% [markdown]
# # OME-Zarr compression results viewer
#
# Absorbs the `test_*.json` documents written by
# `2026-09-01_ome_zarr_compression_tests.py` and plots the compression/quality
# trade-off with plotnine, in the same spirit as `test_viewer.ipynb`.
#
# Runs either interactively (`# %%` cells, jupytext) or as a plain script, in
# which case every figure is also written to
# `output/ome-zarr-viewer/{selection}/`.
#
# The JSON schema is `comptest.types.CompressionTest`. Everything is flattened
# to a wide table, so `ssim.mean` becomes `ssim__mean`, `runner_extra.psnr_db`
# becomes `runner_extra__psnr_db`, and so on.

# %%
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib
import plotnine as gg
import polars as pl

# A notebook has no __file__, and its working directory is notebooks/.
IS_SCRIPT = "__file__" in globals()

if IS_SCRIPT:
    # Run non-interactively, the backend would otherwise be resolved from a
    # display an LSF node does not have, and plotnine's rc_context then trips
    # over matplotlib's unresolved auto-backend sentinel.
    matplotlib.use("Agg")

pl.Config.set_fmt_str_lengths(200)
pl.Config.set_tbl_width_chars(400)
pl.Config.set_tbl_rows(60)

# %load_ext autoreload
# %autoreload 2

# %% [markdown]
# # Parameters
#
# As in the test runner, every parameter can be overridden through a
# `COMPTEST_` environment variable so the script is usable non-interactively.


# %%
def _env_str(name: str, default: str) -> str:
    return os.environ.get(f"COMPTEST_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(f"COMPTEST_{name}")

    if value is None or not value.strip():
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str] | None) -> list[str] | None:
    """Comma- or whitespace-separated; an empty variable means "unset"."""
    value = os.environ.get(f"COMPTEST_{name}")

    if value is None or not value.strip():
        return default

    return value.replace(",", " ").split()


# %%
NOTEBOOK_DIR = Path(__file__).resolve().parent if IS_SCRIPT else Path().resolve()
PROJECT_DIR = NOTEBOOK_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
assert OUTPUT_DIR.is_dir()

TEST_RUN_TYPE = _env_str("TEST_RUN_TYPE", "ome-zarr")
RUNS_DIR = OUTPUT_DIR / TEST_RUN_TYPE
assert RUNS_DIR.is_dir(), f"No run directory {RUNS_DIR}"

# Run directory names under output/{TEST_RUN_TYPE}/; None = every run found.
SELECTED_RUN_IDS: list[str] | None = _env_list("RUN_IDS", None)

# None = every dataset present in the selected runs.
DATASET_NAME: str | None = _env_str("DATASET", "") or None

# The same config can appear in several runs (a rerun, a per-config LSF job).
# By default only the most recent result per (dataset, config) is kept; set this
# to compare runs against each other instead.
KEEP_ALL_RUNS = _env_bool("KEEP_ALL_RUNS", False)

# Where figures are written. Always written when run as a script.
SAVE_FIGURES = _env_bool("SAVE_FIGURES", IS_SCRIPT)
FIGURE_DPI = 150

# %%
RUN_DIRS = sorted(
    directory
    for directory in RUNS_DIR.iterdir()
    if directory.is_dir()
    and (SELECTED_RUN_IDS is None or directory.name in SELECTED_RUN_IDS)
)
assert RUN_DIRS, f"No runs selected in {RUNS_DIR} (wanted {SELECTED_RUN_IDS})"

if SELECTED_RUN_IDS is not None:
    missing = set(SELECTED_RUN_IDS) - {directory.name for directory in RUN_DIRS}
    assert not missing, f"Requested runs not found: {sorted(missing)}"

FIGURE_DIR = (
    OUTPUT_DIR
    / f"{TEST_RUN_TYPE}-viewer"
    / ("+".join(SELECTED_RUN_IDS) if SELECTED_RUN_IDS else "all-runs")
)

for run_dir in RUN_DIRS:
    print(run_dir.name)

# %% [markdown]
# # Loading
#
# `flatten` is the one from `test_viewer.ipynb`, minus the SSIM histogram: its
# 100 bins are fixed on [0, 1], so for anything but a badly degraded volume they
# all land in the top bin and only add 200 useless columns. The quantile fields
# on the same object carry the distribution instead.

# %%
FLATTEN_SKIP_KEYS = {"histogram_values", "histogram_bin_edges", "allowed_dtypes"}


def flatten(data: Any, prefix: str = "", sep: str = "__") -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    if isinstance(data, Mapping):
        for key, value in data.items():
            if key in FLATTEN_SKIP_KEYS:
                continue

            column = f"{prefix}{sep}{key}" if prefix else str(key)
            flattened.update(flatten(value, column, sep))

    elif isinstance(data, Sequence) and not isinstance(data, str | bytes):
        for index, value in enumerate(data):
            flattened.update(flatten(value, f"{prefix}[{index}]", sep))

    else:
        flattened[prefix] = data

    return flattened


# %%
rows: list[dict[str, Any]] = []

for run_dir in RUN_DIRS:
    for dataset_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        if DATASET_NAME is not None and dataset_dir.name != DATASET_NAME:
            continue

        for file in sorted(dataset_dir.glob("test_*.json")):
            data = json.loads(file.read_text())

            rows.append(
                {
                    "run_id": run_dir.name,
                    "source_file": str(file.relative_to(OUTPUT_DIR)),
                    **flatten(data),
                }
            )

assert rows, f"No test_*.json found under {[str(d) for d in RUN_DIRS]}"

df_raw = pl.DataFrame(rows, strict=False, infer_schema_length=None)

print(f"{df_raw.height} test documents, {df_raw.width} columns")

# %% [markdown]
# # Derived columns
#
# The two serializer families parameterise quality differently — JPEG XL by
# Butteraugli `distance`, JPEG-LS by the NEAR tolerance — so both are mapped
# onto a single `quality_param` for plotting, with `quality_param_name` saying
# which knob it was.

# %%
SERIES_LABELS = {
    "zarr-jpegxl": "JPEG XL",
    "zarr-jpegls": "JPEG-LS",
    "zarr-uncompressed": "Uncompressed",
}


def _optional(column: str, dtype: pl.DataType = pl.Float64) -> pl.Expr:
    """Column, or a null literal when this run never wrote it."""
    if column in df_raw.columns:
        return pl.col(column).cast(dtype)

    return pl.lit(None, dtype=dtype).alias(column)


df = df_raw.with_columns(
    _optional("ssim__mean").alias("ssim_mean"),
    _optional("ssim__min").alias("ssim_min"),
    _optional("ssim__max").alias("ssim_max"),
    _optional("ssim__median").alias("ssim_median"),
    _optional("ssim__percentile_25th").alias("ssim_p25"),
    _optional("ssim__percentile_75th").alias("ssim_p75"),
    _optional("runner_extra__psnr_db").alias("psnr_db"),
    _optional("runner_extra__rmse").alias("rmse"),
    _optional("runner_extra__max_abs_error", pl.Int64).alias("max_abs_error"),
    pl.col("series").replace(SERIES_LABELS).alias("codec"),
    (pl.col("compression_wall_rate") / 1e6).alias("compress_wall_mbps"),
    (pl.col("compression_user_rate") / 1e6).alias("compress_user_mbps"),
    (pl.col("decompression_wall_rate") / 1e6).alias("decompress_wall_mbps"),
    (pl.col("decompression_user_rate") / 1e6).alias("decompress_user_mbps"),
    (pl.col("compressed_size") / 1e9).alias("compressed_size_gb"),
)

df = df.with_columns(
    # distance for JPEG XL, NEAR for JPEG-LS. Nulls stay null (uncompressed).
    pl.coalesce(pl.col("distance"), pl.col("tolerance")).alias("quality_param"),
    pl.when(pl.col("distance").is_not_null())
    .then(pl.lit("distance"))
    .when(pl.col("tolerance").is_not_null())
    .then(pl.lit("NEAR"))
    .otherwise(pl.lit("none"))
    .alias("quality_param_name"),
    # 1 - SSIM is the quantity worth a log axis; SSIM itself piles up at 1.0.
    (1.0 - pl.col("ssim_mean")).alias("ssim_loss"),
)

df = df.with_columns(
    pl.when(pl.col("quality_param").is_null())
    .then(pl.col("codec"))
    .otherwise(
        pl.col("quality_param_name")
        + "="
        + pl.col("quality_param").map_elements(lambda v: f"{v:g}", return_dtype=pl.Utf8)
    )
    .alias("label"),
    # plotnine cannot build a legend key for a null discrete level, so the
    # codecs that have no effort knob get an explicit one.
    pl.when(pl.col("effort").is_not_null())
    .then(pl.lit("e") + pl.col("effort").cast(pl.Utf8))
    .otherwise(pl.lit("n/a"))
    .alias("effort_label"),
    # The series a rate/distortion curve is drawn along: one codec at one effort.
    pl.concat_str(
        pl.col("codec"),
        pl.when(pl.col("effort").is_not_null())
        .then(pl.lit(" e") + pl.col("effort").cast(pl.Utf8))
        .otherwise(pl.lit("")),
        ignore_nulls=True,
    ).alias("curve"),
)

# %%
if not KEEP_ALL_RUNS:
    before = df.height
    df = (
        df.sort("start_wall_dt")
        .group_by("dataset_name", "name", maintain_order=True)
        .last()
    )

    if before != df.height:
        print(f"Deduplicated {before} -> {df.height} tests (latest run per config)")

df = df.sort("codec", "quality_param", nulls_last=False)

# %%
# Datasets and codecs are faceted, not overlaid, so a mixed selection is safe
# but worth seeing.
print(df.select("dataset_name", "codec").unique().sort("dataset_name", "codec"))

df_lossy = df.filter(pl.col("was_actually_lossless").not_())
df_lossless = df.filter(pl.col("was_actually_lossless"))

print(f"{df_lossy.height} lossy tests, {df_lossless.height} lossless tests")

# %% [markdown]
# # Summary table

# %%
SUMMARY_COLUMNS = [
    "codec",
    "name",
    "quality_param",
    "effort",
    "compression_ratio",
    "space_saving",
    "bitrate_compressed",
    "compressed_size_gb",
    "ssim_mean",
    "psnr_db",
    "rmse",
    "max_abs_error",
    "compress_wall_mbps",
    "decompress_wall_mbps",
    "was_actually_lossless",
]

summary = df.select(SUMMARY_COLUMNS).sort("codec", "compression_ratio")
summary

# %% [markdown]
# # Plots
#
# Every figure is built by a small function so that the script can save them all
# in one pass while an interactive session still gets them one cell at a time.

# %%
THEME = gg.theme_matplotlib() + gg.theme(
    figure_size=(9, 6),
    dpi=FIGURE_DPI,
    legend_position="right",
    panel_grid_major=gg.element_line(color="#e6e6e6"),
    panel_grid_minor=gg.element_line(color="#f5f5f5"),
)

# Ordered so a codec keeps its colour across every figure.
CODEC_ORDER = sorted(df["codec"].unique().to_list())

CURVE_AES = gg.aes(color="codec", shape="effort_label", group="curve")

FIGURES: dict[str, gg.ggplot] = {}


def register(name: str, plot: gg.ggplot) -> gg.ggplot:
    FIGURES[name] = plot

    return plot


def label_layer(
    data: pl.DataFrame, size: float = 7.0, adjust: bool = True, **kwargs: Any
) -> gg.geom_text:
    """Quality-parameter labels, nudged off the marker they belong to.

    `adjust=False` falls back to a fixed offset: adjustText leaves labels sitting
    on top of their marker when a layer also varies point size, which makes them
    unreadable.
    """
    if adjust:
        kwargs.setdefault(
            "adjust_text",
            {
                "arrowprops": {"arrowstyle": "-", "color": "0.5", "linewidth": 0.4},
                "expand": (1.15, 1.3),
                "force_text": (0.2, 0.4),
            },
        )

    return gg.geom_text(
        data=data,
        mapping=gg.aes(label="label"),
        size=size,
        color="black",
        **kwargs,
    )


# %% [markdown]
# ## Rate–distortion: how much quality each compression ratio costs
#
# The headline plot. Compression ratio on a log axis against mean SSIM; a point
# up and to the right is strictly better. Lossless configs are drawn as vertical
# rules, since their SSIM is 1 by construction and not measured.

# %%
plot = (
    gg.ggplot(df_lossy, gg.aes(x="compression_ratio", y="ssim_mean"))
    + CURVE_AES
    + gg.geom_vline(
        data=df_lossless,
        mapping=gg.aes(xintercept="compression_ratio", color="codec"),
        linetype="dashed",
        alpha=0.7,
        show_legend=False,
    )
    + gg.geom_line(alpha=0.6)
    + gg.geom_point(size=3)
    + label_layer(df_lossy)
    + gg.scale_x_log10()
    + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.scale_shape_discrete(name="Effort")
    + gg.labs(
        title="Rate-distortion: compression ratio vs. mean SSIM",
        subtitle="Dashed rules are lossless configurations (SSIM = 1 by construction)",
        x="Compression ratio (x, log scale)",
        y="Mean SSIM",
    )
    + THEME
)
register("01_ratio_vs_ssim", plot)

# %% [markdown]
# ## The same trade-off with 1 - SSIM on a log axis
#
# Mean SSIM saturates near 1, which hides how far apart the good configurations
# actually are. `1 - SSIM` on a log axis separates them; lower is better.

# %%
plot = (
    gg.ggplot(
        df_lossy.filter(pl.col("ssim_loss") > 0),
        gg.aes(x="compression_ratio", y="ssim_loss"),
    )
    + CURVE_AES
    + gg.geom_line(alpha=0.6)
    + gg.geom_point(size=3)
    + label_layer(df_lossy.filter(pl.col("ssim_loss") > 0))
    + gg.scale_x_log10()
    + gg.scale_y_log10()
    + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.scale_shape_discrete(name="Effort")
    + gg.labs(
        title="Rate-distortion: compression ratio vs. SSIM loss",
        subtitle="Lower is better; log-log separates the configurations SSIM alone hides",
        x="Compression ratio (x, log scale)",
        y="1 - mean SSIM (log scale)",
    )
    + THEME
)
register("02_ratio_vs_ssim_loss", plot)

# %% [markdown]
# ## Rate–distortion in PSNR
#
# Bitrate rather than ratio on the x axis, which is how codec comparisons are
# usually reported, and PSNR as the distortion measure. Both metrics are shown
# because they disagree: SSIM is structural, PSNR is per-voxel.

# %%
plot = (
    gg.ggplot(
        df_lossy.filter(pl.col("psnr_db").is_not_null()),
        gg.aes(x="bitrate_compressed", y="psnr_db"),
    )
    + CURVE_AES
    + gg.geom_line(alpha=0.6)
    + gg.geom_point(size=3)
    + label_layer(df_lossy.filter(pl.col("psnr_db").is_not_null()))
    + gg.scale_x_log10()
    + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.scale_shape_discrete(name="Effort")
    + gg.labs(
        title="Rate-distortion: bitrate vs. PSNR",
        x="Compressed bitrate (bits/voxel, log scale)",
        y="PSNR (dB)",
    )
    + THEME
)
register("03_bitrate_vs_psnr", plot)

# %% [markdown]
# ## What the quality knob buys
#
# Compression ratio against the codec's own quality parameter. The two families
# are faceted because `distance` and NEAR are not the same unit; the point is
# the shape of each curve, not a comparison across the panels.

# %%
df_knob = df_lossy.filter(pl.col("quality_param") > 0)

plot = (
    gg.ggplot(df_knob, gg.aes(x="quality_param", y="compression_ratio"))
    + CURVE_AES
    + gg.geom_line(alpha=0.6)
    + gg.geom_point(size=3)
    + gg.facet_wrap("quality_param_name", scales="free_x")
    + gg.scale_x_log10()
    + gg.scale_y_log10()
    + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.scale_shape_discrete(name="Effort")
    + gg.labs(
        title="Compression ratio vs. the codec's quality parameter",
        subtitle="JPEG XL Butteraugli distance and JPEG-LS NEAR are different units",
        x="Quality parameter (log scale)",
        y="Compression ratio (x, log scale)",
    )
    + THEME
)
register("04_quality_param_vs_ratio", plot)

# %% [markdown]
# ## SSIM spread within a volume
#
# The mean hides slices that fare much worse than the rest, which is exactly
# what matters for a lossy archive format. Plotted as SSIM *loss* on a log axis
# for the same reason as above: on a linear SSIM axis the worst-case whisker
# drags the scale down to 0 and every box collapses onto 1.0.
#
# Box = interquartile range, whiskers = observed min/max over the per-voxel SSIM
# map, ordered by compression ratio.

# %%
df_spread = df_lossy.filter(pl.col("ssim_mean").is_not_null()).with_columns(
    (1.0 - pl.col("ssim_max")).alias("loss_min"),
    (1.0 - pl.col("ssim_p75")).alias("loss_p25"),
    (1.0 - pl.col("ssim_median")).alias("loss_median"),
    (1.0 - pl.col("ssim_p25")).alias("loss_p75"),
    (1.0 - pl.col("ssim_min")).alias("loss_max"),
    (1.0 - pl.col("ssim_mean")).alias("loss_mean"),
)

LOSS_COLUMNS = [
    "loss_min",
    "loss_p25",
    "loss_median",
    "loss_p75",
    "loss_max",
    "loss_mean",
]

# A perfectly reconstructed region gives SSIM exactly 1, and log10(0) is not a
# coordinate. Floor those at half the smallest loss actually observed.
LOSS_FLOOR = (
    df_spread.select(LOSS_COLUMNS).unpivot().filter(pl.col("value") > 0)["value"].min()
    / 2
)

df_spread = df_spread.with_columns(
    pl.max_horizontal(pl.col(column), pl.lit(LOSS_FLOOR)).alias(column)
    for column in LOSS_COLUMNS
).sort("compression_ratio")

plot = (
    gg.ggplot(df_spread, gg.aes(x="name"))
    + gg.geom_boxplot(
        gg.aes(
            ymin="loss_min",
            lower="loss_p25",
            middle="loss_median",
            upper="loss_p75",
            ymax="loss_max",
            fill="codec",
        ),
        stat="identity",
        width=0.6,
    )
    + gg.geom_point(gg.aes(y="loss_mean"), shape="D", size=1.8, color="black")
    + gg.scale_x_discrete(limits=df_spread["name"].to_list())
    + gg.scale_y_log10()
    + gg.scale_fill_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.coord_flip()
    + gg.labs(
        title="SSIM distribution over the volume",
        subtitle=(
            "Box: p25-p75, whiskers: min/max, diamond: mean. "
            "Left is better; ordered by compression ratio"
        ),
        x=None,
        y="1 - SSIM (log scale)",
    )
    + THEME
    + gg.theme(figure_size=(9, 0.32 * max(df_spread.height, 8) + 2))
)
register("05_ssim_spread", plot)

# %% [markdown]
# ## Worst-case error
#
# SSIM and PSNR are averages. `max_abs_error` is the single worst voxel in the
# volume, in raw sample units, and is the number a bound like "NEAR = 8" is
# supposed to guarantee.

# %%
df_error = df_lossy.filter(pl.col("max_abs_error").is_not_null()).unpivot(
    on=["rmse", "max_abs_error"],
    index=["codec", "curve", "effort_label", "compression_ratio", "label"],
    variable_name="error_metric",
    value_name="error",
)
df_error = df_error.with_columns(
    pl.col("error_metric")
    .replace({"rmse": "RMSE", "max_abs_error": "Max absolute error"})
    .alias("error_metric")
)

plot = (
    gg.ggplot(df_error, gg.aes(x="compression_ratio", y="error"))
    + CURVE_AES
    + gg.geom_line(alpha=0.6)
    + gg.geom_point(size=3)
    + gg.facet_wrap("error_metric", scales="free_y")
    + gg.scale_x_log10()
    + gg.scale_y_log10()
    + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.scale_shape_discrete(name="Effort")
    + gg.labs(
        title="Reconstruction error vs. compression ratio",
        subtitle="Sample units of the source dtype; lower is better",
        x="Compression ratio (x, log scale)",
        y="Error (log scale)",
    )
    + THEME
)
register("06_error_vs_ratio", plot)

# %% [markdown]
# ## Throughput against compression ratio
#
# The other axis of the trade-off. Wall rates are what a user waits for;
# user rates are CPU seconds per byte and are the honest cross-machine
# comparison, since the runs are threaded.

# %%
df_rate = df.unpivot(
    on=[
        "compress_wall_mbps",
        "compress_user_mbps",
        "decompress_wall_mbps",
        "decompress_user_mbps",
    ],
    index=["codec", "curve", "effort_label", "compression_ratio", "label"],
    variable_name="rate_kind",
    value_name="rate_mbps",
)
df_rate = df_rate.with_columns(
    pl.col("rate_kind")
    .replace(
        {
            "compress_wall_mbps": "Compress (wall)",
            "compress_user_mbps": "Compress (CPU)",
            "decompress_wall_mbps": "Decompress (wall)",
            "decompress_user_mbps": "Decompress (CPU)",
        }
    )
    .alias("rate_kind")
)

plot = (
    gg.ggplot(df_rate, gg.aes(x="compression_ratio", y="rate_mbps"))
    + CURVE_AES
    + gg.geom_line(alpha=0.6)
    + gg.geom_point(size=3)
    + gg.facet_wrap("rate_kind", scales="free_y", ncol=2)
    + gg.scale_x_log10()
    + gg.scale_y_log10()
    + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.scale_shape_discrete(name="Effort")
    + gg.labs(
        title="Throughput vs. compression ratio",
        subtitle="Uncompressed bytes per second of wall / CPU time",
        x="Compression ratio (x, log scale)",
        y="Throughput (MB/s, log scale)",
    )
    + THEME
    + gg.theme(figure_size=(10, 7))
)
register("07_throughput_vs_ratio", plot)

# %% [markdown]
# ## Quality per unit of decode cost
#
# For an archive that is written once and read often, decompression speed is the
# constraint that actually bites, and it is the one axis the rate-distortion
# plots above leave out. Bottom right is the corner to aim for: fast to read
# back and close to the reference.
#
# No connecting line here — decode throughput is not monotonic in the quality
# knob, so joining the points in knob order would draw a curve that says
# nothing. Compression ratio is deliberately not encoded as point size: a size
# scale in this layer also rescales the labels into illegibility, and figures 01
# and 02 already put ratio on an axis.

# %%
df_decode = df_lossy.filter(pl.col("ssim_loss") > 0)

plot = (
    gg.ggplot(df_decode, gg.aes(x="decompress_wall_mbps", y="ssim_loss"))
    + gg.aes(color="codec", shape="effort_label")
    + gg.geom_point(size=3)
    + label_layer(df_decode)
    + gg.scale_y_log10()
    + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.scale_shape_discrete(name="Effort")
    + gg.labs(
        title="Decode throughput vs. SSIM loss",
        subtitle="Bottom right is best: fast to read back and close to the reference",
        x="Decompression throughput (MB/s, wall)",
        y="1 - mean SSIM (log scale)",
    )
    + THEME
)
register("08_decode_rate_vs_ssim", plot)

# %% [markdown]
# ## Space saving per configuration
#
# The absolute view: how much of the 2 GB volume each configuration removes, and
# what is left on disk.

# %%
df_saving = df.sort("space_saving")

plot = (
    gg.ggplot(df_saving, gg.aes(x="name", y="space_saving", fill="codec"))
    + gg.geom_col(width=0.7)
    + gg.geom_text(
        gg.aes(
            label=pl.Series(
                [
                    f"{ratio:.1f}x  ({size:.2f} GB)"
                    if size >= 0.1
                    else f"{ratio:.1f}x  ({size * 1000:.0f} MB)"
                    for ratio, size in zip(
                        df_saving["compression_ratio"],
                        df_saving["compressed_size_gb"],
                        strict=True,
                    )
                ]
            )
        ),
        ha="left",
        nudge_y=0.01,
        size=7,
    )
    + gg.scale_x_discrete(limits=df_saving["name"].to_list())
    + gg.scale_y_continuous(
        labels=lambda values: [f"{value:.0%}" for value in values],
        expand=(0, 0, 0.18, 0),
    )
    + gg.scale_fill_discrete(limits=CODEC_ORDER, name="Codec")
    + gg.coord_flip()
    + gg.labs(
        title="Space saving per configuration",
        subtitle="Annotated with compression ratio and resulting store size",
        x=None,
        y="Space saving",
    )
    + THEME
    + gg.theme(figure_size=(9, 0.32 * max(df_saving.height, 8) + 2))
)
register("09_space_saving", plot)

# %% [markdown]
# ## In-memory vs. on-disk size
#
# The tests replay each configuration into a `MemoryStore`, while the stores the
# configurations were read from sit on the shared filesystem. The two sizes
# should agree up to the sharding index and any chunk that happens to be empty
# on disk, so a point off the diagonal means the replay did not reproduce the
# store.

# %%
if "runner_extra__source_store_level_size" in df.columns:
    df_sizes = df.with_columns(
        (pl.col("runner_extra__source_store_level_size") / 1e9).alias("on_disk_gb"),
        (
            pl.col("runner_extra__source_store_level_size") / pl.col("compressed_size")
        ).alias("disk_over_memory"),
    )

    plot = (
        gg.ggplot(df_sizes, gg.aes(x="compressed_size_gb", y="on_disk_gb"))
        + gg.geom_abline(slope=1, intercept=0, linetype="dashed", color="#999999")
        + gg.aes(color="codec", shape="effort_label")
        + gg.geom_point(size=3)
        + label_layer(df_sizes)
        # Room for the labels on the two extreme points.
        + gg.scale_x_log10(expand=(0.12, 0))
        + gg.scale_y_log10(expand=(0.10, 0))
        + gg.scale_color_discrete(limits=CODEC_ORDER, name="Codec")
        + gg.scale_shape_discrete(name="Effort")
        + gg.labs(
            title="Replayed in-memory size vs. the store on disk",
            subtitle="Dashed line is equality; the s0 array only",
            x="In-memory compressed size (GB, log scale)",
            y="On-disk s0 size (GB, log scale)",
        )
        + THEME
    )
    register("10_memory_vs_disk_size", plot)

    print(
        df_sizes.select("name", "compressed_size_gb", "on_disk_gb", "disk_over_memory")
        .sort("disk_over_memory")
        .head(5)
    )

# %% [markdown]
# # Saving
#
# Written as PNG for quick viewing and PDF for the report, alongside the wide
# table the figures were built from.

# %%
if SAVE_FIGURES:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    summary.write_csv(FIGURE_DIR / "summary.csv")
    df.write_parquet(FIGURE_DIR / "tests.parquet")

    for figure_name, figure in FIGURES.items():
        for extension in ("png", "pdf"):
            path = FIGURE_DIR / f"{figure_name}.{extension}"
            figure.save(path, dpi=FIGURE_DPI, verbose=False)
            print(f"Wrote {path}")
else:
    print(f"SAVE_FIGURES is off; {len(FIGURES)} figures built but not written")
