# %%
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import tifffile
from matplotlib.patches import Rectangle
from tqdm.auto import tqdm

from comptest.configurations import TIFFFILE_JPEGXL_LOSSY_CONFIGS_EFFORT_7_BIG
from comptest.constants import DATASETS_RECONSTRUCTIONS_DIR, PROJECT_SCRATCH_DIR
from comptest.image_transform import DataTransform

# %load_ext autoreload
# %autoreload 2

# %%
RECONSTRUCTION = "CIL_basic_binned_2x2"
DATASET = "Canislupus_CZM_712"

DISTANCES = [0.1, 1.0, 5.0]
N_JOBS = None
FORCE_RECOMPUTE = False

# Planes through the volume (nz, ny, nx).
Z_INDEX = 500  # z slice -> (ny, nx), the compressed plane
X_INDEX = 500  # x slice -> (nz, ny), across the compressed direction

# (left, upper, right, lower). For the x slice, upper/lower are z bounds.
Z_CROP_AREA = (560, 630, 560 + 60, 630 + 50)
Z_OVERVIEW_CROP_AREA = (300, 250, 850, 750)
X_CROP_AREA = (650, 630, 650 + 60, 630 + 50)
X_OVERVIEW_CROP_AREA = (300, 250, 850, 750)

# %%
DATASET_DIR = DATASETS_RECONSTRUCTIONS_DIR / RECONSTRUCTION / DATASET
assert DATASET_DIR.is_dir()

INPUT_FILES = sorted(
    [
        *DATASET_DIR.glob("*.tif"),
        *DATASET_DIR.glob("*.tiff"),
    ]
)

# Several GB per distance, so this lives on the project scratch, not in the repo.
WORK_DIR = PROJECT_SCRATCH_DIR / "quality_viewer_stack" / RECONSTRUCTION / DATASET
TRANSFORMED_DIR = WORK_DIR / "transformed"
TRANSFORMED_DIR.mkdir(exist_ok=True, parents=True)

OUT_DIR = (
    Path().resolve()
    / ".."
    / "output"
    / "quality_viewer"
    / DATASET
    / "stack_orthoslices"
).resolve()
OUT_DIR.mkdir(exist_ok=True, parents=True)

TRANSFORMED_FILES = [TRANSFORMED_DIR / f"{f.stem}.tiff" for f in INPUT_FILES]

print(f"{len(INPUT_FILES)} slices, work dir {WORK_DIR}")

# %%
CONFIGS = {
    cfg.distance: cfg
    for cfg in TIFFFILE_JPEGXL_LOSSY_CONFIGS_EFFORT_7_BIG
    if cfg.distance in DISTANCES
}

assert set(CONFIGS) == set(DISTANCES)

# %%
# One transform for the whole stack: per-slice maxima span ~0.003 to ~0.19 here, so
# per-slice normalisation would put a different quantisation step on every slice.
TRANSFORM_PATH = WORK_DIR / "transform.json"

if TRANSFORM_PATH.is_file() and not FORCE_RECOMPUTE:
    transform = DataTransform.model_validate_json(TRANSFORM_PATH.read_text())
else:
    data_min, data_max = np.inf, -np.inf

    for file in tqdm(INPUT_FILES, desc="range"):
        arr = tifffile.imread(file)
        data_min = min(data_min, float(arr.min()))
        data_max = max(data_max, float(arr.max()))

    transform = DataTransform.infer(
        np.array([data_min, data_max]), target_range=(0, 1.0)
    )
    TRANSFORM_PATH.write_text(transform.model_dump_json(indent=2))

print(transform)

# %%
for input_file, transformed_file in tqdm(
    list(zip(INPUT_FILES, TRANSFORMED_FILES, strict=True)), desc="transform"
):
    if transformed_file.is_file() and not FORCE_RECOMPUTE:
        continue

    # float32: what the imagecodecs JPEG XL float path accepts.
    arr = transform.apply(tifffile.imread(input_file)).astype(np.float32)
    tifffile.imwrite(transformed_file, arr)

# %%
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
def load_stack(files, desc="load"):
    first = tifffile.imread(files[0])
    volume = np.empty((len(files), *first.shape), dtype=first.dtype)
    volume[0] = first

    for i, file in enumerate(tqdm(files[1:], desc=desc), start=1):
        volume[i] = tifffile.imread(file)

    return volume


