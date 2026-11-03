# %% [markdown]
# # Zarr lossless compression tests
#
# The lossless counterpart of `02b_zarr_compression_tests.py`: the same volumes,
# chunk layouts, in-memory stores and `CompressionTest` JSON per configuration, for
# the lossless settings of the codecs in that study and of the TIFF codecs in
# `archive/projection_file_stack_compression.ipynb`. The TIFF codecs run as Zarr
# codecs through imagecodecs, once each, rather than through libtiff, ImageMagick
# and tifffile as they did there.
#
# Every configuration is checked for a bit-exact round trip. SSIM and MS-SSIM are
# not computed: they say nothing about a lossless result. A configuration that is
# not exact after all gets its PSNR and maximum error, and a warning.
#
# As in `02b`, every compression ratio is against the *uint16* volume's size, so
# that all configurations share one bytes axis. A float32 volume holds twice the
# bytes, so its ratio against what the configuration actually read is in
# `runner_extra.compression_ratio_vs_input`.
#
# Compressed arrays are not kept.

# %%
import importlib.metadata
import json
import logging
import os
import resource
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from pprint import pformat
from time import perf_counter
from typing import Any

import imagecodecs
import numpy as np
import polars as pl
import tifffile
import zarr
import zarr.storage

from comptest import metrics
from comptest.configurations import (
    efforts_deflate,
    efforts_jpegxl,
    efforts_lerc,
    efforts_lzma,
    efforts_png,
    efforts_zstd,
)
from comptest.constants import RECONSTRUCTIONS_TRANSFORMED_DIR
from comptest.types import (
    DTYPE_UINT8_UINT16,
    CompressionTest,
    ZarrCompressionConfig,
)

# %load_ext autoreload
# %autoreload 2

# %% [markdown]
# # Parameters

# %% [markdown]
# Every parameter below can be overridden through a `COMPTEST_` environment
# variable, which is how `03b_submit_zarr_lossless_tests.sh` drives batch runs.
# Left alone, the defaults are what an interactive run uses.


# %%
def _env_str(name: str, default: str) -> str:
    return os.environ.get(f"COMPTEST_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(f"COMPTEST_{name}")

    if value is None or not value.strip():
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int | None) -> int | None:
    value = os.environ.get(f"COMPTEST_{name}")

    if value is None or not value.strip():
        return default

    return int(value)


def _env_list(name: str, default: list[str] | None) -> list[str] | None:
    """Comma- or whitespace-separated; an empty variable means "unset"."""
    value = os.environ.get(f"COMPTEST_{name}")

    if value is None or not value.strip():
        return default

    return value.replace(",", " ").split()


# %%
reverse_configs: bool = _env_bool("REVERSE_CONFIGS", False)
# Codec families (see FAMILIES below) to run; None = all that are available.
codec_families: list[str] | None = _env_list("CODEC_FAMILIES", None)
# Config names (e.g. zarr_jpegls_near000) to run within those; None = all.
target_configs: list[str] | None = _env_list("TARGET_CONFIGS", None)
run_id: str = _env_str("RUN_ID", "none")
# Set by the LSF jobscript; only controls whether memory is released at the end.
is_batch: bool = _env_bool("IS_BATCH", "LSB_JOBID" in os.environ)

# %%
DATASET = _env_str("DATASET", "Canislupus_CZM_712")
# Subdirectories of RECONSTRUCTIONS_TRANSFORMED_DIR. U16_VARIANT is what DICOM
# reads, and its size is the denominator of every compression ratio.
U16_VARIANT = _env_str("U16_VARIANT", "u16_1000")
F32_VARIANT = _env_str("F32_VARIANT", "f32_1000")

# Cut the volume down to the first N slices for a quick smoke test. None = all.
# Keep it a multiple of both shard depths (50 and 40) so no shard is padded.
Z_LIMIT: int | None = _env_int("Z_LIMIT", None)

# Codec threads zarr may use. Defaults to the cores LSF gave the job, or else the
# cores this process may run on — not the machine's CPU count, which on a shared
# node is not what the job was given.
N_THREADS: int = _env_int(
    "N_THREADS",
    int(os.environ.get("LSB_DJOB_NUMPROC", len(os.sched_getaffinity(0)))),
)

TEST_CATEGORY = _env_str("TEST_CATEGORY", "lossless")

# %%
# zarr sizes its thread pool from this setting the first time it needs the pool,
# and never resizes it: it must be set before zarr does any work.
zarr.config.set({"threading.max_workers": N_THREADS})

import imagecodecs.zarr as codecs  # noqa: E402

codecs.register_codecs(verbose=False)

print(f"zarr threading.max_workers: {zarr.config.get('threading.max_workers')}")

