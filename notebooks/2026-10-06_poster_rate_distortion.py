# %% [markdown]
# # Rate-distortion plots for the D3A poster
#
# Compression ratio (log x) against each fidelity metric, for every lossy DICOM
# and OME-Zarr configuration from the 2026-10-05/06 runs, pooled over the three
# wolf skulls. And for the lossless configurations, compression ratio against
# decompression time.

# %%
import copy
import json
from pathlib import Path

import numpy as np
from matplotlib.transforms import Bbox
import pandas as pd
import polars as pl
from scipy import stats
from mizani.bounds import squish
from plotnine.composition import Compose, Stack
from plotnine import (
    aes,
    geom_errorbar,
    geom_errorbarh,
    geom_text,
    element_blank,
    element_line,
    element_rect,
    element_text,
    facet_wrap,
    geom_line,
    geom_point,
    ggplot,
    guide_legend,
    guides,
    labs,
    scale_color_manual,
    scale_fill_manual,
    scale_linetype_manual,
    scale_shape_manual,
    scale_x_log10,
    scale_y_continuous,
    scale_y_log10,
    theme,
    theme_minimal,
)

# %%
# A notebook has no __file__, and its working directory is notebooks/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
# One subfolder per iteration of the plots, so earlier ones stay around to compare.
ITERATION = 18
PLOT_DIR = PROJECT_DIR / "docs" / "poster_D3A_4_0" / "assets" / "plots" / str(ITERATION)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

DICOM_RUNS = [OUTPUT_DIR / "dicom" / "quality_2026-10-05"]
# The 2026-10-05 Zarr run only finished the JPEG family for Canislupus_CZM_712;
# the 2026-10-06 run has everything else. Later runs win on duplicates.
ZARR_RUNS = [
    OUTPUT_DIR / "zarr" / "quality_2026-10-05",
    OUTPUT_DIR / "zarr" / "quality_2026-10-06",
]

DATASET_LABELS = {
    "Canislupus_CZM_712": "CZM 712",
    "Canislupus_BM_2600": "BM 2600",
    "Canislupus_UAM_18197": "UAM 18197",
}


# %%
TIME_KEYS = [
    "decompress_wall_time_seconds",
    "decompress_user_time_seconds",
    "decompress_system_time_seconds",
    "compress_wall_time_seconds",
    "compress_user_time_seconds",
    "compress_system_time_seconds",
]
# The summaries have the wall times; CPU (user + system) only the JSON.
JSON_TIME_KEYS = [k for k in TIME_KEYS if "wall" not in k]


FLOAT_COLUMNS = ["psnr_db", "ssim_mean", "ms_ssim", "max_abs_error", "max_abs_error_u16_equivalent"]


def read_runs(runs: list[Path], pattern: str) -> pl.DataFrame:
    """Summary CSV rows, plus the CPU times that only the per-test JSON has."""
    frames = []
    for run_order, run in enumerate(runs):
        for file in sorted(run.glob(f"*/{pattern}")):
            summary = pl.read_csv(file, infer_schema_length=None).with_columns(
                # Numbers even when a run left them all empty (SSIMs not
                # computed), which would otherwise read as text.
                pl.col(c).cast(pl.Float64)
                for c in FLOAT_COLUMNS
                if c in pl.read_csv(file, n_rows=0).columns
            )
            times = pl.DataFrame(
                [
                    {"name": name} | {k: test[k] for k in JSON_TIME_KEYS}
                    for name in summary["name"]
                    for test in [json.loads((file.parent / f"test_{name}.json").read_text())]
                ]
            )
            frames.append(
                summary.join(times, on="name").with_columns(
                    dataset=pl.lit(file.parent.name),
                    run=pl.lit(run.name),
                    run_order=pl.lit(run_order),
                )
            )
    return (
        pl.concat(frames, how="diagonal_relaxed")
        .sort("run_order")
        .unique(["dataset", "name"], keep="last", maintain_order=True)
    )


