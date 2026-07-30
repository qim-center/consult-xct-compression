from pathlib import Path

from comptest.sh import ProcessResult, run_process
from comptest.utils.bulk import bulk_wrapper


def compress(
    input_path: Path, output_path: Path, *args: str
) -> tuple[Path, ProcessResult]:
    assert input_path.is_file()

    result = run_process("tiffcp", [*args, str(input_path), str(output_path)])

    if not result.returncode == 0:
        # libtiff creates the output file before it fails, so we need to delete it if the compression fails
        output_path.unlink(missing_ok=True)

        raise RuntimeError(
            f"tiffcp failed with return code: {result.returncode}"
            + f" for arguments: {args}"
            + f" and input file: {input_path}"
        )

    return output_path, result


def decompress(
    input_path: Path, output_path: Path, *args: str
) -> tuple[Path, ProcessResult]:
    assert input_path.is_file()

    # This means decompress
    if not args:
        args = (
            "-c",
            "none",
        )

    result = run_process("tiffcp", [*args, str(input_path), str(output_path)])

    if not result.returncode == 0:
        # libtiff creates the output file before it fails, so we need to delete it if the decompression fails
        output_path.unlink(missing_ok=True)

        raise RuntimeError(
            f"tiffcp failed with return code: {result.returncode}"
            + f" for arguments: {args}"
            + f" and input file: {input_path}"
        )

    return output_path, result


def compare(path1: Path, path2: Path, *args: str) -> bool:
    assert path1.is_file()
    assert path2.is_file()

    result = run_process("tiffcmp", [*args, str(path1), str(path2)])

    return result.returncode == 0


def compress_bulk(
    input_paths: list[Path],
    output_paths: list[Path],
    *args: str,
    n_jobs: int | None = None,
    joblib_kwargs: dict | None = None,
) -> list[tuple[Path, ProcessResult]]:
    return bulk_wrapper(
        compress,
        input_paths,
        output_paths,
        *args,
        n_jobs=n_jobs,
        joblib_kwargs=joblib_kwargs,
    )


def decompress_bulk(
    input_paths: list[Path],
    output_paths: list[Path],
    *args: str,
    n_jobs: int | None = None,
    joblib_kwargs: dict | None = None,
) -> list[tuple[Path, ProcessResult]]:
    return bulk_wrapper(
        decompress,
        input_paths,
        output_paths,
        *args,
        n_jobs=n_jobs,
        joblib_kwargs=joblib_kwargs,
    )


def compare_bulk(
    paths_a: list[Path],
    paths_b: list[Path],
    *args: str,
    n_jobs: int | None = None,
    joblib_kwargs: dict | None = None,
) -> list[bool]:
    return bulk_wrapper(
        compare, paths_a, paths_b, *args, n_jobs=n_jobs, joblib_kwargs=joblib_kwargs
    )


# Hack to get name correct in pydantic dump
compress.__name__ = "libtiff.compress"
compress_bulk.__name__ = "libtiff.compress"
decompress.__name__ = "libtiff.decompress"
decompress_bulk.__name__ = "libtiff.decompress"
compare.__name__ = "libtiff.compare"
compare_bulk.__name__ = "libtiff.compare"
