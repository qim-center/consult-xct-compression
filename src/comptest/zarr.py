from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np
import zarr
import zarr.storage

from comptest.types import CompressionTest, ZarrCompressionConfig


def compression_test(
    dataset_name: str,
    dataset_path: Path,
    data: np.ndarray,
    config: ZarrCompressionConfig,
    baseline: CompressionTest | None,
) -> CompressionTest:
    start_dt = datetime.now(timezone.utc)

    # Run test
    # Save to memory to avoid any IO affecting the timing
    data_store = {}
    z = zarr.create_array(
        store=zarr.storage.MemoryStore(data_store),
        shape=data.shape,
        dtype=data.dtype,
        **config.get_zarr_kwargs(data),
    )

    time_start = perf_counter()
    z[:] = data
    compress_time_seconds = perf_counter() - time_start

    end_dt = datetime.now(timezone.utc)
    total_time_seconds = (end_dt - start_dt).total_seconds()

    # Get statistics
    nbytes = z.nbytes
    assert (
        z.nchunks == z.nchunks_initialized
    )  # We need this to be true for nbytes_stored() to be correct, I think
    nbytes_stored = z.nbytes_stored()
    compression_ratio = nbytes / nbytes_stored
    bitrate = 8 * nbytes / z.size
    bitrate_compressed = 8 * nbytes_stored / z.size

    # Get array info
    array_info = asdict(z.info_complete())

    test = CompressionTest(
        name=config.get_name(),
        id=config.get_pathlike_str(),
        series=config.series,
        vary_var=config.vary_var,
        vary_value=config.vary_value,
        dataset_name=dataset_name,
        dataset_path=dataset_path,
        start_dt=start_dt,
        end_dt=end_dt,
        total_time_seconds=total_time_seconds,
        config=config,
        baseline_test=baseline,
        compress_time_seconds=compress_time_seconds,
        nbytes=nbytes,
        nbytes_stored=nbytes_stored,
        bitrate=bitrate,
        bitrate_compressed=bitrate_compressed,
        compression_ratio=compression_ratio,
        lossless=config.is_lossless,
        array_info=array_info,
    )

    return test