dicom = read_runs(DICOM_RUNS, "summary.csv").with_columns(
    container=pl.lit("DICOM"),
    input_variant=pl.lit("u16_1000"),
)
zarr = read_runs(ZARR_RUNS, "summary_*.csv").rename(
    {"max_abs_error_u16_equivalent": "max_abs_error"}
).with_columns(container=pl.lit("OME-Zarr"))

COLUMNS = [
    "dataset",
    "run",
    "container",
    "series",
    "name",
    "input_variant",
    "was_actually_lossless",
    "compression_ratio",
    "psnr_db",
    "ssim_mean",
    "ms_ssim",
    "max_abs_error",
    *TIME_KEYS,
]
results = pl.concat([dicom.select(COLUMNS), zarr.select(COLUMNS)], how="vertical_relaxed")
results.group_by("container", "series").len().sort("container", "series")

# %%
# Codec family -> colour (fixed categorical order), and the variant within a
# family -> marker shape / line type.
FAMILIES = {
    "j2k": "JPEG 2000",
    "htj2k": "HTJ2K",
    "jpegls": "JPEG-LS",
    "jpegxl": "JPEG-XL",
    "lerc": "LERC",
    "sperr": "SPERR",
    # SZ3 per slice and on 3D chunks: two codecs here, not one with variants.
    "sz3_2d": "SZ3 (2D)",
    "sz3": "SZ3 (3D)",
    "zfp": "ZFP",
}
PALETTE = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]
# float32 differs from uint16 in both marker and line type.
VARIANTS = {
    "DICOM, uint16": ("s", "dashdot"),
    "OME-Zarr, uint16": ("o", "solid"),
    "OME-Zarr, uint16, 3D": ("D", "dotted"),
    "OME-Zarr, float32": ("^", "dashed"),
    # The same, for plots with OME-Zarr only, where the container goes unsaid.
    "uint16": ("o", "solid"),
    "float32": ("^", "dashed"),
}

family = (
    pl.when(pl.col("series") == "zarr-sz3-slice")
    .then(pl.lit("sz3_2d"))
    .otherwise(pl.col("series").str.split("-").list.get(1))
)
variant = (
    pl.when(pl.col("container") == "DICOM")
    .then(pl.lit("DICOM, uint16"))
    .when(pl.col("series") == "zarr-lerc-3d")
    # LERC on 3D chunks rather than slices.
    .then(pl.lit("OME-Zarr, uint16, 3D"))
    .when(pl.col("input_variant").str.starts_with("f32"))
    .then(pl.lit("OME-Zarr, float32"))
    .otherwise(pl.lit("OME-Zarr, uint16"))
)

lossy = (
    results.filter(~pl.col("was_actually_lossless"), pl.col("psnr_db").is_not_null())
    .with_columns(
        family=family.replace_strict(FAMILIES),
        variant=variant,
        dataset_label=pl.col("dataset").replace_strict(DATASET_LABELS),
        # SSIM in dB, as is common in the image compression literature: the
        # interesting range is 0.999...9, which a linear axis flattens.
        ssim_db=-10 * (1 - pl.col("ssim_mean")).log10(),
        ms_ssim_db=-10 * (1 - pl.col("ms_ssim")).log10(),
        # Max. absolute error as a fraction of the full uint16 range. For the
        # float32 inputs it is already in uint16 grey levels.
        linf=pl.col("max_abs_error") / np.iinfo(np.uint16).max,
        # Whole volume, 8 cores; CPU is user + system over every thread and
        # worker process.
        compress_wall=pl.col("compress_wall_time_seconds"),
        decompress_wall=pl.col("decompress_wall_time_seconds"),
        compress_cpu=pl.col("compress_user_time_seconds") + pl.col("compress_system_time_seconds"),
        decompress_cpu=pl.col("decompress_user_time_seconds") + pl.col("decompress_system_time_seconds"),
    )
    .with_columns(
        family=pl.col("family").cast(pl.Enum(list(FAMILIES.values()))),
        variant=pl.col("variant").cast(pl.Enum(list(VARIANTS))),
        dataset_label=pl.col("dataset_label").cast(pl.Enum(list(DATASET_LABELS.values()))),
    )
)
lossy.group_by("family", "variant").agg(pl.len(), pl.col("dataset").n_unique()).sort("family", "variant")

