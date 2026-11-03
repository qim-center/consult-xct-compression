# %% [markdown]
# # Lossless compression ratio against compression time
#
# The tall plot of 2026-08-11_lossless_plot_tall.ipynb, for the QIM WG
# presentation, with the lossless configurations of the poster's `summary.csv`.
#
# Not comparable with the original: that one is the 12.6 GB TIFF projection stack
# of one specimen, this one the reconstructed 1000³ volumes of three.

# %%
from pathlib import Path

import polars as pl
from plotnine import (
    aes,
    element_blank,
    element_line,
    element_rect,
    element_text,
    geom_point,
    geom_text,
    ggplot,
    guide_legend,
    guides,
    labs,
    scale_color_manual,
    scale_shape_manual,
    scale_x_continuous,
    scale_y_continuous,
    theme,
    theme_minimal,
)

# %%
# A notebook has no __file__, and its working directory is notebooks/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
SUMMARY_FILE = PROJECT_DIR / "docs" / "poster_D3A_4_0" / "assets" / "summary.csv"
PLOT_FILE = (
    PROJECT_DIR
    / "docs"
    / "presentation_qim_wg_2026-11-06"
    / "assets"
    / "2026-11-02_lossless_plot_tall.svg"
)

FONT = "Liberation Sans"
INK = "#5c5c5c"
INK_MUTED = "#747474"
GRID = "#e1e0d9"

# Colors and shapes of the poster's lossless plot, but for Pcodec, which is a hue
# rather than gray here.
LABELS = {
    "dicom-j2k": "DICOM JPEG 2000",
    "dicom-jpegls": "DICOM JPEG-LS",
    "zarr-pcodec-u16": "OME-Zarr Pcodec, u16",
    "zarr-pcodec-f32": "OME-Zarr Pcodec, f32",
}
COLORS = {
    "DICOM JPEG 2000": "#2a78d6",
    "DICOM JPEG-LS": "#1baf7a",
    "OME-Zarr Pcodec, u16": "#4a3aa7",
    "OME-Zarr Pcodec, f32": "#4a3aa7",
}
SHAPES = {
    "DICOM JPEG 2000": "s",
    "DICOM JPEG-LS": "s",
    "OME-Zarr Pcodec, u16": "o",
    "OME-Zarr Pcodec, f32": "^",
}
# Position and alignment of each direct label, clear of the points.
LABEL_POSITIONS = [
    ("DICOM JPEG 2000", 2.62, 165, "center"),
    ("DICOM JPEG-LS", 2.66, 45, "center"),
    ("OME-Zarr Pcodec, u16", 2.36, 14, "center"),
    ("OME-Zarr Pcodec, f32", 1.04, 40, "left"),
]

# %%
# Full-file schema inference: codec-specific columns are empty in the first rows.
lossless = (
    pl.read_csv(SUMMARY_FILE, infer_schema_length=None)
    .filter(pl.col("was_actually_lossless"))
    .with_columns(configuration=pl.col("series").replace_strict(LABELS))
    .with_columns(pl.col("configuration").cast(pl.Enum(list(LABELS.values()))))
)
assert lossless.height == 12
lossless.select("configuration", "dataset", "compression_ratio", "compress_cpu_time_seconds")

# %%
labels = pl.DataFrame(
    LABEL_POSITIONS,
    schema=["configuration", "x", "y", "ha"],
    orient="row",
).with_columns(pl.col("configuration").cast(pl.Enum(list(LABELS.values()))))

p = (
    ggplot(
        lossless.to_pandas(),
        aes(
            "compression_ratio",
            "compress_cpu_time_seconds",
            color="configuration",
            shape="configuration",
        ),
    )
    + geom_point(size=4, alpha=0.85)
    + geom_text(
        aes("x", "y", label="configuration", ha="ha"),
        data=labels.to_pandas(),
        size=12,
        family=FONT,
        color=INK,
        show_legend=False,
    )
    + scale_x_continuous(limits=(1, 3), breaks=[1, 1.5, 2, 2.5, 3])
    + scale_y_continuous(limits=(0, 175), breaks=range(0, 176, 25))
    + scale_color_manual(values=COLORS)
    + scale_shape_manual(values=SHAPES)
    + labs(
        title="Lossless Compression Analysis   —   Best: Bottom right",
        x="Compression ratio",
        y="Compression CPU time (seconds)",
        color="Configuration",
        shape="Configuration",
        caption=(
            "One point per specimen, 3 volumes of 1000³ voxels. CPU time is user + system.\n"
            "Ratios are against the 2 GB uint16 volume, for f32 too."
        ),
    )
    + guides(color=guide_legend(nrow=2), shape=guide_legend(nrow=2))
    + theme_minimal(base_size=13, base_family=FONT)
    + theme(
        figure_size=(6, 9),
        dpi=300,
        text=element_text(color=INK),
        axis_text=element_text(color=INK_MUTED),
        plot_title=element_text(size=14),
        plot_caption=element_text(size=10, color=INK_MUTED),
        legend_position="bottom",
        legend_title_position="top",
        panel_grid_major=element_line(color=GRID, size=0.6),
        panel_grid_minor=element_blank(),
        panel_border=element_rect(color="#c3c2b7", fill=None, size=0.8),
        plot_background=element_rect(fill="white", color="white"),
    )
)
p.save(PLOT_FILE, verbose=False)
p
