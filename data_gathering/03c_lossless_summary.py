# %% [markdown]
# # Lossless summary table
#
# Every test of the DICOM and OME-Zarr lossless runs (`03a`, `03b`), one row per
# configuration and specimen, compiled from the per-test JSON files (the actual
# results; the runners' summary CSVs are per job). Written next to the WG
# presentation's assets as `lossless_summary.csv`; the poster's `summary.csv` is
# left alone.
#
# Then a check of the run: is every configuration there, was every one actually
# lossless, and do the configurations shared with the poster's run reproduce its
# ratios. Last, the best setting of each codec, and the tall plot of compression
# ratio against compression time that `notebooks/2026-08-11_lossless_plot_tall.ipynb`
# made from the TIFF projection tests, written next to the summary.

# %%
import json
import os
from pathlib import Path

import polars as pl
from plotnine import (
    aes,
    element_blank,
    element_line,
    element_rect,
    element_text,
    facet_wrap,
    geom_path,
    geom_point,
    geom_text,
    ggplot,
    guide_legend,
    guides,
    labs,
    scale_color_manual,
    scale_fill_identity,
    scale_shape_manual,
    scale_x_continuous,
    scale_y_log10,
    theme,
    theme_minimal,
)

# %%
# A notebook has no __file__, and its working directory is data_gathering/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
POSTER_SUMMARY_FILE = PROJECT_DIR / "docs" / "poster_D3A_4_0" / "assets" / "summary.csv"

# The run to summarise; unset takes the newest full run of each container.
RUN_ID = os.environ.get("COMPTEST_RUN_ID") or None
SUMMARY_FILE = Path(
    os.environ.get("COMPTEST_SUMMARY_FILE")
    or PROJECT_DIR
    / "docs"
    / "presentation_qim_wg_2026-11-06"
    / "assets"
    / "lossless_summary.csv"
)

N_DATASETS = 3
N_CONFIGS = {"DICOM": 3, "OME-Zarr": 122}
CONTAINER_DIRS = {"DICOM": "dicom", "OME-Zarr": "zarr"}

CODECS = {
    "deflate": "DEFLATE",
    "htj2k": "HTJ2K",
    "j2k": "JPEG 2000",
    "jpeg": "Lossless JPEG",
    "jpegls": "JPEG-LS",
    "jpegxl": "JPEG-XL",
    "jpegxr": "JPEG XR",
    "lerc": "LERC",
    "lzma": "LZMA",
    "lzw": "LZW",
    "pcodec": "Pcodec",
    "png": "PNG",
    "rle": "RLE",
    "sz3": "SZ3",
    "zfp": "ZFP",
    "zstd": "Zstd",
}
DATA_TYPES = {"u16": "uint16", "f32": "float32"}


# %%
def run_dir(container: str) -> Path:
    root = OUTPUT_DIR / CONTAINER_DIRS[container]

    if RUN_ID is not None:
        run = root / f"lossless_{RUN_ID}"
        assert run.is_dir(), f"{run} does not exist"
        return run

    runs = sorted(
        path for path in root.glob("lossless_*") if "smoke" not in path.name
    )
    assert runs, f"No lossless runs in {root}"

    return runs[-1]