# %% [markdown]
# ## Pooling over datasets
#
# Each configuration is one point per dataset. Pool them into a mean with a 95 %
# confidence interval from the between-dataset variance, mean ± t(0.975, n−1)·s/√n
# (n = 3, so t = 4.30). Quantities shown on a log axis (compression ratio, max.
# error) are pooled in log space, i.e. a geometric mean with a multiplicative
# interval, so the bars are symmetric on the plot.

# %%
N_DATASETS = len(DATASET_LABELS)
T_95 = stats.t.ppf(0.975, N_DATASETS - 1)

METRICS = {
    "psnr_db": dict(label="PSNR (dB)", log=False),
    # dB: -10 log10(1 - SSIM); defined in the poster caption.
    "ssim_db": dict(label="SSIM (dB)", log=False),
    "ms_ssim_db": dict(label="MS-SSIM (dB)", log=False),
    "linf": dict(label=r"Normalised $\ell_\infty$ error", log=True),
    # Times in seconds read as numbers, not powers of ten. On two lines, to fit
    # the height of a stacked panel.
    "compress_wall": dict(label="Compression\ntime (s)", log=True, labels=None),
    "decompress_wall": dict(label="Decompression\ntime (s)", log=True, labels=None),
    "compress_cpu": dict(label="Compression\nCPU time (s)", log=True, labels=None),
    "decompress_cpu": dict(label="Decompression\nCPU time (s)", log=True, labels=None),
}
CONFIG_KEYS = ["container", "series", "name", "family", "variant"]

# JPEG-XL configurations shown filled in: those in the poster's error figure
# (2026-10-04_poster_jpegxl_errors.py), which re-encodes the runner's float32
# volume, so these are byte for byte its data.
HIGHLIGHT_DISTANCES = ["0.1", "1", "5"]
# Only in the error figure's dataset, so only in the per-specimen plots: a
# pooled point is a mean over specimens, not the data in the figure.
HIGHLIGHT_DATASET = "Canislupus_CZM_712"
highlighted = pl.col("name").str.contains(
    rf"^zarr_jpegxl_f32_d({'|'.join(d.replace('.', r'\.') for d in HIGHLIGHT_DISTANCES)})_"
) & (pl.col("dataset") == HIGHLIGHT_DATASET)


def pooled(df: pl.DataFrame, column: str, log: bool, prefix: str) -> list[pl.Expr]:
    """Mean and 95 % CI bounds of `column` over datasets, as `prefix`, `_lo`, `_hi`."""
    value = pl.col(column).log10() if log else pl.col(column)
    mean = value.mean()
    half = T_95 * value.std() / pl.len().sqrt()
    back = (lambda e: 10**e) if log else (lambda e: e)
    return [
        back(mean).alias(prefix),
        back(mean - half).alias(f"{prefix}_lo"),
        back(mean + half).alias(f"{prefix}_hi"),
    ]


def pool(df: pl.DataFrame, x: str, x_log: bool, y: str, y_log: bool) -> pl.DataFrame:
    return (
        df.filter(pl.col(x).is_finite(), pl.col(y).is_finite())
        .group_by(CONFIG_KEYS)
        .agg(pl.len().alias("n"), *pooled(df, x, x_log, "x"), *pooled(df, y, y_log, "y"))
        # Only configurations that ran on every dataset, otherwise the means
        # would mix specimens.
        .filter(pl.col("n") == N_DATASETS)
        .sort(CONFIG_KEYS)
    )


pool(lossy, "compression_ratio", True, "psnr_db", False).head()

# %%
# Poster: A0 portrait, two columns of 375 mm. Drawn at the true column width so
# the sizes below are printed sizes (poster body text is 32 pt).
FIG_WIDTH_IN = 375 / 25.4
FONT = "Liberation Sans"
INK = "#1a1a1a"
INK_MUTED = "#555555"
GRID = "#e1e0d9"
AXIS_TEXT_SIZE = 18