# %% [markdown]
# # Setup


# %%
def configure_logging(log_file: Path) -> tuple[logging.Logger, Path]:
    configured_logger = logging.getLogger(__name__)
    configured_logger.setLevel(logging.DEBUG)
    configured_logger.propagate = False

    # Avoid duplicate handlers when cells are rerun.
    for handler in list(configured_logger.handlers):
        if getattr(handler, "_compression_notebook_handler", False):
            configured_logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)
    stdout_handler._compression_notebook_handler = True

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler._compression_notebook_handler = True

    configured_logger.addHandler(stdout_handler)
    configured_logger.addHandler(file_handler)

    return configured_logger, log_file


# %%
# A notebook has no __file__, and its working directory is data_gathering/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
assert OUTPUT_DIR.is_dir()


def input_files(variant: str) -> list[Path]:
    dataset_dir = RECONSTRUCTIONS_TRANSFORMED_DIR / variant / DATASET
    assert dataset_dir.is_dir(), f"{dataset_dir} does not exist"

    files = sorted(dataset_dir.glob("slice_z*.tif"))
    assert files, f"No slices found in {dataset_dir}"

    return files if Z_LIMIT is None else files[:Z_LIMIT]


# The chunk layouts depend on it, so it is read before the configurations; the
# float variant is checked against it once loaded.
_u16_files = input_files(U16_VARIANT)
with tifffile.TiffFile(_u16_files[0]) as tif:
    INPUT_SHAPE = (len(_u16_files), *tif.pages[0].shape)

print(f"Volume shape {INPUT_SHAPE}")

# %% [markdown]
# # Configurations
#
# The grids were cut down on one 40-slice slab of `Canislupus_CZM_712`, dropping
# settings that cost a lot and gain next to nothing: JPEG XL effort 9, LZMA levels
# 2-5, DEFLATE level 12, Zstd level 19, Pcodec level 12, and most LERC subcodec
# levels. SPERR has no error bound of zero, so it is not here.
#
# The two layouts of `02b`:
# - per slice: chunks `(1, Y, X)`, 50 slices per shard. One frame per slice, the
#   same unit as a single-frame DICOM file, and the only option for the 2D image
#   codecs. The TIFF codecs run on these, closest to the strips they had in TIFF.
# - 3D: chunks `(40, 200, 200)`, 40 slices per shard. Lets the volumetric codecs
#   exploit correlation along z. LERC and Pcodec run on both.
#
# The TIFF predictors carry over, with and without: horizontal differencing on
# uint16 (`Delta`), the floating point predictor on float32 (`Floatpred`). Those
# TIFF codecs are general-purpose, so they are the compressor after the predictor.
# Everything else is a serializer and the only codec. Codecs with their own thread
# pools are pinned to one thread, so all parallelism is zarr's and comparable
# across codecs.

# %%
LAYOUT_SLICE = "slice"
LAYOUT_3D = "3d"


def layout_chunks(layout: str, shape: tuple[int, ...]) -> tuple[tuple, tuple]:
    """(chunks, shards) for a (z, y, x) volume."""
    _, y, x = shape

    match layout:
        case "slice":
            return (1, y, x), (50, y, x)
        case "3d":
            return (40, 200, 200), (40, y, x)
        case _:
            raise ValueError(f"Unknown layout {layout!r}")


# %%
DTYPE_F32 = {np.float32}

# Family -> (input variant, imagecodecs availability flag). The flag is False
# for codecs the installed imagecodecs build was compiled without.
FAMILIES: dict[str, tuple[str, bool]] = {
    "jpegls": (U16_VARIANT, imagecodecs.JPEGLS.available),
    "j2k": (U16_VARIANT, imagecodecs.JPEG2K.available),
    "htj2k": (U16_VARIANT, imagecodecs.HTJ2K.available),
    "jpegxr": (U16_VARIANT, imagecodecs.JPEGXR.available),
    "jpeg": (U16_VARIANT, imagecodecs.JPEG.available),
    "png": (U16_VARIANT, imagecodecs.PNG.available),
    "jpegxl_u16": (U16_VARIANT, imagecodecs.JPEGXL.available),
    "jpegxl_f32": (F32_VARIANT, imagecodecs.JPEGXL.available),
    "lzma_u16": (U16_VARIANT, imagecodecs.LZMA.available),
    "lzma_f32": (F32_VARIANT, imagecodecs.LZMA.available),
    "zstd_u16": (U16_VARIANT, imagecodecs.ZSTD.available),
    "zstd_f32": (F32_VARIANT, imagecodecs.ZSTD.available),
    "deflate_u16": (U16_VARIANT, imagecodecs.DEFLATE.available),
    "deflate_f32": (F32_VARIANT, imagecodecs.DEFLATE.available),
    "lzw_u16": (U16_VARIANT, imagecodecs.LZW.available),
    "lzw_f32": (F32_VARIANT, imagecodecs.LZW.available),
    "rle_u16": (U16_VARIANT, imagecodecs.PACKBITS.available),
    "rle_f32": (F32_VARIANT, imagecodecs.PACKBITS.available),
    "lerc_u16": (U16_VARIANT, imagecodecs.LERC.available),
    "lerc_f32": (F32_VARIANT, imagecodecs.LERC.available),
    "pcodec_u16": (U16_VARIANT, imagecodecs.PCODEC.available),
    "pcodec_f32": (F32_VARIANT, imagecodecs.PCODEC.available),
    "zfp": (F32_VARIANT, imagecodecs.ZFP.available),
    "sz3": (F32_VARIANT, imagecodecs.SZ3.available),
}