def row(test: dict, container: str, run: Path) -> dict:
    config = test["config"]
    runner = test["runner_extra"]
    extra = config.get("extra") or {}

    if container == "DICOM":
        data_type = "uint16"
        layout = "slice"
        ratio_vs_input = test["compression_ratio"]
    else:
        data_type = DATA_TYPES[runner["input_variant"].split("_")[0]]
        layout = extra.get("layout")
        ratio_vs_input = runner["compression_ratio_vs_input"]

    def cpu(step: str) -> float:
        return test[f"{step}_user_time_seconds"] + test[f"{step}_system_time_seconds"]

    return {
        "dataset": test["dataset_name"],
        "container": container,
        "codec": CODECS[test["series"].split("-")[1]],
        "data_type": data_type,
        "layout": layout,
        "name": test["name"],
        "series": test["series"],
        # Codec parameters; each codec uses one or two of these.
        "effort": test["effort"],
        "predictor": test["predictor"],
        "differencing": test["differencing"],
        "subcodec": test["subcodec"],
        "tolerance": test["tolerance"],
        "declared_lossless": test["lossless"],
        "was_actually_lossless": test["was_actually_lossless"],
        "interop_passed": runner.get("interop_passed"),
        # Sizes and ratios: against the uint16 volume (2 bytes per voxel) for every
        # input, float32 included, and against what the configuration actually read.
        "uncompressed_size": test["uncompressed_size"],
        "input_size": runner.get("input_size", test["uncompressed_size"]),
        "compressed_size": test["compressed_size"],
        "compression_ratio": test["compression_ratio"],
        "compression_ratio_vs_input": ratio_vs_input,
        "bitrate_compressed": test["bitrate_compressed"],
        "space_saving": test["space_saving"],
        # Timings of the whole volume. CPU is user + system over every thread
        # and worker process.
        "compress_wall_time_seconds": test["compress_wall_time_seconds"],
        "compress_cpu_time_seconds": cpu("compress"),
        "decompress_wall_time_seconds": test["decompress_wall_time_seconds"],
        "decompress_cpu_time_seconds": cpu("decompress"),
        "n_workers": runner.get("n_threads", runner.get("n_workers")),
        "z_limit": runner.get("z_limit"),
        "host": test["host"],
        "run": run.name,
        "start_time": test["start_wall_dt"],
    }


rows = []
for container in CONTAINER_DIRS:
    run = run_dir(container)
    print(f"{container}: {run}")

    for file in sorted(run.glob("*/test_*.json")):
        rows.append(row(json.loads(file.read_text()), container, run))

summary = pl.DataFrame(rows, infer_schema_length=None).sort(
    "container", "codec", "data_type", "layout", "dataset", "compression_ratio"
)

SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
summary.write_csv(SUMMARY_FILE)
print(f"{summary.height} rows -> {SUMMARY_FILE}")

# %%
summary.group_by("container", "codec", "data_type", "layout").agg(
    configs=pl.col("name").n_unique(),
    datasets=pl.col("dataset").n_unique(),
    ratio_vs_input_max=pl.col("compression_ratio_vs_input").max(),
).sort("container", "codec", "data_type", "layout")

# %% [markdown]
# # Checks

# %%
# Is every configuration there, for every specimen? A smoke test covers one.
for container, n_configs in N_CONFIGS.items():
    results = summary.filter(pl.col("container") == container)
    expected = n_configs * N_DATASETS
    print(
        f"{container}: {results.height}/{expected} results, "
        f"{results['name'].n_unique()}/{n_configs} configurations"
    )

# %%
# Was every one actually lossless?
not_lossless = summary.filter(~pl.col("was_actually_lossless"))
print(f"Not lossless: {not_lossless.height}")
not_lossless.select("dataset", "name", "compression_ratio")

# %%
interop_failed = summary.filter(pl.col("interop_passed").not_())
print(f"DICOM interop failures: {interop_failed.height}")
interop_failed.select("dataset", "name")

# %%
# The configurations also in the poster's run read the same volumes, so they must
# compress to the same size, but for DICOM's per-file random UIDs. Only meaningful
# for full volumes.
if summary["z_limit"].is_null().all():
    reproduced = (
        summary.select("dataset", "name", "compression_ratio")
        .join(
            pl.read_csv(POSTER_SUMMARY_FILE, infer_schema_length=None).select(
                "dataset", "name", poster_ratio="compression_ratio"
            ),
            on=["dataset", "name"],
        )
        .with_columns(
            relative_difference=(pl.col("compression_ratio") / pl.col("poster_ratio") - 1).abs()
        )
    )
    print(f"Worst difference from the poster: {reproduced['relative_difference'].max():.2e}")
    assert reproduced.height == 12, f"Expected 12 shared results, got {reproduced.height}"
else:
    reproduced = None
    print("Not comparing with the poster: some results are of cut-down volumes")

reproduced

# %% [markdown]
# # Best setting per codec
#
# Means over the specimens. Ratios against what each configuration read: 2 GB for
# uint16, 4 GB for float32, so the two data types do not compare directly.