POSTER_THEME = theme_minimal(base_size=20, base_family=FONT) + theme(
    text=element_text(color=INK),
    axis_text=element_text(color=INK_MUTED, size=AXIS_TEXT_SIZE),
    axis_title=element_text(size=22),
    strip_text=element_text(size=22, weight="bold"),
    legend_title=element_text(size=20, weight="bold"),
    legend_text=element_text(size=18),
    legend_position="bottom",
    # Codec and pixel data type legends side by side, titles left of their entries.
    legend_box="horizontal",
    legend_title_position="left",
    legend_key_spacing_x=16,
    legend_key_spacing_y=0,
    legend_key_width=28,
    # Between the codec and pixel data type legends.
    legend_spacing=100,
    # Between the x axis title and the legend, in figure units (default 0.03).
    legend_box_spacing=0.01,
    legend_margin=0,
    panel_grid_major=element_line(color=GRID, size=0.6),
    panel_grid_minor=element_blank(),
    panel_border=element_rect(color="#c3c2b7", fill=None, size=0.8),
    plot_background=element_rect(fill="white", color="white"),
    panel_spacing_x=0.02,
)


def log_labels(breaks):
    return [f"$10^{{{np.log10(b):.0f}}}$" for b in breaks]


# On two lines: the legend is only just as wide as the column.
VARIANT_TITLE = "Container,\nData Type"


# The selected codecs: six of the eight palette slots, picked by hand. No six of
# them clear the all-pairs floors (validate_palette.js --pairs all), so the
# closest pairs (magenta/red 13.2, blue/violet 16.3, OKLab dE x100) go to codecs
# whose curves keep apart: JPEG-LS/JPEG-XL and JPEG 2000/SZ3 (3D).
SELECTED_COLORS = {
    "JPEG 2000": "#2a78d6",  # blue
    "HTJ2K": "#008300",  # green
    "JPEG-LS": "#e87ba4",  # magenta
    "JPEG-XL": "#e34948",  # red
    "SZ3 (2D)": "#eda100",  # yellow
    "SZ3 (3D)": "#4a3aa7",  # violet
}
COLORS_BY_FAMILIES = {frozenset(SELECTED_COLORS): SELECTED_COLORS}


# Lowest compression ratio shown: below it are the near-lossless settings, which
# stretch the y axes for little.
CR_MIN = 7


def rd_scales(metric: str, caption: str, variant_title: str, data: pl.DataFrame, x_max: float) -> list:
    """Scales, labels and theme shared by the pooled and per-specimen plots."""
    spec = METRICS[metric]
    # The palette's slots in order over the codecs present, so a selection of
    # codecs gets evenly spread colours rather than the gaps of the full set.
    families = [f for f in FAMILIES.values() if f in set(data["family"].unique().to_list())]
    colors = COLORS_BY_FAMILIES.get(frozenset(families), dict(zip(families, PALETTE)))
    n_families, n_variants = len(families), data["variant"].n_unique()
    return [
        # Error bars reaching below the limit are cut at the axis.
        # Fixed breaks: with the lower limit, a narrow panel can be left with a
        # single automatic one, which mizani's minor breaks cannot handle.
        # An explicit upper limit too: with None, plotnine resolves the log
        # range wrongly and squishes every point onto one x.
        scale_x_log10(limits=(CR_MIN, x_max), oob=squish, breaks=[10, 30, 100, 300, 1000], minor_breaks=[]),
        scale_color_manual(values=colors),
        scale_fill_manual(values=colors, guide=None),
        scale_shape_manual(values={k: v[0] for k, v in VARIANTS.items()}),
        scale_linetype_manual(values={k: v[1] for k, v in VARIANTS.items()}),
        (
            scale_y_log10(labels=spec.get("labels", log_labels) or (lambda breaks: [f"{b:g}" for b in breaks]))
            if spec["log"]
            else scale_y_continuous()
        ),
        labs(
            x="Compression Ratio",
            y=spec["label"],
            color="Codec",
            shape=variant_title,
            linetype=variant_title,
            caption=caption,
        ),
        # Filled column by column: plotnine only aligns the entries into a grid
        # that way, by row it packs each row on its own.
        guides(
            # All codecs and variants in two rows would be wider than the column.
            color=guide_legend(nrow=2 if n_families <= 6 else 3),
            shape=guide_legend(nrow=2 if n_variants <= 2 else n_variants),
            linetype=guide_legend(nrow=2 if n_variants <= 2 else n_variants),
        ),
        # A copy: `p += theme(...)` updates the plot's theme in place, which
        # would otherwise leak into every other plot through POSTER_THEME.
        copy.deepcopy(POSTER_THEME),
        theme(plot_caption=element_text(size=16, color=INK_MUTED)),
    ]


