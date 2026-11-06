# %% [markdown]
# # Rate-distortion of one codec, two ways
#
# For the QIM WG presentation, from the poster's `summary.csv`: OME-Zarr
# rate-distortion curves of a pair of variants of one codec.
#
# - JPEG-XL on the float32 reconstruction against its uint16 quantisation. The
#   float32 curve lies on the uint16 one: keeping float32 costs nothing at a
#   given quality. Comparable as is: the compression ratio of both is against
#   the 2 GB uint16 volume, and PSNR and the max. error of float32 are in
#   uint16-equivalent units (full range 65535).
# - SZ3 slice by slice (2D) against on 3D chunks, both on float32: how much a 2D
#   codec leaves on the table on a 3D volume. Same error bound, so same max.
#   error at each tolerance; 3D gets there at a higher compression ratio.

# %%
import copy
from pathlib import Path

import numpy as np
import polars as pl
from plotnine import (
    aes,
    element_blank,
    element_line,
    element_rect,
    element_text,
    facet_wrap,
    geom_line,
    geom_point,
    ggplot,
    labs,
    scale_color_manual,
    scale_linetype_manual,
    scale_shape_manual,
    scale_x_log10,
    scale_y_continuous,
    scale_y_log10,
    theme,
    theme_minimal,
)
from plotnine.composition import Stack

# %%
# A notebook has no __file__, and its working directory is notebooks/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
SUMMARY_FILE = PROJECT_DIR / "docs" / "poster_D3A_4_0" / "assets" / "summary.csv"
PLOT_DIR = PROJECT_DIR / "docs" / "presentation_qim_wg_2026-11-06" / "assets"

DATASET_LABELS = {
    "Canislupus_CZM_712": "CZM 712",
    "Canislupus_BM_2600": "BM 2600",
    "Canislupus_UAM_18197": "UAM 18197",
}
# Colour, marker and line type of the first and second variant of a pair.
STYLES = [("#2a78d6", "o", "solid"), ("#e34948", "^", "dashed")]

# Each pair: its series in summary.csv -> legend label, the parameter that runs
# along a curve, the smallest value of it shown, and the x axis breaks.
COMPARISONS = {
    "jpegxl_f32_vs_u16": dict(
        series={"zarr-jpegxl-u16": "uint16", "zarr-jpegxl-f32": "float32"},
        legend_title="Data Type",
        parameter="distance",
        parameter_min=0.0,
        x_breaks=[10, 30, 100, 300],
    ),
    "sz3_2d_vs_3d": dict(
        series={"zarr-sz3-slice": "2D", "zarr-sz3": "3D"},
        legend_title="SZ3",
        parameter="tolerance",
        # Without the two near-lossless tolerances (4e-6, 5e-5; CR 2-5), which
        # stretch the PSNR axis to 111 dB, as the poster's CR ≥ 7 cut does.
        parameter_min=3e-4,
        x_breaks=[10, 30, 100],
    ),
}

# Drawn at the size it is shown, so the font sizes below are the sizes on the
# slide: `height: 80%` of the slide body (167 mm 16:9 page less the theme's
# 2.2 cm top and 1 cm bottom margins) in one of two columns.
FIG_SIZE_IN = (4.5, 0.8 * (167.06 - 22 - 10) / 25.4)
FONT = "Liberation Sans"
INK = "#1a1a1a"
INK_MUTED = "#555555"
GRID = "#e1e0d9"

METRICS = {
    "psnr_db": ("PSNR (dB)", False),
    "linf_normalised": (r"Normalised $\ell_\infty$ error", True),
}
N_DATASETS = len(DATASET_LABELS)

# %%
# Full-file schema inference: codec-specific columns are empty in the first rows.
summary = pl.read_csv(SUMMARY_FILE, infer_schema_length=None).filter(
    ~pl.col("was_actually_lossless")
)


def load(comparison: str) -> pl.DataFrame:
    """The pair's rows, with `variant` its legend label and `parameter` along a curve."""
    spec = COMPARISONS[comparison]
    return (
        summary.filter(
            pl.col("series").is_in(list(spec["series"])),
            pl.col(spec["parameter"]) >= spec["parameter_min"],
        )
        .with_columns(
            variant=pl.col("series")
            .replace_strict(spec["series"])
            .cast(pl.Enum(list(spec["series"].values()))),
            parameter=pl.col(spec["parameter"]),
            dataset_label=pl.col("dataset")
            .replace_strict(DATASET_LABELS)
            .cast(pl.Enum(list(DATASET_LABELS.values()))),
        )
        .sort("dataset_label", "variant", "parameter")
    )


