# %% [markdown]
# # Zarr compression tests
#
# Measures compression/decompression performance and image quality of volumes
# written as Zarr v3 arrays, one serializer (ArrayBytes codec) from
# `imagecodecs.zarr` per configuration, and emits one `CompressionTest` JSON per
# configuration in the same schema and with the same metrics as the DICOM tests
# (`02a_dicom_compression_tests.py`): bit-exact round trip, PSNR, RMSE, max abs
# error, whole-volume 3D SSIM and 3D MS-SSIM. The two are meant to be plotted
# together, fidelity against compression ratio.
#
# Arrays are written to a `MemoryStore`, so the timings measure codec plus
# container rather than the shared filesystem. zarr encodes and decodes chunks on
# its own thread pool; imagecodecs releases the GIL, so no process pool is needed.
#
# Codecs that only take floats (ZFP, SZ3, SPERR), plus a float JPEG-XL and Pcodec
# for comparison, read the `f32_1000` variant; everything else reads `u16_1000`.
# Both are read as is. A float codec is scored against the float volume, but every
# compression ratio is against the *uint16* volume's size, so all configurations
# share one bytes axis.

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
from comptest.configurations import DTYPE_JPEGXL, efforts_jpegxl
from comptest.constants import NATURARV3D_STUDY_DIR, RECONSTRUCTIONS_TRANSFORMED_DIR
from comptest.types import (
    DTYPE_UINT8_UINT16,
    CompressionTest,
    StructuralSimilarityIndexMetrics,
    ZarrCompressionConfig,
)

# %load_ext autoreload
# %autoreload 2

# %% [markdown]
# # Parameters

# %% [markdown]
# Every parameter below can be overridden through a `COMPTEST_` environment
# variable, which is how `02b_submit_zarr_tests.sh` drives batch runs. Left alone,
# the defaults are what an interactive run uses.


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


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(f"COMPTEST_{name}")

    if value is None or not value.strip():
        return default

    return Path(value.strip())


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
# Config names (e.g. zarr_jpegls_near025) to run within those; None = all.
target_configs: list[str] | None = _env_list("TARGET_CONFIGS", None)
# The expensive quality metrics to compute; "none" for neither. PSNR, RMSE and
# the maximum error are always computed: they take seconds, the 3D SSIM and
# MS-SSIM each ~8 min per configuration.
OPTIONAL_METRICS = ["ssim", "ms_ssim"]
quality_metrics: list[str] = [
    metric
    for metric in _env_list("METRICS", OPTIONAL_METRICS)
    if metric.lower() != "none"
]
assert set(quality_metrics) <= set(OPTIONAL_METRICS), (
    f"Unknown metrics {set(quality_metrics) - set(OPTIONAL_METRICS)}, "
    f"expected some of {OPTIONAL_METRICS} or none"
)
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
# The SSIM window spans z, so too few slices makes the metric refuse to run.
# Keep it a multiple of both shard depths (50 and 40) so no shard is padded.
Z_LIMIT: int | None = _env_int("Z_LIMIT", None)

# Codec threads zarr may use. Defaults to the cores LSF gave the job, or else the
# cores this process may run on — not the machine's CPU count, which on a shared
# node is not what the job was given.
N_THREADS: int = _env_int(
    "N_THREADS",
    int(os.environ.get("LSB_DJOB_NUMPROC", len(os.sched_getaffinity(0)))),
)

TEST_CATEGORY = _env_str("TEST_CATEGORY", "quality")