JPEGXL_EFFORTS = [1, 3, 5, 7]
LZMA_LEVELS = [1, 7]
ZSTD_LEVELS = [1, 4, 6, 9, 12, 14, 17]
DEFLATE_LEVELS = [1, 2, 4, 5, 7, 9]
PNG_LEVELS = [1, 2, 3, 4, 5, 6, 7, 9]
# Lossless JPEG (SOF3). Predictors 5-7 are uint8 only.
JPEG_PREDICTORS = [1, 2, 3, 4]
# (subcodec, its index in comptest.configurations, level)
LERC_SUBCODECS = [
    ("none", 0, None),
    ("deflate", 1, 1),
    ("zstd", 2, 1),
    ("zstd", 2, 9),
    ("zstd", 2, 19),
]
# None is the codec's default, whose names and settings match `02b`.
PCODEC_LEVELS = [None, 4]

# Family's dtype -> (differencing, predictor), as in comptest.configurations.
PREDICTORS = {"u16": ("horizontal", 2), "f32": ("float", 3)}
NO_PREDICTOR = ("none", 1)

DTYPES = ("u16", "f32")


def _config(
    family: str,
    name: str,
    layout: str,
    *,
    serializer: tuple[type, tuple, dict] | None = None,
    filters: tuple[type, tuple, dict] | None = None,
    compressors: list[tuple[type, tuple, dict]] | None = None,
    extra: dict[str, Any] | None = None,
    **fields: Any,
) -> ZarrCompressionConfig:
    input_variant = FAMILIES[family][0]
    series = f"zarr-{family.replace('_', '-')}"
    chunks, shards = layout_chunks(layout, INPUT_SHAPE)
    allowed_dtypes = DTYPE_F32 if input_variant == F32_VARIANT else DTYPE_UINT8_UINT16

    return ZarrCompressionConfig(
        name=name,
        series=series,
        subseries=f"{series}-lossless",
        paradigm="zarr",
        implementation="zarr/imagecodecs",
        lossless=True,
        allowed_dtypes=allowed_dtypes,
        chunks=chunks,
        serializer=serializer,
        filters=filters,
        # An empty list, not None: None would leave zarr's default zstd in place.
        compressors=compressors or [],
        extra={
            "family": family,
            "input_variant": input_variant,
            "layout": layout,
            **(extra or {}),
        },
        # Not a declared field: get_zarr_kwargs forwards it to zarr as is.
        shards=shards,
        **fields,
    )


def _general_configs(
    codec: str,
    codec_class: type,
    levels: list[int] | None = None,
    efforts: dict[int, str] | None = None,
) -> list[ZarrCompressionConfig]:
    """A general-purpose TIFF codec, per slice: both dtypes, with and without predictor."""
    built = []

    for dtype in DTYPES:
        family = f"{codec}_{dtype}"

        for predicted in (False, True):
            suffix = "_pred" if predicted else ""
            differencing, predictor = PREDICTORS[dtype] if predicted else NO_PREDICTOR

            filters = None
            serializer = None
            if predicted and dtype == "u16":
                filters = (codecs.Delta, (), {})
            elif predicted:
                serializer = (codecs.Floatpred, (), {})

            for level in levels or [None]:
                kwargs = {} if level is None else {"level": level}
                level_name = "" if level is None else f"_l{level}"

                built.append(
                    _config(
                        family,
                        f"zarr_{family}{level_name}{suffix}",
                        LAYOUT_SLICE,
                        serializer=serializer,
                        filters=filters,
                        compressors=[(codec_class, (), kwargs)],
                        differencing=differencing,
                        predictor=predictor,
                        effort=level,
                        effort_cat=None if efforts is None else efforts.get(level),
                    )
                )

    return built


