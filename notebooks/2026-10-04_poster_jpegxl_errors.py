# %%
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imagecodecs.zarr as codecs
import matplotlib.pyplot as plt
import numpy as np
import tifffile
import zarr
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import ConnectionPatch, Rectangle
from tqdm.auto import tqdm

from comptest.constants import PROJECT_SCRATCH_DIR, RECONSTRUCTIONS_TRANSFORMED_DIR

# %load_ext autoreload
# %autoreload 2

# %%
# The float32 input of the OME-Zarr runs, so the figure shows the very volume
# and codestreams behind the rate-distortion plots.
INPUT_VARIANT = "f32_1000"
DATASET = "Canislupus_CZM_712"
# As the rate-distortion plots name it.
DATASET_LABEL = DATASET.removeprefix("Canislupus_").replace("_", " ")

DISTANCES = [0.1, 1.0, 5.0]
JPEGXL_EFFORT = 7
N_READ_THREADS = 8
FORCE_RECOMPUTE = False

# Planes through the volume (nz, ny, nx).
Z_INDEX = 500  # z slice -> (ny, nx), the compressed plane
X_INDEX = 500  # x slice -> (nz, ny), across the compressed direction

# (left, upper, right, lower). For the x slice, upper/lower are z bounds.
Z_CROP_AREA = (575, 630, 575 + 60, 630 + 50)
Z_OVERVIEW_CROP_AREA = (300, 250, 850, 750)
X_CROP_AREA = (650, 630, 650 + 60, 630 + 50)
X_OVERVIEW_CROP_AREA = (300, 250, 850, 750)

# Compression ratios are quoted against a 16-bit uncompressed baseline, as in the
# poster and the runner, not against the float32 volume that is compressed.
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
# The rate-distortion plots' sizes: strip titles 22 bold, axis titles 22, axis
# and legend text 18.
SIZE_TITLE = 22
SIZE_SUBTITLE = 18
SIZE_LABEL = 22
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
# A notebook has no __file__, and its working directory is notebooks/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
# SVG: the images inside are still raster, resampled (nearest) at the savefig
# dpi, so each data pixel stays a sharp square.
POSTER_PLOT_DIR = NOTEBOOK_DIR.parent / "docs" / "poster_D3A_4_0" / "assets" / "plots"

INPUT_DIR = RECONSTRUCTIONS_TRANSFORMED_DIR / INPUT_VARIANT / DATASET
INPUT_FILES = sorted(INPUT_DIR.glob("slice_z*.tif"))
assert INPUT_FILES, f"No slices in {INPUT_DIR}"

CACHE_DIR = PROJECT_SCRATCH_DIR / "poster_jpegxl_errors" / INPUT_VARIANT / DATASET
CACHE_DIR.mkdir(exist_ok=True, parents=True)

# Results of the OME-Zarr runner, to check the codestreams against.
ZARR_RESULTS_DIR = NOTEBOOK_DIR.parent / "output" / "zarr"

print(f"{len(INPUT_FILES)} slices from {INPUT_DIR}")

# %% [markdown]
# ## Compression
#
# Exactly as `data_gathering/02b_zarr_compression_tests.py` compresses its
# `zarr_jpegxl_f32_d{d}_e7` configurations: the same input volume, one chunk per
# slice in 50-slice shards, the JPEG XL serializer with the same settings and no
# compressor after it. Each chunk is encoded single-threaded, so the result does
# not depend on zarr's thread count, and the compressed size has to match the
# runner's to the byte.

# %%
JPEGXL_KWARGS = {
    "effort": JPEGXL_EFFORT,
    "photometric": "GRAY",
    "transfer": "LINEAR",
    "numthreads": 1,
}
SHARD_DEPTH = 50

codecs.register_codecs(verbose=False)


def config_name(distance: float) -> str:
    return f"zarr_jpegxl_f32_d{distance:g}_e{JPEGXL_EFFORT}"


def runner_compressed_size(distance: float) -> int | None:
    """compressed_size the runner recorded for this distance, latest run first."""
    files = sorted(
        ZARR_RESULTS_DIR.glob(f"quality_*/{DATASET}/test_{config_name(distance)}.json")
    )
    if not files:
        return None
    return json.loads(files[-1].read_text())["compressed_size"]


_volume = None