# %%
by_config = (
    summary.with_columns(
        cpu_time_seconds=pl.col("compress_cpu_time_seconds")
        + pl.col("decompress_cpu_time_seconds")
    )
    .group_by(
        "container", "codec", "data_type", "layout", "name",
        "effort", "predictor", "differencing", "subcodec",
    )
    .agg(
        pl.col(
            "compression_ratio_vs_input",
            "compress_cpu_time_seconds",
            "compress_wall_time_seconds",
            "decompress_cpu_time_seconds",
        ).mean(),
        datasets=pl.col("dataset").n_unique(),
    )
)

best_per_codec = (
    by_config.sort("compression_ratio_vs_input", descending=True)
    .group_by("container", "codec", "data_type", maintain_order=True)
    .first()
    .sort(["data_type", "compression_ratio_vs_input"], descending=[True, True])
    .select(
        "data_type", "container", "codec", "name",
        pl.col("compression_ratio_vs_input").round(3),
        pl.col("compress_cpu_time_seconds").round(0),
        pl.col("compress_wall_time_seconds").round(1),
        pl.col("decompress_cpu_time_seconds").round(0),
    )
)

with pl.Config(tbl_rows=-1, tbl_width_chars=200, fmt_str_lengths=40):
    print(best_per_codec)

# %% [markdown]
# # Plot
#
# Compression ratio against compression CPU time, best at the bottom right, one
# panel per data type, and a version with uint16 alone. Lines join the levels or
# efforts of one setting. The CPU time axis is logarithmic: the codecs span 5 s to
# 20 min.
#
# Settings below a compression ratio of 1.5 are left out: RLE without a
# predictor, and LZW and RLE on float32. They are far from the rest and stretch
# the plot for little.
#
# The codecs in contention have colour, the rest are grey and told apart by
# shape. The colours are the poster's but for JPEG-LS: its magenta is too close
# to JPEG-XL's red, which it sits next to here.

# %%
PLOT_FILE = SUMMARY_FILE.with_name("lossless_plot_tall.svg")
PLOT_FILE_UINT16 = SUMMARY_FILE.with_name("lossless_plot_tall_uint16.svg")

FONT = "Liberation Sans"
# The text colours of plotnine's default theme, as in the 2026-08-11 plot.
INK = "black"
INK_STRIP = "#1a1a1a"
# The default theme's tick colour, here for the ticks and the frame they sit on.
AXIS = "#333333"
GRID = "#e1e0d9"
CR_MIN = 1.5
OTHER = "#8c8c88"

HIGHLIGHTED = {
    "JPEG-XL": "#e34948",
    "JPEG-LS": "#eda100",
    "JPEG 2000": "#2a78d6",
    "HTJ2K": "#008300",
    "Pcodec": "#4a3aa7",
}
OTHERS = [codec for codec in CODECS.values() if codec not in HIGHLIGHTED]
CODEC_ORDER = [*HIGHLIGHTED, *OTHERS]
COLORS = {**HIGHLIGHTED, **dict.fromkeys(OTHERS, OTHER)}
SHAPES = dict(
    zip(
        CODEC_ORDER,
        ["o", "s", "^", "v", "D", "<", ">", "p", "h", "*", "X", "P", "d", "8", "H", "x"],
        strict=True,
    )
)
DATA_TYPE_TITLES = {
    "uint16": "uint16: ratio against the 2 GB volume",
    "float32": "float32: ratio against the 4 GB volume",
}

plot_data = (
    by_config.with_columns(
        codec=pl.col("codec").cast(pl.Enum(CODEC_ORDER)),
        panel=pl.col("data_type")
        .replace_strict(DATA_TYPE_TITLES)
        .cast(pl.Enum(list(DATA_TYPE_TITLES.values()))),
        # Hollow markers for DICOM, filled for OME-Zarr.
        fill=pl.when(pl.col("container") == "DICOM")
        .then(pl.lit("white"))
        .otherwise(pl.col("codec").replace_strict(COLORS)),
        # One line per setting: everything but the level or effort.
        trajectory=pl.concat_str(
            [
                pl.col(column).cast(pl.String).fill_null("-")
                for column in ("container", "codec", "data_type", "layout", "predictor", "differencing", "subcodec")
            ],
            separator="/",
        ),
    )
    .filter(pl.col("compression_ratio_vs_input") >= CR_MIN)
    # geom_path joins in row order: by level or effort.
    .sort("trajectory", "effort")
)