def build_configs() -> list[ZarrCompressionConfig]:
    jpegxl_kwargs = {
        "lossless": True,
        "photometric": "GRAY",
        "transfer": "LINEAR",
        "numthreads": 1,
    }

    return [
        _config(
            "jpegls",
            "zarr_jpegls_near000",
            LAYOUT_SLICE,
            serializer=(codecs.Jpegls, (), {"level": 0}),
            tolerance=0.0,
        ),
        _config(
            "j2k",
            "zarr_j2k_lossless",
            LAYOUT_SLICE,
            serializer=(codecs.Jpeg2k, (), {"reversible": True, "numthreads": 1}),
        ),
        _config(
            "htj2k",
            "zarr_htj2k_lossless",
            LAYOUT_SLICE,
            serializer=(codecs.Htj2k, (), {"reversible": True}),
        ),
        # Level 0 selects lossless coding. uint16 only: the float32 round trip is
        # not exact.
        _config(
            "jpegxr",
            "zarr_jpegxr_lossless",
            LAYOUT_SLICE,
            serializer=(codecs.Jpegxr, (), {"level": 0}),
        ),
        *(
            _config(
                "jpeg",
                f"zarr_jpeg_lossless_pred{predictor}",
                LAYOUT_SLICE,
                serializer=(
                    codecs.Jpeg,
                    (),
                    {"lossless": True, "predictor": predictor, "bitspersample": 16},
                ),
                predictor=predictor,
            )
            for predictor in JPEG_PREDICTORS
        ),
        *(
            _config(
                "png",
                f"zarr_png_l{level}",
                LAYOUT_SLICE,
                serializer=(codecs.Png, (), {"level": level}),
                effort=level,
                effort_cat=efforts_png.get(level),
            )
            for level in PNG_LEVELS
        ),
        *(
            _config(
                f"jpegxl_{dtype}",
                f"zarr_jpegxl_{dtype}_lossless_e{effort}",
                LAYOUT_SLICE,
                serializer=(codecs.Jpegxl, (), {**jpegxl_kwargs, "effort": effort}),
                effort=effort,
                effort_cat=efforts_jpegxl.get(effort),
            )
            for dtype in DTYPES
            for effort in JPEGXL_EFFORTS
        ),
        *_general_configs("lzma", codecs.Lzma, LZMA_LEVELS, efforts_lzma),
        *_general_configs("zstd", codecs.Zstd, ZSTD_LEVELS, efforts_zstd),
        *_general_configs("deflate", codecs.Deflate, DEFLATE_LEVELS, efforts_deflate),
        *_general_configs("lzw", codecs.Lzw),
        *_general_configs("rle", codecs.Packbits),
        *(
            _config(
                f"lerc_{dtype}",
                f"zarr_lerc_{dtype}_{layout}_{subcodec}{'' if level is None else level}",
                layout,
                serializer=(
                    codecs.Lerc,
                    (),
                    {"level": 0.0}
                    if level is None
                    else {
                        "level": 0.0,
                        "compression": subcodec,
                        "compressionargs": {"level": level},
                    },
                ),
                tolerance=0.0,
                subcodec=subcodec,
                subcodec_index=subcodec_index,
                effort=level,
                effort_cat=efforts_lerc[subcodec_index].get(level),
            )
            for dtype in DTYPES
            for layout in (LAYOUT_SLICE, LAYOUT_3D)
            for subcodec, subcodec_index, level in LERC_SUBCODECS
        ),
        *(
            _config(
                f"pcodec_{dtype}",
                f"zarr_pcodec_{dtype}"
                f"{'_slice' if layout == LAYOUT_SLICE else ''}"
                f"{'' if level is None else f'_l{level}'}",
                layout,
                serializer=(codecs.Pcodec, (), {} if level is None else {"level": level}),
                effort=level,
            )
            for dtype in DTYPES
            for layout in (LAYOUT_3D, LAYOUT_SLICE)
            for level in PCODEC_LEVELS
        ),
        _config(
            "zfp",
            "zarr_zfp_reversible",
            LAYOUT_3D,
            serializer=(codecs.Zfp, (), {"mode": "reversible", "numthreads": 1}),
        ),
        # An error bound of zero. SZ3 has no separate lossless mode.
        _config(
            "sz3",
            "zarr_sz3_abs0",
            LAYOUT_3D,
            serializer=(codecs.Sz3, (), {"mode": "abs", "abs": 0.0}),
            tolerance=0.0,
        ),
    ]


configs: dict[str, ZarrCompressionConfig] = {}
for config in build_configs():
    assert config.name not in configs, f"Duplicate config name {config.name}"
    configs[config.name] = config

for config in configs.values():
    print(f"{config.extra['family']:<12} {config.name}")

# 68 on uint16, 54 on float32.
assert len(configs) == 122, f"Expected 122 configurations, got {len(configs)}"