# Keep the compressed array of each configuration, byte for byte as it was in
# memory. Off by default: a lossless u16 array is ~1 GB per dataset.
STORE_ZARRS = _env_bool("STORE_ZARRS", False)
# Or only of these configurations, by name (e.g. zarr_jpegxl_f32_d1_e7). Kept in
# addition to STORE_ZARRS, which keeps every one; "none" keeps none of them.
STORE_CONFIGS_DEFAULT: list[str] = []
store_configs: list[str] = [
    name
    for name in _env_list("STORE_CONFIGS", STORE_CONFIGS_DEFAULT)
    if name.lower() != "none"
]
ZARRS_DIR = _env_path(
    "ZARRS_DIR", NATURARV3D_STUDY_DIR / "compression_tests" / "zarr_stores"
)

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
# Parameters were picked on a sample of `Canislupus_CZM_712` (10 slices spread
# over z for the per-slice codecs, three 40-slice slabs for the 3D ones) to span
# compression ratios of roughly 2-128 against the uint16 volume. They are fixed
# for every dataset, so the ratios land somewhat differently on the others.
# Lossless already reaches ~2.5 on uint16, so the lossy uint16 sweeps start
# around 3.
#
# Two layouts:
# - per slice: chunks `(1, Y, X)`, 50 slices per shard. One frame per slice,
#   the same unit as a single-frame DICOM file; the only option for the 2D image
#   codecs.
# - 3D: chunks `(40, 200, 200)`, 40 slices per shard. Lets the volumetric codecs
#   exploit correlation along z, which a stack of independent frames cannot.
#   40 and 200 are multiples of ZFP's 4-voxel block.
#
# The serializer is the only codec: no compressor after it, as DICOM has none
# either and a general-purpose compressor gains nothing on an entropy-coded
# stream. Codecs with their own thread pools are pinned to one thread, so all
# parallelism is zarr's and comparable across codecs.

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


class ZfpFloatRate(codecs.Zfp):
    """`codecs.Zfp` without its `int(level)`.

    The wrapper truncates `level`, so a fixed rate below 1 bit per value is
    silently stored as 0. Those rates are exactly the ratios above 16 against
    uint16. `header=True` (the default) puts the rate in each chunk, so decoding
    does not depend on it.
    """

    def __init__(self, *, level: float | None = None, **kwargs: Any) -> None:
        super().__init__(level=None, **kwargs)
        object.__setattr__(self, "level", None if level is None else float(level))


# %%
DTYPE_F32 = {np.float32}

# Family -> (input variant, imagecodecs availability flag). The flag is False
# for codecs the installed imagecodecs build was compiled without.
FAMILIES: dict[str, tuple[str, bool]] = {
    "jpegls": (U16_VARIANT, imagecodecs.JPEGLS.available),
    "j2k": (U16_VARIANT, imagecodecs.JPEG2K.available),
    "htj2k": (U16_VARIANT, imagecodecs.HTJ2K.available),
    "jpegxl_u16": (U16_VARIANT, imagecodecs.JPEGXL.available),
    "jpegxl_f32": (F32_VARIANT, imagecodecs.JPEGXL.available),
    "lerc_slice": (U16_VARIANT, imagecodecs.LERC.available),
    "lerc_3d": (U16_VARIANT, imagecodecs.LERC.available),
    "pcodec_u16": (U16_VARIANT, imagecodecs.PCODEC.available),
    "zfp": (F32_VARIANT, imagecodecs.ZFP.available),
    "sz3": (F32_VARIANT, imagecodecs.SZ3.available),
    "sz3_slice": (F32_VARIANT, imagecodecs.SZ3.available),
    "sperr": (F32_VARIANT, imagecodecs.SPERR.available),
    "pcodec_f32": (F32_VARIANT, imagecodecs.PCODEC.available),
}

# JPEG-LS: NEAR, the maximum absolute error. The DICOM sweep, so the two pair up
# config for config. CharLS caps NEAR at 255, which is CR ~30.
JPEGLS_NEARS = [1, 2, 4, 8, 16, 25, 32, 50, 64, 128, 255]
# JPEG 2000 (OpenJPEG): `level` is a target PSNR in dB, not a ratio.
J2K_PSNRS = [98, 90, 74, 66, 61, 57, 54]
# HTJ2K (OpenJPH): `level` is an integer quality, 100 the finest step. 100 is
# already near-lossless (CR ~2.3) and 99 jumps to CR ~20, so nothing lower.
HTJ2K_QUALITIES = [99, 98, 97, 96, 95, 93, 90]
# JPEG-XL: Butteraugli distance. Below ~0.05 the output no longer changes (CR
# ~7 on uint16), so that is where the sweep starts. Same distances for both
# inputs, so they compare at equal settings. 3 and 5 continue the steps up to the
# d = 5 of the poster's error figure.
JPEGXL_DISTANCES = [0.05, 0.1, 0.15, 0.3, 0.5, 1.0, 1.5, 3.0, 5.0]
JPEGXL_EFFORT = 7
# LERC: maximum absolute error, in uint16 steps. The same for both layouts.
LERC_MAX_ERRORS = [4, 12, 100, 300, 700, 2500, 24576]
# ZFP fixed rate, bits per float32 value: CR = 16 / rate against uint16, exactly.
ZFP_RATES = [8, 4, 2, 1, 0.5, 0.25, 0.125]
# SZ3: absolute error bound, in units of the float volume (normalised to [0, 1]).
# The same bounds for both layouts: 3D, and per slice like the image codecs.
SZ3_ABS_ERRORS = [4e-6, 5e-5, 3e-4, 8e-4, 2e-3, 3.5e-3, 6e-3]
# SPERR: target PSNR in dB.
SPERR_PSNRS = [100, 68, 52, 42, 34, 28, 23]


