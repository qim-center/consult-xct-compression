# %% [markdown]
# # DICOM lossless compression tests
#
# The lossless counterpart of `02a_dicom_compression_tests.py`: the same stacks of
# single-frame DICOM files, the same worker pool and the same `CompressionTest`
# JSON per configuration, for every lossless transfer syntax pydicom can encode.
# JPEG XL has no transfer syntax in pydicom yet and HTJ2K no encoder, so neither
# is here.
#
# Every configuration is checked for a bit-exact round trip. SSIM and MS-SSIM are
# not computed: they say nothing about a lossless result. A configuration that is
# not exact after all gets its PSNR and maximum error, and a warning.
#
# Compressed stacks are not kept.

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

import numpy as np
import polars as pl
import tifffile
from pydicom.uid import (
    UID,
    JPEG2000Lossless,
    JPEGLSLossless,
    RLELossless,
    generate_uid,
)

from comptest import metrics
from comptest.constants import RECONSTRUCTIONS_TRANSFORMED_DIR
from comptest.dicom import SliceStackPool, decode_slice
from comptest.types import (
    DTYPE_UINT8_UINT16,
    CompressionTest,
    DicomCompressionConfig,
)

# %load_ext autoreload
# %autoreload 2

# %% [markdown]
# # Parameters

# %% [markdown]
# Every parameter below can be overridden through a `COMPTEST_` environment
# variable, which is how `03a_submit_dicom_lossless_tests.sh` drives batch runs.
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
# Config names (e.g. dicom_rle_lossless) to run; None = all.
target_configs: list[str] | None = _env_list("TARGET_CONFIGS", None)
run_id: str = _env_str("RUN_ID", "none")
# Set by the LSF jobscript; only controls whether memory is released at the end.
is_batch: bool = _env_bool("IS_BATCH", "LSB_JOBID" in os.environ)

# %%
DATASET = _env_str("DATASET", "Canislupus_CZM_712")
# Subdirectory of RECONSTRUCTIONS_TRANSFORMED_DIR: dtype and edge length.
DATA_VARIANT = _env_str("DATA_VARIANT", "u16_1000")

# Cut the volume down to the first N slices for a quick smoke test. None = all.
Z_LIMIT: int | None = _env_int("Z_LIMIT", None)

# Worker processes encoding/decoding slices. Defaults to the cores LSF gave the
# job, or else the cores this process may run on — not the machine's CPU count,
# which on a shared node is not what the job was given.
N_WORKERS: int = _env_int(
    "N_WORKERS",
    int(os.environ.get("LSB_DJOB_NUMPROC", len(os.sched_getaffinity(0)))),
)
# Slices per task sent to a worker; amortises the inter-process overhead.
BATCH_SIZE: int = _env_int("BATCH_SIZE", 4)

TEST_CATEGORY = _env_str("TEST_CATEGORY", "lossless")

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
# A notebook has no __file__, and its working directory is data_gathering/.
NOTEBOOK_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path().resolve()
)
PROJECT_DIR = NOTEBOOK_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"
assert OUTPUT_DIR.is_dir()

DATASET_DIR = RECONSTRUCTIONS_TRANSFORMED_DIR / DATA_VARIANT / DATASET
assert DATASET_DIR.is_dir(), f"{DATASET_DIR} does not exist"

INPUT_FILES = sorted(DATASET_DIR.glob("slice_z*.tif"))
assert INPUT_FILES, f"No slices found in {DATASET_DIR}"

if Z_LIMIT is not None:
    INPUT_FILES = INPUT_FILES[:Z_LIMIT]

print(f"{len(INPUT_FILES)} slices from {DATASET_DIR}")

# %% [markdown]
# # Configurations
#
# JPEG-LS and JPEG 2000 keep their names from `02a`, so the two runs pair up.
#
# The first and last slice of every configuration are also read by a second,
# independent decoder, outside the timed regions: a file only one decoder can read
# is not much use as DICOM. That is GDCM, but pydicom has no GDCM decoder for RLE,
# so there it is pydicom's own.


# %%
def lossless_config(
    name: str,
    series: str,
    transfer_syntax_uid: UID,
    plugin: str,
    interop_plugin: str = "gdcm",
    **fields: Any,
) -> DicomCompressionConfig:
    return DicomCompressionConfig(
        name=name,
        series=series,
        subseries=f"{series}-lossless",
        paradigm="dicom",
        implementation="pydicom",
        lossless=True,
        allowed_dtypes=DTYPE_UINT8_UINT16,
        transfer_syntax_uid=transfer_syntax_uid,
        encoding_plugin=plugin,
        decoding_plugin=plugin,
        encoder_kwargs={},
        extra={"interop_decoding_plugin": interop_plugin},
        **fields,
    )


