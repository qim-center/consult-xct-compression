from pathlib import Path


def get_dir_size_bytes(path: Path, rglob: str = "*") -> int:
    """
    Get the total size of a directory in bytes.

    Returns:
        int: The total size of the directory in bytes.
    """
    if not path.is_dir():
        raise ValueError(f"Path {path} is not a directory.")

    total_size = 0
    for file in path.rglob(rglob):
        if file.is_file():
            total_size += file.stat().st_size

    return total_size