DATA = {comparison: load(comparison) for comparison in COMPARISONS}
for comparison, df in DATA.items():
    # Every parameter value for both variants on every specimen.
    counts = df.group_by("variant", "parameter").len()["len"]
    assert (counts == N_DATASETS).all(), comparison
    print(comparison, df.height, "rows")

# %% [markdown]
# ## Pooling over specimens
#
# Per variant and parameter value, the mean over the specimens. Quantities on a
# log axis (compression ratio, max. error) are averaged in log space, i.e. a
# geometric mean, as in the poster's pooled plots. No error bars: they clutter
# plots whose point is how two curves lie relative to each other.


# %%
def mean(column: str, log: bool) -> pl.Expr:
    return 10 ** pl.col(column).log10().mean() if log else pl.col(column).mean()


def pool(df: pl.DataFrame, metric: str) -> pl.DataFrame:
    return (
        df.group_by("variant", "parameter")
        .agg(
            mean("compression_ratio", True).alias("x"),
            mean(metric, METRICS[metric][1]).alias("y"),
        )
        .sort("variant", "parameter")
    )


pool(DATA["sz3_2d_vs_3d"], "psnr_db")

# %%
# Slide body text is 20 pt and captions 16 pt.
THEME = theme_minimal(base_size=14, base_family=FONT) + theme(
    text=element_text(color=INK),
    axis_text=element_text(color=INK_MUTED, size=13),
    axis_title=element_text(size=16),
    strip_text=element_text(size=14, weight="bold"),
    legend_title=element_text(size=14, weight="bold"),
    legend_text=element_text(size=14),
    legend_position="bottom",
    legend_title_position="left",
    legend_key_spacing_x=10,
    legend_key_width=24,
    legend_box_spacing=0.01,
    legend_margin=0,
    panel_grid_major=element_line(color=GRID, size=0.6),
    panel_grid_minor=element_blank(),
    panel_border=element_rect(color="#c3c2b7", fill=None, size=0.8),
    plot_background=element_rect(fill="white", color="white"),
    panel_spacing_x=0.02,
)


def rd_plot(comparison: str, metric: str, by_specimen: bool) -> ggplot:
    spec = COMPARISONS[comparison]
    df = DATA[comparison]
    label, log = METRICS[metric]
    if by_specimen:
        p = (
            ggplot(df.to_pandas(), aes("compression_ratio", metric, color="variant", group="variant"))
            + facet_wrap("dataset_label", nrow=1)
        )
    else:
        p = ggplot(pool(df, metric).to_pandas(), aes("x", "y", color="variant", group="variant"))
    y_scale = (
        # Decades only: the automatic 3·10^n breaks would read as 10^n.
        scale_y_log10(
            breaks=[10.0**e for e in range(-6, 1)],
            minor_breaks=[],
            labels=lambda breaks: [f"$10^{{{np.log10(b):.0f}}}$" for b in breaks],
        )
        if log
        else scale_y_continuous()
    )
    variants = list(spec["series"].values())
    title = spec["legend_title"]
    return (
        p
        + geom_line(aes(linetype="variant"), size=0.9)
        + geom_point(aes(shape="variant"), size=2.5, fill="white", stroke=1.0)
        + scale_x_log10(
            # Decades only on the narrow per-specimen panels, where the 3·10^n crowd.
            breaks=[b for b in spec["x_breaks"] if not by_specimen or np.log10(b).is_integer()],
            minor_breaks=[],
        )
        + y_scale
        + scale_color_manual(values={v: s[0] for v, s in zip(variants, STYLES)})
        + scale_shape_manual(values={v: s[1] for v, s in zip(variants, STYLES)})
        + scale_linetype_manual(values={v: s[2] for v, s in zip(variants, STYLES)})
        + labs(x="Compression Ratio", y=label, color=title, shape=title, linetype=title)
        # A copy: `+ theme(...)` below would otherwise change THEME in place.
        + copy.deepcopy(THEME)
    )


def rd_stack(comparison: str, by_specimen: bool) -> Stack:
    """PSNR above max. error, sharing the compression-ratio axis."""
    top = rd_plot(comparison, "psnr_db", by_specimen) + theme(
        legend_position="none",
        axis_title_x=element_blank(),
        axis_text_x=element_blank(),
    )
    bottom = rd_plot(comparison, "linf_normalised", by_specimen) + theme(strip_text=element_blank())
    return Stack([top, bottom]) + theme(figure_size=FIG_SIZE_IN)


# One per specimen, and pooled over them.
for comparison in COMPARISONS:
    for by_specimen, suffix in [(False, ""), (True, "_by_specimen")]:
        path = PLOT_DIR / f"rd_stack_{comparison}{suffix}.svg"
        rd_stack(comparison, by_specimen).save(path)

rd_stack("sz3_2d_vs_3d", by_specimen=False)