def _config(
    family: str,
    name: str,
    series: str,
    layout: str,
    serializer: tuple[type, tuple, dict],
    *,
    lossless: bool = False,
    extra: dict[str, Any] | None = None,
    **fields: Any,
) -> ZarrCompressionConfig:
    input_variant = FAMILIES[family][0]
    chunks, shards = layout_chunks(layout, INPUT_SHAPE)
    allowed_dtypes = DTYPE_F32 if input_variant == F32_VARIANT else DTYPE_UINT8_UINT16

    return ZarrCompressionConfig(
        name=name,
        series=series,
        subseries=f"{series}-{'lossless' if lossless else 'lossy'}",
        paradigm="zarr",
        implementation="zarr/imagecodecs",
        lossless=lossless,
        allowed_dtypes=fields.pop("allowed_dtypes", allowed_dtypes),
        chunks=chunks,
        serializer=serializer,
        # An empty list, not None: None would leave zarr's default zstd in place.
        compressors=[],
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


def build_configs() -> list[ZarrCompressionConfig]:
    jpegxl_kwargs = {
        "effort": JPEGXL_EFFORT,
        "photometric": "GRAY",
        "transfer": "LINEAR",
        "numthreads": 1,
    }

    return [
        *(
            _config(
                "jpegls",
                f"zarr_jpegls_near{near:03d}",
                "zarr-jpegls",
                LAYOUT_SLICE,
                (codecs.Jpegls, (), {"level": near}),
                tolerance=float(near),
            )
            for near in JPEGLS_NEARS
        ),
        *(
            _config(
                "j2k",
                f"zarr_j2k_psnr{psnr:03d}",
                "zarr-j2k",
                LAYOUT_SLICE,
                (
                    codecs.Jpeg2k,
                    (),
                    {"level": psnr, "reversible": False, "numthreads": 1},
                ),
                quality=psnr,
                extra={"target_psnr_db": psnr},
            )
            for psnr in J2K_PSNRS
        ),
        *(
            _config(
                "htj2k",
                f"zarr_htj2k_q{quality:03d}",
                "zarr-htj2k",
                LAYOUT_SLICE,
                (codecs.Htj2k, (), {"level": quality, "reversible": False}),
                quality=quality,
            )
            for quality in HTJ2K_QUALITIES
        ),
        *(
            _config(
                family,
                f"zarr_{family}_d{distance:g}_e{JPEGXL_EFFORT}",
                f"zarr-{family.replace('_', '-')}",
                LAYOUT_SLICE,
                (codecs.Jpegxl, (), {**jpegxl_kwargs, "distance": distance}),
                allowed_dtypes=DTYPE_JPEGXL,
                distance=distance,
                effort=JPEGXL_EFFORT,
                effort_cat=efforts_jpegxl.get(JPEGXL_EFFORT),
            )
            for family in ("jpegxl_u16", "jpegxl_f32")
            for distance in JPEGXL_DISTANCES
        ),
        *(
            _config(
                f"lerc_{layout}",
                f"zarr_lerc_{layout}_err{max_error:05d}",
                f"zarr-lerc-{layout}",
                layout,
                (codecs.Lerc, (), {"level": float(max_error)}),
                tolerance=float(max_error),
            )
            for layout in (LAYOUT_SLICE, LAYOUT_3D)
            for max_error in LERC_MAX_ERRORS
        ),
        *(
            _config(
                "zfp",
                f"zarr_zfp_rate{rate:g}",
                "zarr-zfp",
                LAYOUT_3D,
                (
                    ZfpFloatRate,
                    (),
                    {"level": rate, "mode": "rate", "numthreads": 1},
                ),
                extra={"rate_bits_per_value": rate, "target_ratio": 16 / rate},
            )
            for rate in ZFP_RATES
        ),
        *(
            _config(
                "sz3",
                f"zarr_sz3_abs{abs_error:.1e}",
                "zarr-sz3",
                LAYOUT_3D,
                (codecs.Sz3, (), {"mode": "abs", "abs": abs_error}),
                tolerance=abs_error,
            )
            for abs_error in SZ3_ABS_ERRORS
        ),
        # Named apart from the 3D ones rather than by layout, so those keep the
        # names of the runs already made.
        *(
            _config(
                "sz3_slice",
                f"zarr_sz3_slice_abs{abs_error:.1e}",
                "zarr-sz3-slice",
                LAYOUT_SLICE,
                (codecs.Sz3, (), {"mode": "abs", "abs": abs_error}),
                tolerance=abs_error,
            )
            for abs_error in SZ3_ABS_ERRORS
        ),
        *(
            _config(
                "sperr",
                f"zarr_sperr_psnr{psnr:03d}",
                "zarr-sperr",
                LAYOUT_3D,
                (
                    codecs.Sperr,
                    (),
                    {"mode": "psnr", "level": float(psnr), "numthreads": 1},
                ),
                quality=psnr,
                extra={"target_psnr_db": psnr},
            )
            for psnr in SPERR_PSNRS
        ),
        *(
            _config(
                family,
                f"zarr_{family}",
                f"zarr-{family.replace('_', '-')}",
                LAYOUT_3D,
                (codecs.Pcodec, (), {}),
                lossless=True,
            )
            for family in ("pcodec_u16", "pcodec_f32")
        ),
    ]


configs: dict[str, ZarrCompressionConfig] = {}
for config in build_configs():
    assert config.name not in configs, f"Duplicate config name {config.name}"
    configs[config.name] = config

for config in configs.values():
    print(f"{config.extra['family']:<12} {config.name}")

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

unknown = set(store_configs) - set(configs)
assert not unknown, f"Unknown configs to store: {unknown}"


def stores(name: str) -> bool:
    """Whether to keep the compressed array of this configuration."""
    return STORE_ZARRS or name in store_configs


# Names the log and summary of this job. Several jobs (one per family) share a
# dataset's output directory, so these must not collide.
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

# Same run/dataset coordinates as TEST_OUTPUT_DIR, on scratch rather than in the
# repo, so test_{name}.json and {name}.zarr are trivially paired.
ZARR_OUTPUT_DIR = ZARRS_DIR / RUN_DIR_NAME / DATASET

if any(stores(name) for name in TARGET_CONFIGS):
    ZARR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger, LOG_FILE = configure_logging(
    TEST_OUTPUT_DIR / f"compression_{FAMILY_LABEL}.log"
)

PACKAGE_VERSIONS: dict[str, Any] = _package_versions("zarr", "numcodecs", "imagecodecs")
# The codec libraries imagecodecs was built against; "n/a" for those left out.
PACKAGE_VERSIONS["imagecodecs_libraries"] = imagecodecs.version(dict)

logger.info("Initialized Zarr compression test run")
logger.info("Host: %s, timestamp: %s", host, RUN_TIMESTAMP)
logger.info("Dataset: %s, variants: %s", DATASET, VARIANTS)
logger.info("Volume shape: %s", INPUT_SHAPE)
logger.info("Families: %s", FAMILY_NAMES)
logger.info("zarr threads: %s", zarr.config.get("threading.max_workers"))
logger.info("Packages: %s", PACKAGE_VERSIONS)
logger.info("Test output directory: %s", TEST_OUTPUT_DIR)
logger.info("Log file: %s", LOG_FILE)
logger.info(
    "Store Zarr arrays: %s",
    "all" if STORE_ZARRS else [name for name in TARGET_CONFIGS if stores(name)],
)

if any(stores(name) for name in TARGET_CONFIGS):
    logger.info("Zarr output directory: %s", ZARR_OUTPUT_DIR)

# %%
tests: list[CompressionTest] = []

n_elements = int(np.prod(INPUT_SHAPE))
# Every ratio, rate and bitrate is against the uint16 volume, whatever the
# configuration reads, so float codecs land on the same bytes axis as the rest.
uncompressed_size = n_elements * np.dtype(np.uint16).itemsize

logger.info("Number of configs: %d, reversed: %s", len(TARGET_CONFIGS), reverse_configs)
logger.info("Quality metrics beyond PSNR: %s", quality_metrics or "none")
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

        del compressed_array

        # Compare, against the volume this configuration read: a float codec
        # against the float volume, in its own data range.
        logger.info("Comparing decompressed volume for config %s", config.name)
        was_actually_lossless = bool(np.array_equal(decompressed, reference))
        logger.info(
            "Comparison completed for %s: lossless=%s",
            config.name,
            was_actually_lossless,
        )

        if was_actually_lossless:
            ssim = None
        else:
            # PSNR over the whole volume, not averaged over per-slice PSNRs,
            # which is a different and smaller number.
            logger.info("Calculating PSNR for config %s", config.name)

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
                # In uint16 steps, to read against JPEG-LS NEAR and LERC: the
                # uint16 variant maps this data range onto 0-65535.
                "max_abs_error_u16_equivalent": max_abs_error
                * float(np.iinfo(np.uint16).max)
                / data_range,
                "rmse": rmse,
                "psnr_db": psnr_db,
            }

            logger.info(
                "PSNR for config %s: %.4f dB (rmse=%.6g, max_abs_error=%.6g)",
                config.name,
                psnr_db,
                rmse,
                max_abs_error,
            )

            # 3D SSIM: the window spans z as well, so a codec that encodes each
            # slice independently is scored on the structure it breaks between
            # slices too. The map is float64 and voxel-for-voxel with the
            # volume, so it is summarised and dropped immediately.
            if "ssim" in quality_metrics:
                logger.info("Calculating SSIM for config %s", config.name)

                ssim_full = StructuralSimilarityIndexMetrics.get_ssim(
                    reference,
                    decompressed,
                    data_range=data_range,
                )
                ssim = StructuralSimilarityIndexMetrics.from_ndarray(ssim_full)

                del ssim_full

                logger.info(
                    "SSIM calculated for config %s: mean=%.9f", config.name, ssim.mean
                )
            else:
                logger.info("Skipping SSIM for config %s: not selected", config.name)
                ssim = None

            # MS-SSIM, also 3D: the same comparison over five successively
            # halved resolutions, so it also scores structure coarser than the
            # 11-voxel SSIM window. A scalar, so there is no map to summarise.
            if "ms_ssim" not in quality_metrics:
                logger.info("Skipping MS-SSIM for config %s: not selected", config.name)
                ms_ssim = None
            elif min(reference.shape) >= metrics.MS_SSIM_MIN_EXTENT:
                logger.info("Calculating MS-SSIM for config %s", config.name)

                ms_ssim = metrics.ms_ssim(
                    reference, decompressed, data_range=data_range
                )

                logger.info(
                    "MS-SSIM calculated for config %s: %.9f", config.name, ms_ssim
                )
            else:
                logger.warning(
                    "Skipping MS-SSIM for config %s: shape %s is below %d along "
                    "some axis (expected when Z_LIMIT is set)",
                    config.name,
                    reference.shape,
                    metrics.MS_SSIM_MIN_EXTENT,
                )
                ms_ssim = None

            extra |= {"ms_ssim": ms_ssim}

        del decompressed

        # Keep the compressed array, byte for byte. Written after every
        # measurement and outside both timed regions, so it cannot affect the
        # reported rates.
        if stores(config.name):
            zarr_store = ZARR_OUTPUT_DIR / f"{config.name}.zarr"

            logger.info("Storing Zarr array to %s", zarr_store)

            for key, buffer in data_store.items():
                path = zarr_store / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(buffer.to_bytes())

            extra |= {"zarr_store": str(zarr_store)}

        del data_store

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
            ssim=ssim,
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
            "tolerance": test.tolerance,
            "quality": test.quality,
            "distance": test.distance,
            "declared_lossless": test.lossless,
            "was_actually_lossless": test.was_actually_lossless,
            "compression_ratio": test.compression_ratio,
            "bitrate_compressed": test.bitrate_compressed,
            "compress_wall_time_seconds": test.compress_wall_time_seconds,
            "decompress_wall_time_seconds": test.decompress_wall_time_seconds,
            "ssim_mean": test.ssim.mean if test.ssim is not None else None,
            "ms_ssim": test.runner_extra.get("ms_ssim"),
            "psnr_db": test.runner_extra.get("psnr_db"),
            "max_abs_error_u16_equivalent": test.runner_extra.get(
                "max_abs_error_u16_equivalent"
            ),
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