def orthoslices(volume):
    # Copies, not views, so the volume can be freed afterwards.
    return {
        "z": volume[Z_INDEX, :, :].copy(),
        "x": volume[:, :, X_INDEX].copy(),
    }


# %%
reference = load_stack(TRANSFORMED_FILES, desc="reference")
reference_slices = orthoslices(reference)

slices_by_distance = {}
slice_rmse = {}

for distance in DISTANCES:
    decompressed = load_stack(decompressed_files[distance], desc=f"d={distance:g}")
    slices_by_distance[distance] = orthoslices(decompressed)
    # Per slice, to avoid materialising a float64 copy of the whole volume.
    slice_rmse[distance] = np.array(
        [
            np.sqrt(np.square(dec.astype(np.float64) - ref).mean())
            for dec, ref in zip(decompressed, reference, strict=True)
        ]
    )
    del decompressed

# %%
summary = pl.DataFrame(
    [
        {
            "distance": distance,
            "effort": CONFIGS[distance].effort,
            "compressed_mb": sum(f.stat().st_size for f in compressed_files[distance])
            / 1e6,
            "ratio": sum(f.stat().st_size for f in TRANSFORMED_FILES)
            / sum(f.stat().st_size for f in compressed_files[distance]),
            "rmse": float(np.sqrt(np.square(slice_rmse[distance]).mean())),
            "psnr_db": float(
                20 * np.log10(1.0 / np.sqrt(np.square(slice_rmse[distance]).mean()))
            ),
        }
        for distance in DISTANCES
    ]
)
summary.write_csv(OUT_DIR / "stack_summary.csv")
print(summary)


