# %%
from concurrent.futures import ThreadPoolExecutor
import matplotlib.pyplot as plt
import numpy as np
import tifffile
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import ConnectionPatch, Rectangle
from tqdm.auto import tqdm

from comptest.configurations import TIFFFILE_JPEGXL_LOSSY_CONFIGS_EFFORT_7_BIG
from comptest.constants import PROJECT_SCRATCH_DIR

# %load_ext autoreload
# %autoreload 2

# %%
RECONSTRUCTION = "CIL_basic_binned_2x2"
DATASET = "Canislupus_CZM_712"

DISTANCES = [0.1, 1.0, 5.0]
N_JOBS = None
N_READ_THREADS = 8
FORCE_RECOMPUTE = False

# Planes through the volume (nz, ny, nx).
Z_INDEX = 500  # z slice -> (ny, nx), the compressed plane
X_INDEX = 500  # x slice -> (nz, ny), across the compressed direction

# (left, upper, right, lower). For the x slice, upper/lower are z bounds.
Z_CROP_AREA = (560, 630, 560 + 60, 630 + 50)
Z_OVERVIEW_CROP_AREA = (300, 250, 850, 750)
X_CROP_AREA = (650, 630, 650 + 60, 630 + 50)
X_OVERVIEW_CROP_AREA = (300, 250, 850, 750)

# Compression ratios are quoted against a 16-bit uncompressed baseline, as in the
# poster, not against the float32 files that are actually compressed.
BASELINE_BYTES_PER_VOXEL = 2

# %%
# Poster: A0 portrait, 30 mm side margins, two columns with the default 4% gutter.
# The figure is drawn at the true column width, so include it at `width: 100%`
# and the font sizes below are the printed sizes (poster body text is 32 pt).
FIG_WIDTH_MM = 375

PRIMARY = "#990000"  # DTU corporate red, rgb(153, 0, 0)
INK = "#1a1a1a"
INK_MUTED = "#555555"
FRAME = "#9a9a9a"

FONT = "Liberation Sans"  # poster body font
SIZE_TITLE = 28
SIZE_SUBTITLE = 24
SIZE_TICK = 20
LINE_WIDTH = 2.5

# Diverging: DTU blue darkened to the lightness of corporate red (OKLab L ~ 0.43),
# a neutral light grey midpoint, and stops interpolated in OKLab.
ERROR_CMAP = LinearSegmentedColormap.from_list(
    "dtu_diverging",
    [
        "#2636c0",
        "#4f6cd1",
        "#829adf",
        "#b8c6ea",
        "#f2f2f2",
        "#e2bdb6",
        "#ce887d",
        "#b65245",
        "#990000",
    ],
)

plt.rcParams.update(
    {
        "font.family": FONT,
        "text.color": INK,
        "axes.labelcolor": INK,
        "ytick.color": INK_MUTED,
        "ytick.labelcolor": INK,
    }
)

# %%
WORK_DIR = PROJECT_SCRATCH_DIR / "quality_viewer_stack" / RECONSTRUCTION / DATASET
TRANSFORMED_DIR = WORK_DIR / "transformed"
CACHE_DIR = WORK_DIR / "poster_planes"
CACHE_DIR.mkdir(exist_ok=True, parents=True)

TRANSFORMED_FILES = sorted(TRANSFORMED_DIR.glob("*.tiff"))
assert TRANSFORMED_FILES, (
    f"No transformed slices in {TRANSFORMED_DIR}; "
    "run 2026-09-01_lossy_jpegxl_stack_orthoslices.py first"
)

print(f"{len(TRANSFORMED_FILES)} slices, work dir {WORK_DIR}")

# %%
CONFIGS = {
    cfg.distance: cfg
    for cfg in TIFFFILE_JPEGXL_LOSSY_CONFIGS_EFFORT_7_BIG
    if cfg.distance in DISTANCES
}

assert set(CONFIGS) == set(DISTANCES)

# %%
# Same layout as the 2026-09-01 notebook, so its outputs are reused.
compressed_files = {}
decompressed_files = {}

for distance, cfg in CONFIGS.items():
    compressed_dir = WORK_DIR / "compressed" / cfg.name
    decompressed_dir = WORK_DIR / "decompressed" / cfg.name
    compressed_dir.mkdir(exist_ok=True, parents=True)
    decompressed_dir.mkdir(exist_ok=True, parents=True)

    compressed_files[distance] = [compressed_dir / f.name for f in TRANSFORMED_FILES]
    decompressed_files[distance] = [
        decompressed_dir / f.name for f in TRANSFORMED_FILES
    ]

    for func_args, sources, destinations in (
        (cfg.compressor, TRANSFORMED_FILES, compressed_files[distance]),
        (cfg.decompressor, compressed_files[distance], decompressed_files[distance]),
    ):
        todo = [
            (src, dst)
            for src, dst in zip(sources, destinations, strict=True)
            if FORCE_RECOMPUTE or not dst.is_file()
        ]

        if not todo:
            continue

        print(f"{cfg.name}: {len(todo)} files -> {destinations[0].parent.parent.name}")
        func, args, kwargs = func_args
        func(
            [src for src, _ in todo],
            [dst for _, dst in todo],
            *args,
            **kwargs | {"n_jobs": N_JOBS},
        )


