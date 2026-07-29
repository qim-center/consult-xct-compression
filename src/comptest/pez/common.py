"""
This file is shared between the payload process and the submission process.
"""

from pathlib import Path


def get_node_path_from_payload_path(payload_path: Path, index: int) -> Path:
    return payload_path.with_name(
        payload_path.stem + f"___{index}" + payload_path.suffix
    )