def to_pandas(df: pl.DataFrame, like: pl.DataFrame | None = None):
    """With only the categories present in `like` (default `df`), in enum order.

    Absent ones would still be listed in the legend. Every layer of a plot must
    get the same categories, or plotnine splits the shape and line-type legends.
    """
    like = df if like is None else like
    out = df.to_pandas()
    for column in ["family", "variant"]:
        present = set(like[column].unique().to_list())
        order = [c for c in df[column].dtype.categories.to_list() if c in present]
        out[column] = pd.Categorical(out[column].astype(str), categories=order, ordered=True)
    return out


def rd_plot(metric: str, data: pl.DataFrame, variant_title: str = VARIANT_TITLE) -> ggplot:
    """Pooled over specimens, with 95 % CIs."""
    spec = METRICS[metric]
    df = pool(data, "compression_ratio", True, metric, spec["log"]).filter(pl.col("x") >= CR_MIN)
    p = (
        ggplot(to_pandas(df), aes("x", "y", color="family", group="series"))
        + geom_errorbar(aes(ymin="y_lo", ymax="y_hi"), width=0.025, size=0.7, alpha=0.8)
        + geom_errorbarh(aes(xmin="x_lo", xmax="x_hi"), height=0.0, size=0.6, alpha=0.5)
        + geom_line(aes(linetype="variant"), size=1.2)
        + geom_point(aes(shape="variant"), size=3.5, fill="white", stroke=1.2)
    )
    for layer in rd_scales(
        metric,
        f"Mean over {N_DATASETS} specimens, bars: 95 % CI",
        variant_title,
        data,
        # From the whole selection, not this metric, so stacked panels align.
        pool(data, "compression_ratio", True, "psnr_db", False)["x_hi"].max(),
    ):
        p += layer
    return p


def rd_plot_by_specimen(metric: str, data: pl.DataFrame, variant_title: str = VARIANT_TITLE) -> ggplot:
    """One panel per specimen, side by side."""
    df = data.filter(pl.col(metric).is_finite(), pl.col("compression_ratio") >= CR_MIN)
    p = (
        ggplot(to_pandas(df), aes("compression_ratio", metric, color="family", group="series"))
        + geom_line(aes(linetype="variant"), size=1.2)
        + geom_point(aes(shape="variant"), size=3.5, fill="white", stroke=1.2)
        + geom_point(aes(shape="variant", fill="family"), data=to_pandas(df.filter(highlighted), like=df), size=4.5, stroke=1.2, show_legend=False)
        + facet_wrap("dataset_label", nrow=1)
    )
    for layer in rd_scales(metric, None, variant_title, data, data["compression_ratio"].max()):
        p += layer
    return p


# %%
# Every plot below is made for each of these codec selections, into its own
# subfolder.
# Selected: no DICOM, and none of these codecs. Everything left is OME-Zarr, so
# the variants are just the pixel data type.
EXCLUDED = ["LERC", "SPERR", "ZFP"]
selected = (
    lossy.filter(pl.col("container") != "DICOM", ~pl.col("family").is_in(EXCLUDED))
    .with_columns(
        variant=pl.col("variant")
        .cast(pl.String)
        .str.strip_prefix("OME-Zarr, ")
        .cast(pl.Enum(list(VARIANTS)))
    )
)
SELECTIONS = {
    # Without SZ3 (2D): nine codecs would be one more than the palette has.
    "all_codecs": (lossy.filter(pl.col("family") != "SZ3 (2D)"), VARIANT_TITLE),
    "selected_codecs": (selected, "Data\nType"),
}
for selection in SELECTIONS:
    (PLOT_DIR / selection).mkdir(exist_ok=True)