configs: dict[str, DicomCompressionConfig] = {
    config.name: config
    for config in [
        lossless_config(
            "dicom_jpegls_near000",
            "dicom-jpegls",
            JPEGLSLossless,
            "pyjpegls",
            tolerance=0.0,
        ),
        lossless_config(
            "dicom_j2k_lossless", "dicom-j2k", JPEG2000Lossless, "pylibjpeg"
        ),
        lossless_config(
            "dicom_rle_lossless",
            "dicom-rle",
            RLELossless,
            "pylibjpeg",
            interop_plugin="pydicom",
        ),
    ]
}

for config in configs.values():
    print(f"{config.name:<25} {UID(config.transfer_syntax_uid).name}")

# %%
TARGET_CONFIGS = list(configs) if target_configs is None else target_configs

unknown = set(TARGET_CONFIGS) - set(configs)
assert not unknown, f"Unknown configs: {unknown}"

_reverser = -1 if reverse_configs else 1
TARGET_CONFIGS = TARGET_CONFIGS[::_reverser]

TARGET_CONFIGS

# %% [markdown]
# # Reference volume
#
# Read straight into the shared memory the workers encode from, so the volume
# exists once rather than once per worker.

# %%
with tifffile.TiffFile(INPUT_FILES[0]) as tif:
    SLICE_SHAPE = tif.pages[0].shape
    INPUT_DTYPE = tif.pages[0].dtype

INPUT_SHAPE = (len(INPUT_FILES), *SLICE_SHAPE)

print(f"Volume {INPUT_SHAPE} {INPUT_DTYPE}, {N_WORKERS} workers")


def _codec_spec(config: DicomCompressionConfig) -> dict[str, Any]:
    return {
        "transfer_syntax_uid": str(config.transfer_syntax_uid),
        "encoding_plugin": config.encoding_plugin,
        "decoding_plugin": config.decoding_plugin,
        "encoder_kwargs": config.encoder_kwargs,
    }


# One per distinct codec, so every plugin is imported before anything is timed.
_warm_up_codecs = list(
    {
        (config.transfer_syntax_uid, config.encoding_plugin): _codec_spec(config)
        for config in (configs[name] for name in TARGET_CONFIGS)
    }.values()
)

pool = SliceStackPool(
    INPUT_SHAPE,
    INPUT_DTYPE,
    n_workers=N_WORKERS,
    batch_size=BATCH_SIZE,
    warm_up_codecs=_warm_up_codecs,
)
reference = pool.reference

# %%
images_input_sizes: dict[str, int] = {}

for z, file in enumerate(INPUT_FILES):
    image = tifffile.imread(file)
    assert image.shape == SLICE_SHAPE and image.dtype == INPUT_DTYPE, (
        f"{file.name} is {image.shape} {image.dtype}, "
        f"expected {SLICE_SHAPE} {INPUT_DTYPE}"
    )
    reference[z] = image
    images_input_sizes[file.stem] = file.stat().st_size

data_min = reference.min()
data_max = reference.max()
data_range = float(data_max) - float(data_min)

print(f"min={data_min} max={data_max} range={data_range}")

# %% [markdown]
# # Run