# %%
def read_planes(name, files, reference_files=None):
    """
    Stream a stack once, keeping only the z and x planes and, against a
    reference stack, the summed squared error. Cached, as a full pass reads
    several GB.
    """
    cache_path = CACHE_DIR / f"{name}_z{Z_INDEX}_x{X_INDEX}.npz"

    if cache_path.is_file() and not FORCE_RECOMPUTE:
        cached = np.load(cache_path)
        return {key: cached[key] for key in cached.files}

    def read_one(i):
        arr = tifffile.imread(files[i])
        squared_error = (
            np.square(
                arr.astype(np.float64) - tifffile.imread(reference_files[i])
            ).sum()
            if reference_files is not None
            else 0.0
        )
        return arr[:, X_INDEX].copy(), squared_error

    with ThreadPoolExecutor(N_READ_THREADS) as pool:
        results = list(
            tqdm(pool.map(read_one, range(len(files))), total=len(files), desc=name)
        )

    first = tifffile.imread(files[0])
    planes = {
        "z": tifffile.imread(files[Z_INDEX]),
        "x": np.stack([column for column, _ in results]),
        "squared_error": np.array(sum(se for _, se in results)),
        "n_voxels": np.array(len(files) * first.size),
    }
    np.savez(cache_path, **planes)

    return planes


# %%
reference = read_planes("reference", TRANSFORMED_FILES)

decoded = {
    distance: read_planes(
        CONFIGS[distance].name, decompressed_files[distance], TRANSFORMED_FILES
    )
    for distance in DISTANCES
}

# %%
stats = {}

for distance, planes in decoded.items():
    rmse = float(np.sqrt(planes["squared_error"] / planes["n_voxels"]))
    compressed_bytes = sum(f.stat().st_size for f in compressed_files[distance])
    stats[distance] = {
        "ratio": int(planes["n_voxels"]) * BASELINE_BYTES_PER_VOXEL / compressed_bytes,
        # Transformed data spans 0-1, so this is PSNR against full scale.
        "psnr_db": 20 * np.log10(1.0 / rmse),
    }
    print(
        f"d={distance:g}: CR {stats[distance]['ratio']:.1f}:1, "
        f"PSNR {stats[distance]['psnr_db']:.1f} dB"
    )