for selection, (data, variant_title) in SELECTIONS.items():
    for metric in METRICS:
        p = rd_plot(metric, data, variant_title) + theme(figure_size=(FIG_WIDTH_IN, 6))
        p.save(PLOT_DIR / selection / f"rd_{metric}.svg", verbose=False)

        p = rd_plot_by_specimen(metric, data, variant_title) + theme(figure_size=(FIG_WIDTH_IN, 5.4))
        p.save(PLOT_DIR / selection / f"rd_{metric}_by_specimen.svg", verbose=False)


# %% [markdown]
# ## Stacked metrics
#
# Several metrics above each other on a shared compression-ratio axis. Only the
# bottom plot keeps the x axis, legend and caption; only the top one keeps the
# specimen strips.

# %%
def rd_stack(metrics: list[str], data: pl.DataFrame, variant_title: str, by_specimen: bool) -> Compose:
    make = rd_plot_by_specimen if by_specimen else rd_plot
    plots = []
    for i, metric in enumerate(metrics):
        p = make(metric, data, variant_title)
        if i < len(metrics) - 1:
            p += theme(
                legend_position="none",
                axis_title_x=element_blank(),
                axis_text_x=element_blank(),
                plot_caption=element_blank(),
            )
        if i > 0 and by_specimen:
            p += theme(strip_text=element_blank())
        plots.append(p)
    return Stack(plots)


STACKS = {
    "psnr_db+linf": (["psnr_db", "linf"], 8.0),
    "ms_ssim_db+linf": (["ms_ssim_db", "linf"], 8.0),
    "ms_ssim_db+linf+psnr_db": (["ms_ssim_db", "linf", "psnr_db"], 10.5),
    "compress_wall+decompress_wall": (["compress_wall", "decompress_wall"], 8.0),
    "compress_cpu+decompress_cpu": (["compress_cpu", "decompress_cpu"], 8.0),
}
for selection, (data, variant_title) in SELECTIONS.items():
    for stack_name, (metrics, height) in STACKS.items():
        for by_specimen, suffix in [(False, ""), (True, "_by_specimen")]:
            c = rd_stack(metrics, data, variant_title, by_specimen) + theme(figure_size=(FIG_WIDTH_IN, height))
            c.save(PLOT_DIR / selection / f"rd_stack_{stack_name}{suffix}.svg")

rd_plot("psnr_db", lossy) + theme(figure_size=(FIG_WIDTH_IN, 6))

# %% [markdown]
# ## Half-column versions
#
# Two specimens, half the column width, y axis on the right. Selected codecs
# only: the legend of all eight does not fit in half a column.

# %%
HALF_SPECIMENS = ["Canislupus_CZM_712", "Canislupus_BM_2600"]
HALF_WIDTH_IN = FIG_WIDTH_IN / 2
HALF_THEME = theme(
    # Legend groups closer, to fit under the narrower panels.
    legend_spacing=12,
    legend_key_spacing_x=4,
)
HALF_VARIANT_TITLE = "Data\nType"
# Codecs in three rows: five in two rows are wider than half a column.
HALF_GUIDES = guides(color=guide_legend(nrow=3))


