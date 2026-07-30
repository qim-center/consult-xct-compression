from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from joblib import Parallel, delayed

T = TypeVar("T")


def bulk_wrapper(
    func: Callable[..., T],
    paths_a: list[Path],
    paths_b: list[Path],
    *args: str,
    n_jobs: int | None = None,
    joblib_kwargs: dict | None = None,
) -> list[T]:
    assert len(paths_a) == len(paths_b)

    if n_jobs is None:
        return [
            func(path_a, path_b, *args)
            for path_a, path_b in zip(paths_a, paths_b)
        ]

    return Parallel(n_jobs=n_jobs, **(joblib_kwargs or {}))(
        delayed(func)(path_a, path_b, *args)
        for path_a, path_b in zip(paths_a, paths_b)
    )
