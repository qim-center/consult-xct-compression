import resource
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any, TypeVar

import numpy as np
import tifffile

from comptest.sh import ProcessResult
from comptest.utils.bulk import bulk_wrapper

T = TypeVar("T")


def _max_rss_bytes(rusage: resource.struct_rusage) -> int:
    """Return ``ru_maxrss`` in bytes on supported platforms."""
    if sys.platform.startswith("linux"):
        return rusage.ru_maxrss * 1024
    return rusage.ru_maxrss


def _rewrite(
    input_path: Path,
    output_path: Path,
    compression: Any,
    **kwargs: Any,
) -> ProcessResult:
    assert input_path.is_file()

    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    wall_time_start = perf_counter()

    try:
        data = tifffile.imread(input_path)
        tifffile.imwrite(
            output_path,
            data,
            compression=compression,
            **kwargs,
        )
    except Exception:
        # imwrite may leave a partial or otherwise unusable TIFF behind.
        output_path.unlink(missing_ok=True)
        raise

    wall_time = perf_counter() - wall_time_start
    usage_end = resource.getrusage(resource.RUSAGE_SELF)

    return ProcessResult(
        wall_time=wall_time,
        user_time=usage_end.ru_utime - usage_start.ru_utime,
        system_time=usage_end.ru_stime - usage_start.ru_stime,
        memory_max_rss=_max_rss_bytes(usage_end),
        returncode=0,
        stdout="",
        stderr="",
    )


def compress(
    input_path: Path,
    output_path: Path,
    compression: Any = None,
    **kwargs: Any,
) -> ProcessResult:
    """Rewrite a TIFF using tifffile and the requested compression options."""
    return _rewrite(input_path, output_path, compression, **kwargs)


def decompress(
    input_path: Path,
    output_path: Path,
    compression: Any = None,
    **kwargs: Any,
) -> ProcessResult:
    """Decode a TIFF and write it uncompressed by default."""
    return _rewrite(input_path, output_path, compression, **kwargs)


def compare(path_a: Path, path_b: Path, **kwargs: Any) -> bool:
    """Return whether two TIFF files contain identical arrays."""
    assert path_a.is_file()
    assert path_b.is_file()

    array_a = tifffile.imread(path_a, **kwargs)
    array_b = tifffile.imread(path_b, **kwargs)

    return (
        array_a.shape == array_b.shape
        and array_a.dtype == array_b.dtype
        and np.array_equal(array_a, array_b, equal_nan=True)
    )


def _bulk(
    func: Callable[..., T],
    paths_a: list[Path],
    paths_b: list[Path],
    *args: Any,
    n_jobs: int | None,
    joblib_kwargs: dict[str, Any] | None,
    **kwargs: Any,
) -> list[T]:
    if kwargs:
        func = partial(func, **kwargs)

    return bulk_wrapper(
        func,
        paths_a,
        paths_b,
        *args,
        n_jobs=n_jobs,
        joblib_kwargs=joblib_kwargs,
    )


def compress_bulk(
    input_paths: list[Path],
    output_paths: list[Path],
    *args: Any,
    n_jobs: int | None = None,
    joblib_kwargs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> list[ProcessResult]:
    return _bulk(
        compress,
        input_paths,
        output_paths,
        *args,
        n_jobs=n_jobs,
        joblib_kwargs=joblib_kwargs,
        **kwargs,
    )


def decompress_bulk(
    input_paths: list[Path],
    output_paths: list[Path],
    *args: Any,
    n_jobs: int | None = None,
    joblib_kwargs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> list[ProcessResult]:
    return _bulk(
        decompress,
        input_paths,
        output_paths,
        *args,
        n_jobs=n_jobs,
        joblib_kwargs=joblib_kwargs,
        **kwargs,
    )


def compare_bulk(
    paths_a: list[Path],
    paths_b: list[Path],
    *args: Any,
    n_jobs: int | None = None,
    joblib_kwargs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> list[bool]:
    return _bulk(
        compare,
        paths_a,
        paths_b,
        *args,
        n_jobs=n_jobs,
        joblib_kwargs=joblib_kwargs,
        **kwargs,
    )


# Hack to get names correct in pydantic dumps.
compress.__name__ = "tifffile.compress"
compress_bulk.__name__ = "tifffile.compress"
decompress.__name__ = "tifffile.decompress"
decompress_bulk.__name__ = "tifffile.decompress"
compare.__name__ = "tifffile.compare"
compare_bulk.__name__ = "tifffile.compare"