def y_axis_right(fig, pad_pt: float = 6):
    """Move the y axis (ticks, labels, title) of a drawn plotnine figure to the right.

    plotnine cannot place it there itself. This runs after plotnine's own
    layout on every draw, then narrows the panels from the right to make room,
    keeping the left margin as wide as the right one was. Strips and panel
    backgrounds move with their axes and the x title stays centred on the
    panels. The legend stays centred on the figure: it is wider than the panels.
    """
    engine = fig.get_layout_engine()
    plotnine_execute = engine.execute

    def execute(f):
        plotnine_execute(f)
        # Whatever renderer this draw uses (SVG has no canvas renderer).
        renderer = f._get_renderer()
        to_fig = f.transFigure.inverted()

        def extent(artist):
            return to_fig.transform_bbox(artist.get_window_extent(renderer))

        panels = [a for a in f.axes if a.get_visible()]
        rows: dict[float, list] = {}
        for a in panels:
            rows.setdefault(round(a.get_position().y0, 4), []).append(a)

        tick_width = 0.0
        for row in rows.values():
            rightmost = max(row, key=lambda a: a.get_position().x1)
            for a in row:
                a.tick_params(axis="y", which="both", left=False, labelleft=False, labelright=a is rightmost)
                for tick in a.yaxis.get_major_ticks():
                    # The right labels are not themed: style them as POSTER_THEME
                    # styles axis text (plotnine themes the left ones later on).
                    tick.label2.set_text(tick.label1.get_text())
                    tick.label2.set_fontfamily(FONT)
                    tick.label2.set_fontsize(AXIS_TEXT_SIZE)
                    tick.label2.set_color(INK_MUTED)
                    tick.label2.set_horizontalalignment("left")
                    tick.label2.set_visible(a is rightmost)
                    if a is rightmost and tick.label2.get_text():
                        tick_width = max(tick_width, extent(tick.label2).width)

        left = min(a.get_position().x0 for a in panels)
        right = max(a.get_position().x1 for a in panels)
        margin = 1 - right
        pad = pad_pt / 72 / f.get_figwidth()
        y_titles = [t for t in f.texts if t.get_rotation() == 90]
        title_width = max((extent(t).width for t in y_titles), default=0)

        new_left, new_right = margin, 1 - margin - tick_width - title_width - 2 * pad
        scale = (new_right - new_left) / (right - left)

        def map_x(x):
            return new_left + (x - left) * scale

        for a in panels:
            b = a.get_position()
            a.set_position([map_x(b.x0), b.y0, b.width * scale, b.height])

        for t in y_titles:
            t.set_x(new_right + tick_width + 2 * pad)
            t.set_horizontalalignment("left")

        # The x title, centred on the panels.
        for t in f.texts:
            if t.get_rotation() == 0:
                b = extent(t)
                centre = (b.x0 + b.x1) / 2
                if left <= centre <= right:
                    t.set_x(t.get_position()[0] + map_x(centre) - centre)
        for artist in f.artists:
            if type(artist).__name__ == "FlexibleAnchoredOffsetbox":
                b = extent(artist)
                dx = (0.5 - (b.x0 + b.x1) / 2) * f.bbox.width
                anchor = artist.get_bbox_to_anchor()
                artist.set_bbox_to_anchor(
                    Bbox.from_extents(anchor.x0 + dx, anchor.y0, anchor.x1 + dx, anchor.y1)
                )

    engine.execute = execute
    return fig


def save_y_right(plot, path: Path):
    fig = plot.draw()
    y_axis_right(fig)
    fig.savefig(path)


half_data, _ = SELECTIONS["selected_codecs"]
half_data = half_data.filter(pl.col("dataset").is_in(HALF_SPECIMENS))
half_dir = PLOT_DIR / "selected_codecs_half"
half_dir.mkdir(exist_ok=True)

for metric in METRICS:
    p = rd_plot_by_specimen(metric, half_data, HALF_VARIANT_TITLE) + HALF_THEME + HALF_GUIDES + theme(
        figure_size=(HALF_WIDTH_IN, 5.4)
    )
    save_y_right(p, half_dir / f"rd_{metric}_by_specimen.svg")

for stack_name, (metrics, height) in STACKS.items():
    c = rd_stack(metrics, half_data, HALF_VARIANT_TITLE, by_specimen=True)
    for plot in c:
        plot += HALF_THEME
        plot += HALF_GUIDES
    save_y_right(c + theme(figure_size=(HALF_WIDTH_IN, height)), half_dir / f"rd_stack_{stack_name}_by_specimen.svg")

# %% [markdown]
# ## Lossless: compression ratio against decompression time
#
# CPU time is user + system over every thread and worker process; wall time is
# with 8 cores. Both decode the full 1000³ volume (2 GB as u16).