# %%
def plot_quality_comparison(
    original,
    decompressed_by_distance,
    crop_area,
    *,
    overview_crop_area=None,
    title=None,
    vmin=0.0,
    vmax=1.0,
    diff_percentile=99.5,
):
    """
    Parameters
    ----------
    original
        Full 2D reference plane.
    decompressed_by_distance
        Mapping from JPEG XL distance to decompressed 2D plane.
    crop_area
        Zoom area as (left, upper, right, lower), in full-plane coordinates.
    overview_crop_area
        Area of the original displayed in the overview panel, also in
        full-plane coordinates. It must contain crop_area.
    """
    original = np.asarray(original)

    if original.ndim != 2:
        raise ValueError(f"Expected a 2D original image, got shape {original.shape}")

    height, width = original.shape

    def validate_area(area, name):
        left, upper, right, lower = map(int, area)

        if not (0 <= left < right <= width and 0 <= upper < lower <= height):
            raise ValueError(f"{name} {area} is outside image shape {original.shape}")

        return left, upper, right, lower

    (
        zoom_left,
        zoom_upper,
        zoom_right,
        zoom_lower,
    ) = validate_area(crop_area, "crop_area")

    if overview_crop_area is None:
        overview_left = 0
        overview_upper = 0
        overview_right = width
        overview_lower = height
    else:
        (
            overview_left,
            overview_upper,
            overview_right,
            overview_lower,
        ) = validate_area(
            overview_crop_area,
            "overview_crop_area",
        )

    if not (
        overview_left <= zoom_left < zoom_right <= overview_right
        and overview_upper <= zoom_upper < zoom_lower <= overview_lower
    ):
        raise ValueError("crop_area must be completely inside overview_crop_area")

    original_overview = original[
        overview_upper:overview_lower,
        overview_left:overview_right,
    ]

    original_zoom = original[
        zoom_upper:zoom_lower,
        zoom_left:zoom_right,
    ]
    original_zoom_float = original_zoom.astype(np.float64)

    comparisons = []

    for distance, decompressed in decompressed_by_distance.items():
        decompressed = np.asarray(decompressed)

        if decompressed.shape != original.shape:
            raise ValueError(
                f"Distance {distance:g} has shape {decompressed.shape}; "
                f"expected {original.shape}"
            )

        decompressed_zoom = decompressed[
            zoom_upper:zoom_lower,
            zoom_left:zoom_right,
        ]

        difference = decompressed_zoom.astype(np.float64) - original_zoom_float

        comparisons.append((distance, decompressed_zoom, difference))

    if not comparisons:
        raise ValueError("No decompressed images were supplied")

    absolute_differences = np.concatenate(
        [np.abs(difference).ravel() for _, _, difference in comparisons]
    )
    finite_differences = absolute_differences[np.isfinite(absolute_differences)]

    diff_limit = (
        np.percentile(finite_differences, diff_percentile)
        if finite_differences.size
        else 1.0
    )

    if not np.isfinite(diff_limit) or diff_limit <= 0:
        diff_limit = 1.0

    nrows = len(comparisons) + 1

    # The third GridSpec column is reserved for the colorbar. This prevents
    # the colorbar from resizing or shifting the error-image column.
    fig = plt.figure(
        figsize=(10, 4.0 * nrows),
    )

    grid = fig.add_gridspec(
        nrows=nrows,
        ncols=3,
        width_ratios=(1, 1, 0.025),
        left=0.02,
        right=0.97,
        bottom=0.02,
        top=0.955,
        wspace=0.02,
        hspace=0.10,
    )

    axes = np.empty((nrows, 2), dtype=object)

    for row in range(nrows):
        axes[row, 0] = fig.add_subplot(grid[row, 0])
        axes[row, 1] = fig.add_subplot(grid[row, 1])

    colorbar_axis = fig.add_subplot(grid[1:, 2])

    # Original zoom on the left.
    axes[0, 0].imshow(
        original_zoom,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        aspect="equal",
    )
    axes[0, 0].set_title("Original zoom")

    # Cropped original overview on the right.
    axes[0, 1].imshow(
        original_overview,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        aspect="equal",
    )

    # Convert the zoom position from full-image coordinates to coordinates
    # relative to the cropped overview.
    outline_left = zoom_left - overview_left
    outline_upper = zoom_upper - overview_upper

    axes[0, 1].add_patch(
        Rectangle(
            (outline_left - 0.5, outline_upper - 0.5),
            zoom_right - zoom_left,
            zoom_lower - zoom_upper,
            fill=False,
            edgecolor="red",
            linewidth=2,
        )
    )
    axes[0, 1].set_title("Original")

    difference_image = None

    for row, (distance, decompressed_zoom, difference) in enumerate(
        comparisons,
        start=1,
    ):
        axes[row, 0].imshow(
            decompressed_zoom,
            cmap="viridis",
            vmin=vmin,
            vmax=vmax,
            aspect="equal",
        )
        axes[row, 0].set_title(f"Distance = {distance:g}")

        difference_image = axes[row, 1].imshow(
            difference,
            cmap="RdBu_r",
            vmin=-diff_limit,
            vmax=diff_limit,
            aspect="equal",
        )
        axes[row, 1].set_title(f"Difference — Distance = {distance:g}")

    for axis in axes.flat:
        axis.set_axis_off()
        axis.set_anchor("N")

    fig.colorbar(
        difference_image,
        cax=colorbar_axis,
        label="Pixel difference (data range 0–1)",
    )

    if title is not None:
        fig.suptitle(title, y=0.995, va="top")

    return fig, axes


def planes(name):
    return {d: slices_by_distance[d][name] for d in DISTANCES}


# %%
# z slice: the plane JPEG XL actually sees.
fig, axes = plot_quality_comparison(
    reference_slices["z"],
    planes("z"),
    Z_CROP_AREA,
    overview_crop_area=Z_OVERVIEW_CROP_AREA,
    title=f"z slice (z = {Z_INDEX}), the compressed plane",
)
fig.savefig("2026-09-01_jpegxl_quality_z.png", dpi=300, bbox_inches="tight")

# %%
# x slice: every row comes from a different, independently compressed slice.
fig, axes = plot_quality_comparison(
    reference_slices["x"],
    planes("x"),
    X_CROP_AREA,
    overview_crop_area=X_OVERVIEW_CROP_AREA,
    title=f"x slice (x = {X_INDEX}), across the compressed direction",
)
fig.savefig("2026-09-01_jpegxl_quality_x.png", dpi=300, bbox_inches="tight")

# %%