def volume() -> np.ndarray:
    """The input volume, read once and only if something is not cached."""
    global _volume

    if _volume is None:
        first = tifffile.imread(INPUT_FILES[0])
        _volume = np.empty((len(INPUT_FILES), *first.shape), dtype=first.dtype)

        def read_one(z):
            _volume[z] = tifffile.imread(INPUT_FILES[z])

        with ThreadPoolExecutor(N_READ_THREADS) as pool:
            list(tqdm(pool.map(read_one, range(len(INPUT_FILES))), total=len(INPUT_FILES), desc="input"))

    return _volume


def cached(name, compute):
    path = CACHE_DIR / f"{name}_z{Z_INDEX}_x{X_INDEX}.npz"

    if path.is_file() and not FORCE_RECOMPUTE:
        loaded = np.load(path)
        return {key: loaded[key] for key in loaded.files}

    result = compute()
    np.savez(path, **result)
    return result


def reference_planes():
    vol = volume()
    return {
        "z": vol[Z_INDEX].copy(),
        "x": vol[:, :, X_INDEX].copy(),
        # The runner's PSNR is against the volume's own range.
        "data_range": np.array(float(vol.max()) - float(vol.min())),
    }


def decoded_planes(distance: float):
    vol = volume()
    _, y, x = vol.shape
    store: dict = {}
    array = zarr.create_array(
        store=zarr.storage.MemoryStore(store),
        shape=vol.shape,
        dtype=vol.dtype,
        chunks=(1, y, x),
        shards=(SHARD_DEPTH, y, x),
        serializer=codecs.Jpegxl(**JPEGXL_KWARGS, distance=distance),
        # An empty list, not None: None would leave zarr's default zstd in place.
        compressors=[],
    )
    array[:] = vol
    compressed_size = int(array.nbytes_stored())
    decoded = array[:]

    return {
        "z": decoded[Z_INDEX].copy(),
        "x": decoded[:, :, X_INDEX].copy(),
        # In slabs: the whole volume in float64 would be another 8 GB, twice.
        "squared_error": np.array(
            sum(
                np.square(decoded[z : z + SHARD_DEPTH].astype(np.float64) - vol[z : z + SHARD_DEPTH]).sum()
                for z in range(0, len(vol), SHARD_DEPTH)
            )
        ),
        "n_voxels": np.array(vol.size),
        "compressed_size": np.array(compressed_size),
    }


# %%
reference = cached("reference", reference_planes)
decoded = {
    distance: cached(config_name(distance), lambda d=distance: decoded_planes(d))
    for distance in DISTANCES
}

for distance, planes in decoded.items():
    expected = runner_compressed_size(distance)
    size = int(planes["compressed_size"])
    if expected is None:
        print(f"d={distance:g}: {size} B, no runner result to compare with")
    else:
        assert size == expected, f"d={distance:g}: {size} B, runner had {expected} B"
        print(f"d={distance:g}: {size} B, identical to the runner")

# %%
stats = {}

for distance, planes in decoded.items():
    rmse = float(np.sqrt(planes["squared_error"] / planes["n_voxels"]))
    stats[distance] = {
        "ratio": int(planes["n_voxels"]) * BASELINE_BYTES_PER_VOXEL
        / int(planes["compressed_size"]),
        "psnr_db": 20 * np.log10(float(reference["data_range"]) / rmse),
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
        (DATASET_LABEL, f"(original, {INPUT_VARIANT.split('_')[0].replace('f', 'float')})", original, None),
        *(
            (f"JPEG XL, d = {distance:g}", subtitles[distance], dec, errors[distance])
            for distance, dec in decompressed_by_distance.items()
        ),
    ]

    # Geometry in mm, laid out by hand so the figure width is exact.
    pad, col_gap, zoom_gap, header = 1.5, 6.0, 14.0, 20.0
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
        fontsize=SIZE_LABEL,
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
fig.savefig(POSTER_PLOT_DIR / "jpegxl_errors_z.svg", dpi=600)

# %%
# x slice: every row comes from a different, independently compressed slice.
fig = plot_poster_errors(
    reference["x"],
    {d: decoded[d]["x"] for d in DISTANCES},
    subtitles,
    X_CROP_AREA,
    X_OVERVIEW_CROP_AREA,
)
fig.savefig(POSTER_PLOT_DIR / "jpegxl_errors_x.svg", dpi=600)

# %%