# %%
LOSSLESS_LABELS = {
    "dicom-j2k": "DICOM JPEG 2000",
    "dicom-jpegls": "DICOM JPEG-LS",
    "zarr-pcodec-u16": "OME-Zarr Pcodec, u16",
    "zarr-pcodec-f32": "OME-Zarr Pcodec, f32",
}
LOSSLESS_COLORS = {
    "DICOM JPEG 2000": PALETTE[0],
    "DICOM JPEG-LS": PALETTE[2],
    "OME-Zarr Pcodec, u16": "#52514e",
    "OME-Zarr Pcodec, f32": "#52514e",
}
LOSSLESS_SHAPES = {
    "DICOM JPEG 2000": "s",
    "DICOM JPEG-LS": "s",
    "OME-Zarr Pcodec, u16": "o",
    "OME-Zarr Pcodec, f32": "^",
}
CLOCKS = {"cpu": "CPU time", "wall": "Wall time (8 cores)"}

lossless = (
    results.filter(pl.col("was_actually_lossless"))
    .with_columns(
        family=pl.col("series").replace_strict(LOSSLESS_LABELS),
        variant=pl.lit(None, pl.String),
        cpu=pl.col("decompress_user_time_seconds") + pl.col("decompress_system_time_seconds"),
        wall=pl.col("decompress_wall_time_seconds"),
    )
    .unpivot(on=list(CLOCKS), index=[*CONFIG_KEYS, "dataset", "compression_ratio"], variable_name="clock", value_name="seconds")
    .with_columns(clock=pl.col("clock").replace_strict(CLOCKS))
)
lossless_pooled = pl.concat(
    [
        pool(lossless.filter(pl.col("clock") == clock), "seconds", True, "compression_ratio", False).with_columns(
            clock=pl.lit(clock)
        )
        for clock in CLOCKS.values()
    ]
).with_columns(clock=pl.col("clock").cast(pl.Enum(list(CLOCKS.values()))))
lossless_pooled.select("family", "clock", "x", "x_lo", "x_hi", "y", "y_lo", "y_hi")

# %%
p = (
    ggplot(lossless_pooled.to_pandas(), aes("x", "y", color="family", shape="family"))
    + geom_point(
        aes("seconds", "compression_ratio"),
        data=lossless.with_columns(clock=pl.col("clock").cast(pl.Enum(list(CLOCKS.values())))).to_pandas(),
        size=2.5,
        alpha=0.35,
    )
    + geom_errorbar(aes(ymin="y_lo", ymax="y_hi"), width=0.03, size=0.8)
    + geom_errorbarh(aes(xmin="x_lo", xmax="x_hi"), height=0.0, size=0.8)
    + geom_point(size=4.5, fill="white", stroke=1.4)
    # Labels to the right of each point; JPEG-LS raised to clear the JPEG 2000 marker.
    + geom_text(
        aes(label="family"),
        data=lossless_pooled.filter(pl.col("family") != "DICOM JPEG-LS").to_pandas(),
        nudge_x=0.09, size=16, family=FONT, color=INK, ha="left", va="center",
    )
    + geom_text(
        aes(label="family"),
        data=lossless_pooled.filter(pl.col("family") == "DICOM JPEG-LS").to_pandas(),
        nudge_x=0.09, nudge_y=0.15, size=16, family=FONT, color=INK, ha="left", va="center",
    )
    + facet_wrap("clock", nrow=1)
    # Room on the right for the labels.
    + scale_x_log10(limits=(1, 2000))
    + scale_color_manual(values=LOSSLESS_COLORS)
    + scale_shape_manual(values=LOSSLESS_SHAPES)
    + labs(
        x="Decompression time for the full volume (s)",
        y="Compression Ratio",
        caption=f"Mean over {N_DATASETS} specimens (faint: each specimen), bars: 95 % CI",
    )
    + POSTER_THEME
    + theme(
        legend_position="none",
        plot_caption=element_text(size=16, color=INK_MUTED),
        figure_size=(FIG_WIDTH_IN, 4.8),
    )
)
p.save(PLOT_DIR / "lossless_cr_vs_decompression_time.svg", verbose=False)
p