# %%
def process_times() -> tuple[float, float, float]:
    """(wall, user, system) seconds of this process.

    The workers' CPU time is accounted for by the pool and added on top.
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


# %%
host = socket.gethostname()
RUN_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# One directory per run, shared by every dataset's job: host and timestamp are
# per job and go into the log and each JSON instead.
RUN_DIR_NAME = f"{TEST_CATEGORY}_{run_id}"

TEST_OUTPUT_DIR = OUTPUT_DIR / "dicom" / RUN_DIR_NAME / DATASET
TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger, LOG_FILE = configure_logging(TEST_OUTPUT_DIR)

PACKAGE_VERSIONS = _package_versions(
    "pydicom", "pyjpegls", "pylibjpeg", "pylibjpeg-openjpeg", "pylibjpeg-rle", "python-gdcm"
)

logger.info("Initialized DICOM lossless compression test run")
logger.info("Host: %s, timestamp: %s", host, RUN_TIMESTAMP)
logger.info("Dataset: %s (%s)", DATASET, DATASET_DIR)
logger.info("Volume: shape=%s dtype=%s", INPUT_SHAPE, INPUT_DTYPE)
logger.info("Workers: %d, slices per task: %d", N_WORKERS, BATCH_SIZE)
logger.info("Packages: %s", PACKAGE_VERSIONS)
logger.info("Test output directory: %s", TEST_OUTPUT_DIR)
logger.info("Log file: %s", LOG_FILE)

# %%
tests: list[CompressionTest] = []

uncompressed_size = int(reference.nbytes)
n_elements = int(reference.size)
slice_names = [file.stem for file in INPUT_FILES]

logger.info("Number of configs: %d, reversed: %s", len(TARGET_CONFIGS), reverse_configs)
logger.info("Uncompressed volume size: %d bytes", uncompressed_size)

for config_name in TARGET_CONFIGS:
    config = configs[config_name]
    codec = _codec_spec(config)

    try:
        if INPUT_DTYPE not in config.allowed_dtypes:
            logger.warning(
                "Skipping config %s because dtype %s is unsupported",
                config.name,
                INPUT_DTYPE,
            )
            continue

        logger.info("Starting config: %s", config.name)

        start_wall_dt = datetime.now(UTC)
        total_wall_time_start = perf_counter()

        extra: dict[str, Any] = {
            "data_variant": DATA_VARIANT,
            "z_limit": Z_LIMIT,
            "n_workers": N_WORKERS,
            "batch_size": BATCH_SIZE,
            "run_timestamp": RUN_TIMESTAMP,
            "lsb_jobid": os.environ.get("LSB_JOBID"),
            "package_versions": PACKAGE_VERSIONS,
        }

        # Compress: header, encode, encapsulate and write each slice to a
        # complete file in memory.
        study_uid = generate_uid()
        series_uid = generate_uid()

        logger.info("Compressing with config %s", config.name)
        compress_wall_start, compress_user_start, compress_system_start = (
            process_times()
        )
        files, pixel_data_sizes, workers_user, workers_system = pool.encode(
            codec, study_uid=study_uid, series_uid=series_uid
        )
        compress_wall_end, compress_user_end, compress_system_end = process_times()

        compress_wall_time_seconds = compress_wall_end - compress_wall_start
        compress_user_time_seconds = (
            compress_user_end - compress_user_start + workers_user
        )
        compress_system_time_seconds = (
            compress_system_end - compress_system_start + workers_system
        )

        logger.info(
            "Compression completed for %s in %.3f seconds",
            config.name,
            compress_wall_time_seconds,
        )

        images_compressed_sizes = {
            name: len(raw) for name, raw in zip(slice_names, files, strict=True)
        }
        compressed_size = sum(images_compressed_sizes.values())

        # The files' size is what is reported. The codestreams alone show how
        # much of that is per-file DICOM header.
        pixel_data_size = sum(pixel_data_sizes)
        extra |= {
            "pixel_data_size": pixel_data_size,
            "header_overhead_size": compressed_size - pixel_data_size,
        }

        # Decompress: read each file and decode it into the shared volume.
        pool.decoded.fill(0)

        logger.info("Decompressing output from config %s", config.name)
        (
            decompress_wall_start,
            decompress_user_start,
            decompress_system_start,
        ) = process_times()
        workers_user, workers_system = pool.decode(files, config.decoding_plugin)
        (
            decompress_wall_end,
            decompress_user_end,
            decompress_system_end,
        ) = process_times()

        decompress_wall_time_seconds = decompress_wall_end - decompress_wall_start
        decompress_user_time_seconds = (
            decompress_user_end - decompress_user_start + workers_user
        )
        decompress_system_time_seconds = (
            decompress_system_end - decompress_system_start + workers_system
        )

        logger.info(
            "Decompression completed for %s in %.3f seconds",
            config.name,
            decompress_wall_time_seconds,
        )

        decompressed = pool.decoded
        actual_uncompressed_size = int(decompressed.nbytes)
        images_uncompressed_sizes = {
            name: int(image.nbytes)
            for name, image in zip(slice_names, decompressed, strict=True)
        }

        # Interoperability: an independent decoder must read the same pixels.
        interop_plugin = config.extra["interop_decoding_plugin"]
        interop_slices = sorted({0, len(files) - 1})
        try:
            interop_passed = all(
                np.array_equal(decode_slice(files[z], interop_plugin), decompressed[z])
                for z in interop_slices
            )
        except Exception:
            logger.exception(
                "Interop decoder %s failed for config %s",
                interop_plugin,
                config.name,
            )
            interop_passed = False

        extra |= {
            "interop_decoding_plugin": interop_plugin,
            "interop_slices": interop_slices,
            "interop_passed": interop_passed,
        }

        if not interop_passed:
            logger.warning(
                "Interop check failed for config %s: %s disagrees on slices %s",
                config.name,
                interop_plugin,
                interop_slices,
            )

        # Compare
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

            logger.warning(
                "Config %s is not lossless: PSNR %.4f dB, max_abs_error=%d",
                config.name,
                psnr_db,
                max_abs_error,
            )

        del files

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
            dataset_path=DATASET_DIR,
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
            images_input_sizes=images_input_sizes,
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
            "declared_lossless": test.lossless,
            "was_actually_lossless": test.was_actually_lossless,
            "compression_ratio": test.compression_ratio,
            "bitrate_compressed": test.bitrate_compressed,
            "compress_wall_time_seconds": test.compress_wall_time_seconds,
            "decompress_wall_time_seconds": test.decompress_wall_time_seconds,
            "interop_passed": test.runner_extra.get("interop_passed"),
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
    # Views of the pool's shared memory, which close() releases.
    reference = decompressed = None
    pool.close()
