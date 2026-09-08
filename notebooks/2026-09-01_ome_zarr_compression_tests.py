# %% [markdown]
# # OME-Zarr compression tests
#
# Measures compression/decompression performance and image quality for the
# OME-Zarr stores written by `2026-08-28_compress_ome_zarrs.ipynb`, and emits
# one `CompressionTest` JSON per store — the same metadata schema the file-stack
# notebook (`projection_file_stack_compression.ipynb`) writes, so the results can
# be loaded the same way `test_viewer.ipynb` loads its runs.
#
# The stores on disk are the *source of truth* for the configurations: each
# array's zarr.json gives the serializer, its parameters, the compressors and
# the chunk/shard layout. Those are replayed against the reference volume in a
# `MemoryStore`, so the timings measure the codec rather than the shared
# filesystem the stores live on.
#
# The reference volume is the `uncompressed` store (BytesCodec + zstd level 0),
# which is what all the other stores were written from.

# %%
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

import imagecodecs.zarr as codecs
import numpy as np
import polars as pl
import zarr
import zarr.storage

from comptest import metrics
from comptest.configurations import DTYPE_JPEGXL, efforts_jpegxl
from comptest.constants import COMPRESSION_TESTS_DIR, DATASETS_RECONSTRUCTIONS_DIR
from comptest.fs import get_dir_size_bytes
from comptest.types import (
    DTYPE_ANY,
    DTYPE_UINT8_UINT16,
    CompressionTest,
    StructuralSimilarityIndexMetrics,
    ZarrCompressionConfig,
)

# %load_ext autoreload
# %autoreload 2

# %%
codecs.register_codecs(verbose=False)

# %% [markdown]
# # Parameters

# %% [markdown]
# Every parameter below can be overridden through a `COMPTEST_` environment
# variable, which is how `submit_ome_zarr_tests.sh` drives batch runs: this is a
# jupytext script rather than an `.ipynb`, so papermill has no parameter cell to
# inject into. Left alone, the defaults are what an interactive run uses.


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
# Serializer names (the middle part of the store filename) to run; None = all.
target_serializers: list[str] | None = _env_list("TARGET_SERIALIZERS", None)
run_id: str = _env_str("RUN_ID", "none")
# Set by the LSF jobscript; only controls whether memory is released at the end.
is_batch: bool = _env_bool("IS_BATCH", "LSB_JOBID" in os.environ)

# %%
RECONSTRUCTION = _env_str("RECONSTRUCTION", "CIL_basic_binned_2x2")
DATASET = _env_str("DATASET", "Canislupus_CZM_712")
STUDY = _env_str("STUDY", "NaturArv3D_format_viability_study")
OUTPUT_ID = _env_str("OUTPUT_ID", "OME-Zarr_quality")

# Store whose contents every other store was written from.
REFERENCE_SERIALIZER = _env_str("REFERENCE_SERIALIZER", "uncompressed")

# OME-Zarr multiscale level to test. s0 is full resolution; the pyramid levels
# are written by ome-zarr-py and are not part of the codec comparison.
MULTISCALE_LEVEL = _env_str("MULTISCALE_LEVEL", "s0")

# Cut the volume down to the first N slices for a quick smoke test. None = all.
# The SSIM window spans z, so this cannot go below comptest.metrics
# .SSIM_MIN_EXTENT without the metric refusing to run.
Z_LIMIT: int | None = _env_int("Z_LIMIT", None)

# Codec threads zarr may use. zarr defaults to the machine's CPU count, which on
# a shared LSF node is not the core count the job was given, so timings are only
# comparable between runs if this is pinned to the allocation.
N_THREADS: int | None = _env_int("N_THREADS", None)

TEST_CATEGORY = _env_str("TEST_CATEGORY", "quality")

# Keep the decompressed volume each configuration produced, so the lossy result
# can be viewed and differenced afterwards rather than only summarised by SSIM.
# Off by default: a run writes one volume per configuration, which is tens of GB
# and does not belong next to the small JSON results in the repo's output/.
STORE_VOLUMES = _env_bool("STORE_VOLUMES", False)

# Volumes go to the project scratch space, indexed by run and then by test, so a
# stored volume sits at the same run/dataset/test coordinates as its JSON.
VOLUMES_DIR = _env_path("VOLUMES_DIR", COMPRESSION_TESTS_DIR / "decompressed_volumes")

# %%
if N_THREADS is not None:
    zarr.config.set({"threading.max_workers": N_THREADS})

print(f"zarr threading.max_workers: {zarr.config.get('threading.max_workers')}")

# %% [markdown]
# # Setup