# %%
if codec_families is None:
    # Interactive: everything this imagecodecs build can do.
    FAMILY_NAMES = [name for name, (_, available) in FAMILIES.items() if available]
    unavailable = sorted(set(FAMILIES) - set(FAMILY_NAMES))
    if unavailable:
        print(f"Skipping families missing from this imagecodecs build: {unavailable}")
else:
    FAMILY_NAMES = codec_families
    unknown = set(FAMILY_NAMES) - set(FAMILIES)
    assert not unknown, f"Unknown codec families: {unknown}"
    # A batch job asked for these by name: fail now, not once per config.
    unavailable = [name for name in FAMILY_NAMES if not FAMILIES[name][1]]
    assert not unavailable, (
        f"Families {unavailable} are not available in imagecodecs "
        f"{imagecodecs.__version__} as installed"
    )

TARGET_CONFIGS = [
    name for name, config in configs.items() if config.extra["family"] in FAMILY_NAMES
]

if target_configs is not None:
    unknown = set(target_configs) - set(configs)
    assert not unknown, f"Unknown configs: {unknown}"
    TARGET_CONFIGS = [name for name in TARGET_CONFIGS if name in target_configs]

_reverser = -1 if reverse_configs else 1
TARGET_CONFIGS = TARGET_CONFIGS[::_reverser]

# Names the log and summary of this job. Several jobs (one per family group) share
# a dataset's output directory, so these must not collide.
FAMILY_LABEL = "all" if codec_families is None else "+".join(FAMILY_NAMES)

TARGET_CONFIGS

# %% [markdown]
# # Reference volumes
#
# Only the variants the selected configurations read.

# %%
VARIANTS = sorted({configs[name].extra["input_variant"] for name in TARGET_CONFIGS})


def read_volume(files: list[Path]) -> np.ndarray:
    with tifffile.TiffFile(files[0]) as tif:
        slice_shape = tif.pages[0].shape
        dtype = tif.pages[0].dtype

    volume = np.empty((len(files), *slice_shape), dtype=dtype)

    for z, file in enumerate(files):
        image = tifffile.imread(file)
        assert image.shape == slice_shape and image.dtype == dtype, (
            f"{file.name} is {image.shape} {image.dtype}, "
            f"expected {slice_shape} {dtype}"
        )
        volume[z] = image

    return volume


INPUT_FILES: dict[str, list[Path]] = {}
references: dict[str, np.ndarray] = {}
data_ranges: dict[str, float] = {}
images_input_sizes: dict[str, dict[str, int]] = {}

for variant in VARIANTS:
    INPUT_FILES[variant] = input_files(variant)
    references[variant] = read_volume(INPUT_FILES[variant])
    images_input_sizes[variant] = {
        file.stem: file.stat().st_size for file in INPUT_FILES[variant]
    }

    data_min = references[variant].min()
    data_max = references[variant].max()
    data_ranges[variant] = float(data_max) - float(data_min)

    print(
        f"{variant}: {references[variant].shape} {references[variant].dtype}, "
        f"min={data_min} max={data_max} range={data_ranges[variant]}"
    )

assert all(reference.shape == INPUT_SHAPE for reference in references.values())

# %% [markdown]
# # Run


