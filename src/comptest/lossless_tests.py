import logging
from pathlib import Path
from time import perf_counter

import imagecodecs
import imagecodecs.zarr as codecs
import qim3d
import zarr
import zarr.codecs

from comptest.types import CompressionTest, ZarrCompressionConfig
from comptest.zarr import compression_test

logger = logging.getLogger(__name__)

imagecodecs.zarr.register_codecs()

default_serializer = (zarr.codecs.BytesCodec, {},)

chunks_1_channel = (1, 1000, 1000)  # 16-bit * 1 * 1000 * 1000 = 2 MB per chunk
chunks_3_channel = (3, 500, 500)  # 16-bit * 3 * 500 * 500 = 1.5 MB per chunk
chunks_4_channel = (4, 500, 500)  # 16-bit * 4 * 500 * 500 = 2 MB per chunk
chunks_131_channel = (131, 100, 100)  # 16-bit * 1 * 131 * 1000 = 2.62 MB per chunk
chunks_big_image_1_channel = (
    1,
    2000,
    2000,
)  # 16-bit * 1 * 2000 * 2000 = 8 MB per chunk
chunks_big_image_5_channel = (
    5,
    2000,
    2000,
)  # 16-bit * 5 * 2000 * 2000 = 40 MB per chunk
chunks_default = (3, 2000, 2000)

_C = ZarrCompressionConfig
BASELINE_CONFIG = _C(
    name="baseline",
    series="baseline",
    is_lossless=True,
    serializer=(codecs.Jpegxl, {"level": 5, "effort": 3, "lossless": True}),
    chunks=chunks_default,
)

CONFIG_INSTANCES = [
    _C(
        name="no-op",
        series="no-op",
        is_lossless=True,
        serializer=default_serializer,
        chunks=chunks_default,
    ),

    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 1, "lossless": True}),
        chunks=chunks_default,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 2, "lossless": True}),
        chunks=chunks_default,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 3, "lossless": True}),
        chunks=chunks_default,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 4, "lossless": True}),
        chunks=chunks_default,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 5, "lossless": True}),
        chunks=chunks_default,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 6, "lossless": True}),
        chunks=chunks_default,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 7, "lossless": True}),
        chunks=chunks_default,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 3, "lossless": True}),
        chunks=chunks_1_channel,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 3, "lossless": True}),
        chunks=chunks_3_channel,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 3, "lossless": True}),
        chunks=chunks_131_channel,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 3, "lossless": True}),
        chunks=chunks_big_image_1_channel,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 3, "lossless": True}),
        chunks=chunks_big_image_5_channel,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {"level": 5, "effort": 5, "lossless": True}),
        chunks=chunks_big_image_1_channel,
    ),
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(
            codecs.Jpegxl,
            {
                "level": 5,
                "effort": 3,
                "lossless": True,
                "planar": True,
                "transfer": "LINEAR",
                "usecontainer": False,
            },
        ),
        chunks=chunks_big_image_5_channel,
    ),
    _C(
        series="jpegls",
        is_lossless=True,
        serializer=(codecs.Jpegls, {"level": 0}),
        chunks=chunks_1_channel,
    ),
]


BASE_JPEGXL_CONFIG = {
    "level": 5,
    "planar": True,
    "transfer": imagecodecs.JPEGXL.TRANSFER_FUNCTION.LINEAR,
    "photometric": imagecodecs.JPEGXL.COLOR_SPACE.GRAY,
    "usecontainer": False,
}

# TODO: In 3.15 switch to unpacking in list comprehension
JPEGXL_EFFORT_CONFIGS = [
    _C(
        series="jpegxl-effort",
        is_lossless=True,
        serializer=(codecs.Jpegxl, {
            "effort": i,
            "lossless": True,
        } | BASE_JPEGXL_CONFIG),
        chunks=(5, ..., ...),
    ) for i in range (1, 8)
]

CURATED_CONFIGS = [
    # JPEG XL: Vary effort
    *JPEGXL_EFFORT_CONFIGS
]



def lossless_compression_test(
    dataset_path: Path, config: ZarrCompressionConfig
) -> CompressionTest:
    # Load data
    data_load_start = perf_counter()
    data = qim3d.io.load(dataset_path, contains=dataset_path.stem)
    data_load_seconds = perf_counter() - data_load_start
    logger.info(f"Loaded dataset {dataset_path} in {data_load_seconds:.2f} seconds")

    dataset_name = dataset_path.stem

    # Baseline
    baseline_test = compression_test(
        dataset_name=dataset_name,
        dataset_path=dataset_path,
        data=data,
        config=BASELINE_CONFIG,
        baseline=None,
    )
    logger.info(f"Baseline test completed: {baseline_test.model_dump()}")

    # Test
    test = compression_test(
        dataset_name=dataset_name,
        dataset_path=dataset_path,
        data=data,
        config=config,
        baseline=baseline_test,
    )
    logger.info(f"Test completed: {test.model_dump()}")

    return test