# %%
def plot_poster_errors(
    original,
    decompressed_by_distance,
    subtitles,
    crop_area,
    overview_crop_area,
    *,
    window_percentiles=(0.5, 99.9),
    diff_percentile=99.5,
):
    """
    One column per image (original first), two rows: overview with the zoom
    area marked, and the zoom area. For the compressed images, the right half
    of the zoom shows the signed error instead of the image.

    Parameters
    ----------
    original
        Full 2D reference plane, data range 0-1.
    decompressed_by_distance
        Mapping from JPEG XL distance to decompressed 2D plane.
    subtitles
        Mapping from JPEG XL distance to the second header line.
    crop_area, overview_crop_area
        (left, upper, right, lower) in full-plane coordinates. The zoom area
        must lie inside the overview area.
    """
    zl, zu, zr, zb = crop_area
    ol, ou, or_, ob = overview_crop_area
    assert ol <= zl < zr <= or_ and ou <= zu < zb <= ob

    # Zoom columns [0, split) show the image, [split, zoom width) the error.
    split = (zr - zl) // 2

    def zoom(image):
        return image[zu:zb, zl:zr]

    def overview(image):
        return image[ou:ob, ol:or_]

    original_overview = overview(original)
    overview_window = np.percentile(original_overview, window_percentiles)
    zoom_window = np.percentile(zoom(original), window_percentiles)

    # Percent of full scale, on one scale for all distances so they compare.
    errors = {
        distance: 100 * (zoom(dec).astype(np.float64) - zoom(original))[:, split:]
        for distance, dec in decompressed_by_distance.items()
    }
    error_limit = np.percentile(
        np.abs(np.concatenate([e.ravel() for e in errors.values()])), diff_percentile
    )

    columns = [
        ("Original", "(uncompressed)", original, None),
        *(
            (f"JPEG XL, d = {distance:g}", subtitles[distance], dec, errors[distance])
            for distance, dec in decompressed_by_distance.items()
        ),
    ]

    # Geometry in mm, laid out by hand so the figure width is exact.
    pad, col_gap, zoom_gap, header = 1.5, 6.0, 14.0, 24.0
    cbar_width, cbar_labels = 7.0, 30.0  # bar, then tick labels and label
    ncols = len(columns)
    width = (
        FIG_WIDTH_MM
        - 2 * pad
        - ncols * col_gap
        - cbar_width
        - cbar_labels
    ) / ncols
    h_overview = width * original_overview.shape[0] / original_overview.shape[1]
    h_zoom = width * (zb - zu) / (zr - zl)
    height = header + h_overview + zoom_gap + h_zoom + pad

    fig = plt.figure(figsize=(FIG_WIDTH_MM / 25.4, height / 25.4))

    def add_axes(x, top, w, h):
        # x and top in mm from the left and top edges.
        return fig.add_axes(
            (x / FIG_WIDTH_MM, 1 - (top + h) / height, w / FIG_WIDTH_MM, h / height)
        )

    def frame(axis, color):
        axis.set_xticks([])
        axis.set_yticks([])
        for spine in axis.spines.values():
            spine.set_edgecolor(color)
            spine.set_linewidth(LINE_WIDTH)

    top_overview = header
    top_zoom = top_overview + h_overview + zoom_gap

    for col, (title, subtitle, image, error) in enumerate(columns):
        x = pad + col * (width + col_gap)

        fig.text(
            (x + width / 2) / FIG_WIDTH_MM,
            1 - 2 / height,
            title,
            ha="center",
            va="top",
            fontsize=SIZE_TITLE,
            fontweight="bold",
        )
        fig.text(
            (x + width / 2) / FIG_WIDTH_MM,
            1 - (header - 4) / height,
            subtitle,
            ha="center",
            va="bottom",
            fontsize=SIZE_SUBTITLE,
            color=INK_MUTED,
        )

        ax_overview = add_axes(x, top_overview, width, h_overview)
        ax_overview.imshow(
            overview(image),
            cmap="gray",
            vmin=overview_window[0],
            vmax=overview_window[1],
            interpolation="nearest",
        )
        ax_overview.set_axis_off()
        ax_overview.add_patch(
            Rectangle(
                (zl - ol - 0.5, zu - ou - 0.5),
                zr - zl,
                zb - zu,
                fill=False,
                edgecolor=PRIMARY,
                linewidth=LINE_WIDTH,
            )
        )

        ax_zoom = add_axes(x, top_zoom, width, h_zoom)
        zoom_image = zoom(image) if error is None else zoom(image)[:, :split]
        ax_zoom.imshow(
            zoom_image,
            cmap="gray",
            vmin=zoom_window[0],
            vmax=zoom_window[1],
            interpolation="nearest",
            extent=(-0.5, zoom_image.shape[1] - 0.5, zb - zu - 0.5, -0.5),
        )

        if error is not None:
            error_image = ax_zoom.imshow(
                error,
                cmap=ERROR_CMAP,
                vmin=-error_limit,
                vmax=error_limit,
                interpolation="nearest",
                extent=(split - 0.5, zr - zl - 0.5, zb - zu - 0.5, -0.5),
            )
            # Surface-coloured gap between the image and error halves.
            ax_zoom.axvline(split - 0.5, color="white", linewidth=LINE_WIDTH)

        ax_zoom.set_xlim(-0.5, zr - zl - 0.5)
        ax_zoom.set_ylim(zb - zu - 0.5, -0.5)
        frame(ax_zoom, PRIMARY)

        # Lead lines from the marked area down to the zoom panel.
        for corner_x, frac_x in ((zl - ol - 0.5, 0), (zr - ol - 0.5, 1)):
            fig.add_artist(
                ConnectionPatch(
                    xyA=(corner_x, zb - ou - 0.5),
                    coordsA=ax_overview.transData,
                    xyB=(frac_x, 1),
                    coordsB=ax_zoom.transAxes,
                    color=PRIMARY,
                    linewidth=LINE_WIDTH / 2,
                )
            )

    cax = add_axes(
        pad + ncols * (width + col_gap),
        top_overview,
        cbar_width,
        top_zoom + h_zoom - top_overview,
    )
    colorbar = fig.colorbar(error_image, cax=cax)
    colorbar.outline.set_visible(False)
    tick = float(np.floor(error_limit)) or float(f"{error_limit:.1g}")
    ticks = [-tick, -tick / 2, 0, tick / 2, tick]
    colorbar.set_ticks(ticks, labels=[f"{t:g}".replace("-", "\u2212") for t in ticks])
    colorbar.ax.tick_params(labelsize=SIZE_TICK, length=6, width=1.5)
    colorbar.set_label(
        "Error (% of full scale)",
        fontsize=SIZE_SUBTITLE,
        labelpad=8,
    )

    return fig


subtitles = {
    distance: f"{s['ratio']:.1f} : 1, {s['psnr_db']:.1f} dB"
    for distance, s in stats.items()
}

# %%
# z slice: the plane JPEG XL actually sees.
fig = plot_poster_errors(
    reference["z"],
    {d: decoded[d]["z"] for d in DISTANCES},
    subtitles,
    Z_CROP_AREA,
    Z_OVERVIEW_CROP_AREA,
)
fig.savefig("2026-10-04_poster_jpegxl_errors_z.png", dpi=600)

# %%
# x slice: every row comes from a different, independently compressed slice.
fig = plot_poster_errors(
    reference["x"],
    {d: decoded[d]["x"] for d in DISTANCES},
    subtitles,
    X_CROP_AREA,
    X_OVERVIEW_CROP_AREA,
)
fig.savefig("2026-10-04_poster_jpegxl_errors_x.png", dpi=600)

# %%