# %%
def process_times() -> tuple[float, float, float]:
    """(wall, user, system) seconds.

    User/system come from the whole process, so nothing else may run in this
    kernel while a test is timed — zarr encodes chunks on its own thread pool,
    and per-thread accounting would miss that work.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return perf_counter(), usage.ru_utime, usage.ru_stime


def _package_versions(*names: str) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}

    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None

    return versions


def create_array(
    config: ZarrCompressionConfig, like: np.ndarray
) -> tuple[zarr.Array, dict[str, Any]]:
    """An empty in-memory array for `like`, and the dict backing its store."""
    data_store: dict[str, Any] = {}
    array = zarr.create_array(
        store=zarr.storage.MemoryStore(data_store),
        shape=like.shape,
        dtype=like.dtype,
        **config.get_zarr_kwargs(like),
    )

    return array, data_store


SHARD_INDEX_EMPTY = 2**64 - 1


def chunk_sizes(array: zarr.Array, data_store: dict[str, Any]) -> dict[tuple, int]:
    """Encoded size of every chunk, by chunk grid coordinates.

    Read from the shard indices: per shard, (offset, nbytes) as little-endian
    uint64 for each inner chunk in C order, then a 4-byte CRC32C, at the end of
    the shard (zarr's defaults for `sharding_indexed`).
    """
    chunks_per_shard = tuple(
        shard // chunk for shard, chunk in zip(array.shards, array.chunks, strict=True)
    )
    n_inner = int(np.prod(chunks_per_shard))
    index_size = 16 * n_inner + 4

    sizes: dict[tuple, int] = {}

    for key, buffer in data_store.items():
        if not key.startswith("c/"):
            continue

        raw = buffer.to_bytes()
        index = np.frombuffer(raw[-index_size:-4], dtype="<u8").reshape(-1, 2)

        shard_coords = tuple(int(part) for part in key.split("/")[1:])

        for inner, (offset, nbytes) in enumerate(index):
            if offset == SHARD_INDEX_EMPTY:
                continue

            inner_coords = np.unravel_index(inner, chunks_per_shard)
            coords = tuple(
                s * n + int(i)
                for s, n, i in zip(
                    shard_coords, chunks_per_shard, inner_coords, strict=True
                )
            )
            sizes[coords] = int(nbytes)

    return sizes


# %%
host = socket.gethostname()
RUN_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# One directory per run, shared by every dataset's and every family's job: host
# and timestamp are per job and go into the log and each JSON instead.
RUN_DIR_NAME = f"{TEST_CATEGORY}_{run_id}"

TEST_OUTPUT_DIR = OUTPUT_DIR / "zarr" / RUN_DIR_NAME / DATASET
TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger, LOG_FILE = configure_logging(
    TEST_OUTPUT_DIR / f"compression_{FAMILY_LABEL}.log"
)

PACKAGE_VERSIONS: dict[str, Any] = _package_versions("zarr", "numcodecs", "imagecodecs")
# The codec libraries imagecodecs was built against; "n/a" for those left out.
PACKAGE_VERSIONS["imagecodecs_libraries"] = imagecodecs.version(dict)

logger.info("Initialized Zarr lossless compression test run")
logger.info("Host: %s, timestamp: %s", host, RUN_TIMESTAMP)
logger.info("Dataset: %s, variants: %s", DATASET, VARIANTS)
logger.info("Volume shape: %s", INPUT_SHAPE)
logger.info("Families: %s", FAMILY_NAMES)
logger.info("zarr threads: %s", zarr.config.get("threading.max_workers"))
logger.info("Packages: %s", PACKAGE_VERSIONS)
logger.info("Test output directory: %s", TEST_OUTPUT_DIR)
logger.info("Log file: %s", LOG_FILE)

# %%
tests: list[CompressionTest] = []

n_elements = int(np.prod(INPUT_SHAPE))
# Every ratio, rate and bitrate is against the uint16 volume, whatever the
# configuration reads, so float codecs land on the same bytes axis as the rest.
uncompressed_size = n_elements * np.dtype(np.uint16).itemsize

logger.info("Number of configs: %d, reversed: %s", len(TARGET_CONFIGS), reverse_configs)
logger.info("Uncompressed (uint16) volume size: %d bytes", uncompressed_size)

for config_name in TARGET_CONFIGS:
    config = configs[config_name]
    variant = config.extra["input_variant"]
    reference = references[variant]
    data_range = data_ranges[variant]
    slice_names = [file.stem for file in INPUT_FILES[variant]]

    try:
        if reference.dtype not in config.allowed_dtypes:
            logger.warning(
                "Skipping config %s because dtype %s is unsupported",
                config.name,
                reference.dtype,
            )
            continue

        logger.info("Starting config: %s", config.name)

        start_wall_dt = datetime.now(UTC)
        total_wall_time_start = perf_counter()

        extra: dict[str, Any] = {
            "input_variant": variant,
            "input_dtype": str(reference.dtype),
            "input_size": int(reference.nbytes),
            "z_limit": Z_LIMIT,
            "n_threads": zarr.config.get("threading.max_workers"),
            "run_timestamp": RUN_TIMESTAMP,
            "lsb_jobid": os.environ.get("LSB_JOBID"),
            "package_versions": PACKAGE_VERSIONS,
        }

        # Warm up outside the timed region: the first use of a codec loads its
        # library, and the first array operation starts zarr's thread pool.
        warm_up, _ = create_array(config, reference)
        warm_up[: config.chunks[0]] = reference[: config.chunks[0]]
        _ = warm_up[: config.chunks[0]]
        del warm_up

        # Compress
        compressed_array, data_store = create_array(config, reference)

        logger.info("Compressing with config %s", config.name)
        compress_wall_start, compress_user_start, compress_system_start = (
            process_times()
        )
        compressed_array[:] = reference
        compress_wall_end, compress_user_end, compress_system_end = process_times()

        compress_wall_time_seconds = compress_wall_end - compress_wall_start
        compress_user_time_seconds = compress_user_end - compress_user_start
        compress_system_time_seconds = compress_system_end - compress_system_start

        logger.info(
            "Compression completed for %s in %.3f seconds",
            config.name,
            compress_wall_time_seconds,
        )

        # nbytes_stored() covers everything in the store: the shards (encoded
        # chunks plus their indices) and zarr.json. That is the counterpart of
        # DICOM's file sizes, headers included.
        assert compressed_array.nchunks_initialized >= compressed_array.nchunks
        compressed_size = int(compressed_array.nbytes_stored())

        if any(
            dim % shard
            for dim, shard in zip(
                compressed_array.shape, compressed_array.shards, strict=True
            )
        ):
            logger.warning(
                "Volume shape %s is not a multiple of the shard shape %s, so the "
                "padded shard inflates compressed_size (expected when Z_LIMIT is set)",
                compressed_array.shape,
                compressed_array.shards,
            )

        # The encoded chunks alone show how much of that is container.
        sizes = chunk_sizes(compressed_array, data_store)
        codestream_size = sum(sizes.values())
        extra |= {
            "chunks": list(compressed_array.chunks),
            "shards": list(compressed_array.shards),
            "n_chunks": len(sizes),
            "codestream_size": codestream_size,
            "container_overhead_size": compressed_size - codestream_size,
            # Against what this configuration actually read, e.g. float32.
            "compression_ratio_vs_input": reference.nbytes / compressed_size,
        }

        # One chunk per slice: per-slice sizes, as DICOM has per file.
        if config.extra["layout"] == LAYOUT_SLICE:
            images_compressed_sizes = {
                name: sizes[(z, 0, 0)] for z, name in enumerate(slice_names)
            }
        else:
            images_compressed_sizes = None

        # Decompress
        logger.info("Decompressing output from config %s", config.name)
        (
            decompress_wall_start,
            decompress_user_start,
            decompress_system_start,
        ) = process_times()
        decompressed = compressed_array[:]
        (
            decompress_wall_end,
            decompress_user_end,
            decompress_system_end,
        ) = process_times()

        decompress_wall_time_seconds = decompress_wall_end - decompress_wall_start
        decompress_user_time_seconds = decompress_user_end - decompress_user_start
        decompress_system_time_seconds = decompress_system_end - decompress_system_start

        logger.info(
            "Decompression completed for %s in %.3f seconds",
            config.name,
            decompress_wall_time_seconds,
        )

        actual_uncompressed_size = int(decompressed.nbytes)
        if config.extra["layout"] == LAYOUT_SLICE:
            images_uncompressed_sizes = {
                name: int(image.nbytes)
                for name, image in zip(slice_names, decompressed, strict=True)
            }
        else:
            images_uncompressed_sizes = None

        del compressed_array, data_store

        # Compare, against the volume this configuration read: a float codec
        # against the float volume, in its own data range.
        logger.info("Comparing decompressed volume for config %s", config.name)
        was_actually_lossless = bool(np.array_equal(decompressed, reference))
        logger.info(
            "Comparison completed for %s: lossless=%s",
            config.name,
            was_actually_lossless,
        )

        if not was_actually_lossless:
            # PSNR over the whole volume, not averaged over per-slice PSNRs,
            # which is a different and smaller number.
            psnr_db = metrics.psnr(reference, decompressed, data_range=data_range)
            rmse = metrics.rmse_from_psnr(psnr_db, data_range=data_range)

            # The worst single voxel in the volume. Accumulated over z slabs
            # only to avoid materialising a full difference volume; a max is an
            # exact reduction either way, unlike SSIM and PSNR.
            difference_dtype = (
                np.float64 if np.issubdtype(reference.dtype, np.floating) else np.int64
            )
            max_abs_error = 0
            for reference_slice, decompressed_slice in zip(
                reference, decompressed, strict=True
            ):
                difference = (
                    decompressed_slice.astype(difference_dtype) - reference_slice
                )
                max_abs_error = max(max_abs_error, np.abs(difference).max().item())

            extra |= {
                "max_abs_error": max_abs_error,
                # In uint16 steps: the uint16 variant maps this data range onto
                # 0-65535.
                "max_abs_error_u16_equivalent": max_abs_error
                * float(np.iinfo(np.uint16).max)
                / data_range,
                "rmse": rmse,
                "psnr_db": psnr_db,
            }

            logger.warning(
                "Config %s is not lossless: PSNR %.4f dB, max_abs_error=%.6g",
                config.name,
                psnr_db,
                max_abs_error,
            )

        del decompressed

        # Calculate quantities. Rates are uint16-equivalent bytes per second,
        # i.e. voxels per second times two, for every input dtype.
        compression_wall_rate = uncompressed_size / compress_wall_time_seconds
        compression_user_rate = uncompressed_size / compress_user_time_seconds
        decompression_wall_rate = uncompressed_size / decompress_wall_time_seconds
        decompression_user_rate = uncompressed_size / decompress_user_time_seconds

        bitrate_uncompressed = 8 * uncompressed_size / n_elements
        bitrate_compressed = 8 * compressed_size / n_elements

        compression_ratio = uncompressed_size / compressed_size
        space_saving = 1 - 1 / compression_ratio

        end_wall_dt = datetime.now(UTC)
        total_wall_time_seconds = perf_counter() - total_wall_time_start

        test = CompressionTest(
            **config.model_dump(),
            id=config.get_pathlike_str(),
            dataset_name=DATASET,
            dataset_path=INPUT_FILES[variant][0].parent,
            start_wall_dt=start_wall_dt,
            end_wall_dt=end_wall_dt,
            total_wall_time_seconds=total_wall_time_seconds,
            config=config,
            baseline_test=None,
            host=host,
            compress_wall_time_seconds=compress_wall_time_seconds,
            compress_user_time_seconds=compress_user_time_seconds,
            compress_system_time_seconds=compress_system_time_seconds,
            decompress_wall_time_seconds=decompress_wall_time_seconds,
            decompress_user_time_seconds=decompress_user_time_seconds,
            decompress_system_time_seconds=decompress_system_time_seconds,
            uncompressed_size=uncompressed_size,
            actual_uncompressed_size=actual_uncompressed_size,
            compressed_size=compressed_size,
            n_elements=n_elements,
            compression_wall_rate=compression_wall_rate,
            compression_user_rate=compression_user_rate,
            decompression_wall_rate=decompression_wall_rate,
            decompression_user_rate=decompression_user_rate,
            bitrate_uncompressed=bitrate_uncompressed,
            bitrate_compressed=bitrate_compressed,
            compression_ratio=compression_ratio,
            space_saving=space_saving,
            was_actually_lossless=was_actually_lossless,
            ssim=None,
            images_input_sizes=images_input_sizes[variant],
            images_uncompressed_sizes=images_uncompressed_sizes,
            images_compressed_sizes=images_compressed_sizes,
            runner_extra=extra,
        )

        tests.append(test)

        logger.debug("Test result:\n%s", pformat(test.summary(), sort_dicts=False))

        output_file = TEST_OUTPUT_DIR / f"test_{test.name}.json"
        with open(output_file, "w") as f:
            f.write(test.model_dump_json(indent=4, fallback=repr))

        logger.info(
            "Completed config %s: ratio=%.4f, space_saving=%.2f%%, result=%s",
            config.name,
            compression_ratio,
            space_saving * 100,
            output_file,
        )

    except Exception as e:
        if isinstance(e, KeyboardInterrupt):
            logger.warning("KeyboardInterrupt received, stopping tests")
            raise

        logger.exception("Error running test for config %s", config.name)

# %% [markdown]
# # Summary
#
# The per-test JSON files in `TEST_OUTPUT_DIR` are the actual result. This is
# just a look at the run that produced them.

# %%
summary = pl.DataFrame(
    [
        {
            "name": test.name,
            "host": test.host,
            "series": test.series,
            "input_variant": test.runner_extra.get("input_variant"),
            "declared_lossless": test.lossless,
            "was_actually_lossless": test.was_actually_lossless,
            "compression_ratio": test.compression_ratio,
            "compression_ratio_vs_input": test.runner_extra.get(
                "compression_ratio_vs_input"
            ),
            "bitrate_compressed": test.bitrate_compressed,
            "compress_wall_time_seconds": test.compress_wall_time_seconds,
            "decompress_wall_time_seconds": test.decompress_wall_time_seconds,
        }
        for test in tests
    ],
    infer_schema_length=None,
)

SUMMARY_FILE = TEST_OUTPUT_DIR / f"summary_{FAMILY_LABEL}.csv"

if not summary.is_empty():
    # A rerun of only some configurations keeps the other rows of the summary.
    if SUMMARY_FILE.is_file():
        previous = pl.read_csv(SUMMARY_FILE, infer_schema_length=None)
        summary = pl.concat(
            [previous.filter(~pl.col("name").is_in(summary["name"].implode())), summary],
            how="diagonal_relaxed",
        )
    summary = summary.sort("compression_ratio")
    summary.write_csv(SUMMARY_FILE)

summary

# %%
# Reload the run the way a viewer notebook would, as a sanity check that the
# JSON files carry everything needed.
reloaded = [
    json.loads(file.read_text()) for file in sorted(TEST_OUTPUT_DIR.glob("test_*.json"))
]

print(f"{len(reloaded)} test files in {TEST_OUTPUT_DIR}")

# %%
CLEAR_MEMORY = True

if is_batch or CLEAR_MEMORY:
    reference = None
    references.clear()
