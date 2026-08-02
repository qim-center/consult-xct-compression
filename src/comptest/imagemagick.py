from pathlib import Path

from comptest.sh import ProcessResult, run_process
from comptest.utils.bulk import bulk_wrapper


def compress(
    input_path: Path, output_path: Path, *args: str
) -> ProcessResult:
    assert input_path.is_file()

    result = run_process("magick", [*args, str(input_path), str(output_path)])

    if not result.returncode == 0:
        raise RuntimeError(
            "imagemagick failed with return code: " + str(result.returncode)
            + f" for arguments: {args}"
            + f" and input file: {input_path}"
            + f" and stdout: {result.stdout}"
            + f" and stderr: {result.stderr}"
        )

    return result


def decompress(
    input_path: Path, output_path: Path, *args: str
) -> ProcessResult:
    assert input_path.is_file()

    if not args:
        args = ("-compress", "none")

    result = run_process("magick", [*args, str(input_path), str(output_path)])

    if result.returncode != 0:
        raise RuntimeError(
            "imagemagick failed with return code: "
            + str(result.returncode)
            + f" for arguments: {args}"
            + f" and input file: {input_path}"
            + f" and stdout: {result.stdout}"
            + f" and stderr: {result.stderr}"
        )

    return result


def compare(path_a: Path, path_b: Path, *args: str) -> bool:
    assert path_a.is_file()
    assert path_b.is_file()

    result = run_process(
        "magick",
        ["compare", *args, str(path_a), str(path_b), "null:"],
    )

    return result.returncode == 0


def compress_bulk(
    input_paths: list[Path],
    output_paths: list[Path],
    *args: str,
    n_jobs: int | None = None,
    joblib_kwargs: dict | None = None,
) -> list[ProcessResult]:
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
) -> list[ProcessResult]:
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
        compare,
        paths_a,
        paths_b,
        *args,
        n_jobs=n_jobs,
        joblib_kwargs=joblib_kwargs,
    )


# Hack to get name correct in pydantic dump
compress.__name__ = "imagemagick.compress"
compress_bulk.__name__ = "imagemagick.compress"
decompress.__name__ = "imagemagick.decompress"
decompress_bulk.__name__ = "imagemagick.decompress"
compare.__name__ = "imagemagick.compare"
compare_bulk.__name__ = "imagemagick.compare"