# %%
def configure_logging(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_file = log_dir / "compression.log"

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
# A notebook has no __file__, and its working directory is notebooks/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
assert OUTPUT_DIR.is_dir()

STUDY_DIR = DATASETS_RECONSTRUCTIONS_DIR / RECONSTRUCTION / STUDY / OUTPUT_ID
assert STUDY_DIR.is_dir()

STORES = sorted(STUDY_DIR.glob(f"{DATASET}__*.ome.zarr"))
assert STORES, f"No stores found in {STUDY_DIR}"

print(f"{len(STORES)} stores in {STUDY_DIR}")

# %% [markdown]
# # Configurations
#
# Each store name is `{dataset}__{serializer}__{scale_factors}.ome.zarr`, and
# the array metadata carries the actual codec parameters. `_config_from_array`
# turns that into the `ZarrCompressionConfig` that is both replayed and recorded
# in the result JSON.


# %%
def parse_store_name(store: Path) -> tuple[str, str, str]:
    """`{dataset}__{serializer}__{scale_factors}.ome.zarr` -> its three parts."""
    stem = store.name.removesuffix(".ome.zarr")
    dataset, serializer_name, scale_factors_name = stem.split("__")

    return dataset, serializer_name, scale_factors_name


def codec_spec(codec: Any) -> tuple[type, tuple, dict]:
    """A live zarr codec -> the (callable, args, kwargs) triple configs use."""
    return (type(codec), (), dict(codec.to_dict().get("configuration", {})))


def _serializer_metadata(codec_name: str, codec_config: dict) -> dict[str, Any]:
    """
    Codec-specific grouping metadata for BaseCompressionConfig.

    `lossless` is what the configuration *asks* for. Whether the round trip is
    actually bit-exact is measured per test and reported as
    `was_actually_lossless`.
    """
    match codec_name:
        case "imagecodecs_jpegxl":
            distance = codec_config.get("distance")
            effort = codec_config.get("effort")
            # imagecodecs treats a non-None `level` as "encode losslessly",
            # which overrides `distance` unless lossless=False is explicit.
            lossless = bool(codec_config.get("lossless")) or distance == 0.0

            return {
                "name": f"zarr_jpegxl_d{distance:g}_e{effort}",
                "series": "zarr-jpegxl",
                "subseries": "zarr-jpegxl-lossless"
                if lossless
                else "zarr-jpegxl-lossy",
                "lossless": lossless,
                "allowed_dtypes": DTYPE_JPEGXL,
                "effort": effort,
                "effort_cat": efforts_jpegxl.get(effort),
                "distance": distance,
            }

        case "imagecodecs_jpegls":
            # JPEG-LS `level` is NEAR: the maximum absolute error per sample.
            near = codec_config.get("level", 0)
            lossless = near == 0

            return {
                "name": f"zarr_jpegls_near{near:03d}",
                "series": "zarr-jpegls",
                "subseries": "zarr-jpegls-lossless"
                if lossless
                else "zarr-jpegls-lossy",
                "lossless": lossless,
                "allowed_dtypes": DTYPE_UINT8_UINT16,
                "tolerance": float(near),
            }

        case "bytes":
            return {
                "name": "zarr_uncompressed",
                "series": "zarr-uncompressed",
                "lossless": True,
                "allowed_dtypes": DTYPE_ANY,
            }

        case _:
            raise NotImplementedError(f"No metadata mapping for codec {codec_name!r}")


def config_from_array(array: zarr.Array) -> ZarrCompressionConfig:
    serializer = codec_spec(array.serializer)
    codec_name = array.serializer.to_dict()["name"]
    compressors = [codec_spec(compressor) for compressor in array.compressors]
    filters = [codec_spec(filter_) for filter_ in array.filters]

    if len(filters) > 1:
        raise NotImplementedError(f"Config holds at most one filter, got {filters}")

    return ZarrCompressionConfig(
        **_serializer_metadata(codec_name, serializer[2]),
        paradigm="zarr",
        implementation="zarr/imagecodecs",
        chunks=array.chunks,
        filters=filters[0] if filters else None,
        serializer=serializer,
        compressors=compressors or None,
        # Extra fields are forwarded to zarr.create_array by get_zarr_kwargs.
        shards=array.shards,
    )


# %%
source_arrays: dict[str, zarr.Array] = {}
source_stores: dict[str, Path] = {}
configs: dict[str, ZarrCompressionConfig] = {}

for store in STORES:
    _dataset, serializer_name, _scale_factors_name = parse_store_name(store)
    assert _dataset == DATASET, f"Unexpected dataset {_dataset} in {store}"

    array = zarr.open_array(store / MULTISCALE_LEVEL, mode="r")
    source_arrays[serializer_name] = array
    source_stores[serializer_name] = store
    configs[serializer_name] = config_from_array(array)

# Catches a config whose name is not unique, e.g. because two stores differ only
# in a parameter that does not make it into the name.
names = [config.name for config in configs.values()]
if len(names) != len(set(names)):
    duplicates = {name for name in names if names.count(name) > 1}
    raise ValueError(f"Duplicate config names found: {duplicates}")

for serializer_name, config in configs.items():
    print(f"{serializer_name:<30} {config.name}")

# %%
assert REFERENCE_SERIALIZER in source_arrays, (
    f"Reference store {REFERENCE_SERIALIZER!r} not found in {STUDY_DIR}"
)

TARGET_SERIALIZERS = list(configs) if target_serializers is None else target_serializers
TARGET_SERIALIZERS = [
    name for name in TARGET_SERIALIZERS if name != REFERENCE_SERIALIZER
]

_reverser = -1 if reverse_configs else 1
TARGET_SERIALIZERS = TARGET_SERIALIZERS[::_reverser]

TARGET_SERIALIZERS

# %% [markdown]
# # Reference volume

# %%
reference_array = source_arrays[REFERENCE_SERIALIZER]

INPUT_SHAPE = (
    reference_array.shape
    if Z_LIMIT is None
    else (min(Z_LIMIT, reference_array.shape[0]), *reference_array.shape[1:])
)
INPUT_DTYPE = reference_array.dtype

print(
    f"Reading reference volume {INPUT_SHAPE} {INPUT_DTYPE} from {reference_array.store}"
)

reference = reference_array[: INPUT_SHAPE[0]]

data_min = reference.min()
data_max = reference.max()
data_range = float(data_max) - float(data_min)

print(f"min={data_min} max={data_max} range={data_range}")

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


# %%
host = socket.gethostname()
RUN_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

RUN_DIR_NAME = f"{TEST_CATEGORY}_{RUN_TIMESTAMP}_{host}_{run_id}"

TEST_OUTPUT_DIR = OUTPUT_DIR / "ome-zarr" / RUN_DIR_NAME / DATASET
TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Same run/dataset coordinates as TEST_OUTPUT_DIR, on scratch rather than in the
# repo, so test_{name}.json and {name}.zarr are trivially paired.
VOLUME_OUTPUT_DIR = VOLUMES_DIR / RUN_DIR_NAME / DATASET

if STORE_VOLUMES:
    VOLUME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger, LOG_FILE = configure_logging(TEST_OUTPUT_DIR)

logger.info("Initialized OME-Zarr compression test run")
logger.info("Host: %s", host)
logger.info("Dataset: %s", DATASET)
logger.info("Study directory: %s", STUDY_DIR)
logger.info("Reference store: %s", REFERENCE_SERIALIZER)
logger.info("Volume: shape=%s dtype=%s", INPUT_SHAPE, INPUT_DTYPE)
logger.info("Test output directory: %s", TEST_OUTPUT_DIR)
logger.info("Log file: %s", LOG_FILE)
logger.info("Store decompressed volumes: %s", STORE_VOLUMES)

if STORE_VOLUMES:
    logger.info("Volume output directory: %s", VOLUME_OUTPUT_DIR)

# %%
tests: list[CompressionTest] = []

uncompressed_size = int(reference.nbytes)
n_elements = int(reference.size)

logger.info(
    "Number of configs: %d, reversed: %s", len(TARGET_SERIALIZERS), reverse_configs
)
logger.info("Uncompressed volume size: %d bytes", uncompressed_size)

for serializer_name in TARGET_SERIALIZERS:
    config = configs[serializer_name]
    source_array = source_arrays[serializer_name]
    source_store = source_stores[serializer_name]

    try:
        if INPUT_DTYPE not in config.allowed_dtypes:
            logger.warning(
                "Skipping config %s because dtype %s is unsupported",
                config.name,
                INPUT_DTYPE,
            )
            continue

        logger.info("Starting config: %s (%s)", config.name, serializer_name)

        start_wall_dt = datetime.now(UTC)
        total_wall_time_start = perf_counter()

        extra: dict[str, Any] = {
            "serializer_name": serializer_name,
            "source_store": str(source_array.store),
            "multiscale_level": MULTISCALE_LEVEL,
            "z_limit": Z_LIMIT,
            "n_threads": zarr.config.get("threading.max_workers"),
            "lsb_jobid": os.environ.get("LSB_JOBID"),
        }

        # Compress: replay the stored configuration into memory, so the timing
        # is the codec's and not the shared filesystem's.
        data_store: dict[str, Any] = {}
        compressed_array = zarr.create_array(
            store=zarr.storage.MemoryStore(data_store),
            shape=reference.shape,
            dtype=reference.dtype,
            **config.get_zarr_kwargs(reference),
        )

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

        # nbytes_stored() only covers what was actually written. A sharded
        # array pads its last shard, so the initialized count can exceed
        # nchunks - but it must never fall short of it.
        assert compressed_array.nchunks_initialized >= compressed_array.nchunks
        compressed_size = int(compressed_array.nbytes_stored())

        if compressed_array.shards is not None and any(
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

        # Captured before the in-memory array goes away: a stored volume reuses
        # the layout of the store it came from.
        volume_chunks = compressed_array.chunks
        volume_shards = compressed_array.shards

        del data_store, compressed_array

        # The stores on disk hold the same volume under the same configuration,
        # so their size is a cross-check on the in-memory one. It differs by the
        # sharding index and by chunks that happen to be empty on disk.
        extra |= {
            "source_store_level_size": get_dir_size_bytes(
                source_store / MULTISCALE_LEVEL
            ),
            "source_store_size": get_dir_size_bytes(source_store),
        }

        # Compare
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
            # Per slice: SSIM is defined on the plane the codecs actually see,
            # and a whole-volume float map would be several GB.
            # PSNR over the whole volume, not averaged over per-slice PSNRs,
            # which is a different and smaller number.
            logger.info("Calculating PSNR for config %s", config.name)

            psnr_db = metrics.psnr(reference, decompressed, data_range=data_range)
            rmse = metrics.rmse_from_psnr(psnr_db, data_range=data_range)

            # The worst single voxel in the volume. Accumulated over z slabs
            # only to avoid materialising a full int64 difference; a max is an
            # exact reduction either way, unlike SSIM and PSNR.
            max_abs_error = 0
            for reference_slice, decompressed_slice in zip(
                reference, decompressed, strict=True
            ):
                difference = decompressed_slice.astype(np.int64) - reference_slice
                max_abs_error = max(max_abs_error, int(np.abs(difference).max()))

            extra |= {
                "max_abs_error": max_abs_error,
                "rmse": rmse,
                "psnr_db": psnr_db,
            }

            logger.info(
                "PSNR for config %s: %.4f dB (rmse=%.4f, max_abs_error=%d)",
                config.name,
                psnr_db,
                rmse,
                max_abs_error,
            )

            # 3D SSIM: the window spans z as well, so a codec that encodes each
            # slice independently is scored on the structure it breaks between
            # slices too. The map is float64 and voxel-for-voxel with the
            # volume, so it is summarised and dropped immediately.
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

        # Keep the decompressed volume. Written after every measurement and
        # outside both timed regions, so it cannot affect the reported rates.
        if STORE_VOLUMES:
            volume_store = VOLUME_OUTPUT_DIR / f"{config.name}.zarr"

            logger.info("Storing decompressed volume to %s", volume_store)

            # zarr's default compressor rather than the configuration's own
            # serializer: the point is a faithful record of what that serializer
            # produced, so re-encoding it lossily would defeat the purpose.
            volume_array = zarr.create_array(
                store=volume_store,
                shape=decompressed.shape,
                dtype=decompressed.dtype,
                chunks=volume_chunks,
                shards=volume_shards,
                overwrite=True,
            )
            volume_array[:] = decompressed

            volume_store_size = get_dir_size_bytes(volume_store)
            extra |= {
                "volume_store": str(volume_store),
                "volume_store_size": volume_store_size,
            }

            logger.info(
                "Stored decompressed volume for %s: %.2f GB",
                config.name,
                volume_store_size / 1e9,
            )

            del volume_array

        del decompressed

        # Calculate quantities
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
            dataset_path=source_store,
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
            # Per-image sizes are a file-stack concept; a zarr store has none.
            images_input_sizes=None,
            images_uncompressed_sizes=None,
            images_compressed_sizes=None,
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
            "series": test.series,
            "distance": test.distance,
            "tolerance": test.tolerance,
            "effort": test.effort,
            "declared_lossless": test.lossless,
            "was_actually_lossless": test.was_actually_lossless,
            "compression_ratio": test.compression_ratio,
            "bitrate_compressed": test.bitrate_compressed,
            "compress_wall_time_seconds": test.compress_wall_time_seconds,
            "decompress_wall_time_seconds": test.decompress_wall_time_seconds,
            "ssim_mean": test.ssim.mean if test.ssim is not None else None,
            "psnr_db": test.runner_extra.get("psnr_db"),
            "max_abs_error": test.runner_extra.get("max_abs_error"),
        }
        for test in tests
    ]
)

if not summary.is_empty():
    summary = summary.sort("compression_ratio")
    summary.write_csv(TEST_OUTPUT_DIR / "summary.csv")

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
    del reference