# Each highlighted codec labelled once per panel, right of its best setting,
# where the plot is empty: these are the rightmost points.
labels = (
    plot_data.filter(pl.col("codec").is_in(list(HIGHLIGHTED)))
    .sort("compression_ratio_vs_input", descending=True)
    .group_by("panel", "codec", maintain_order=True)
    .first()
)

def lossless_plot(
    data: pl.DataFrame, figure_size: tuple[float, float], legend_columns: int
) -> ggplot:
    """`data` against CPU time, a panel per data type it holds."""
    data_labels = labels.join(data.select("panel").unique(), on="panel")
    # Only the codecs in `data` in the legend: ZFP and SZ3 are float32 only.
    present = set(data["codec"].cast(pl.String))
    codecs = [codec for codec in CODEC_ORDER if codec in present]
    # The panel titles name the data types; a single panel goes without.
    panels = data["panel"].unique()
    title = "Lossless compression — Best: bottom right"

    if len(panels) == 1:
        layout = []
    else:
        layout = [facet_wrap("panel", ncol=1, scales="free")]

    return (
        ggplot(
            data.to_pandas(),
            aes(
                "compression_ratio_vs_input",
                "compress_cpu_time_seconds",
                color="codec",
                shape="codec",
                group="trajectory",
            ),
        )
        + geom_path(size=0.7, alpha=0.6)
        + geom_point(aes(fill="fill"), size=3, stroke=0.8)
        + geom_text(
            aes(label="codec"),
            data=data_labels.to_pandas(),
            nudge_x=0.03,
            ha="left",
            size=10,
            family=FONT,
            color=INK,
            show_legend=False,
        )
        + layout
        # Room on the right for the labels.
        + scale_x_continuous(
            limits=(CR_MIN, None),
            breaks=[1.5, 1.75, 2, 2.25, 2.5, 2.75, 3],
            expand=(0.05, 0, 0.25, 0),
        )
        + scale_y_log10()
        + scale_color_manual(values=COLORS, breaks=codecs)
        + scale_shape_manual(values=SHAPES, breaks=codecs)
        + scale_fill_identity()
        + labs(
            title=title,
            x="Compression ratio",
            y="Compression CPU time (seconds)",
            color="Codec",
            shape="Codec",
        )
        + guides(
            color=guide_legend(ncol=legend_columns),
            shape=guide_legend(ncol=legend_columns),
        )
        + theme_minimal(base_size=12, base_family=FONT)
        + theme(
            figure_size=figure_size,
            dpi=300,
            text=element_text(color=INK),
            axis_text=element_text(color=INK),
            axis_ticks=element_line(color=AXIS, size=0.6),
            axis_ticks_length=4,
            # Ticks only where the labels are, as the gridlines.
            axis_ticks_minor=element_blank(),
            plot_title=element_text(size=13),
            strip_text=element_text(size=11, ha="left", color=INK_STRIP),
            legend_position="bottom",
            legend_title_position="top",
            panel_grid_major=element_line(color=GRID, size=0.6),
            panel_grid_minor=element_blank(),
            panel_border=element_rect(color=AXIS, fill=None, size=0.8),
            plot_background=element_rect(fill="white", color="white"),
        )
    )


p = lossless_plot(plot_data, figure_size=(4.5, 8), legend_columns=3)
p.save(PLOT_FILE, verbose=False)
print(f"Plot -> {PLOT_FILE}")
p

# %%
p_uint16 = lossless_plot(
    plot_data.filter(pl.col("data_type") == "uint16"),
    figure_size=(4, 6.5),
    legend_columns=2,
)
p_uint16.save(PLOT_FILE_UINT16, verbose=False)
print(f"Plot -> {PLOT_FILE_UINT16}")
p_uint16
