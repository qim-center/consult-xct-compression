from enum import StrEnum, auto
from pathlib import Path

import typer

from comptest.lossless_tests import (
    CONFIG_INSTANCES,
    CURATED_CONFIGS,
    lossless_compression_test,
)

app = typer.Typer(name="comptest")

class RunType(StrEnum):
    LOSSLESS_CURATED = auto()
    LOSSLESS = auto()

@app.command()
def run_lossless_test(
    run_type: RunType = typer.Argument(..., help="Type of test to run."),
    dataset_path: Path = typer.Option(
        ...,
        help="Path to the dataset to run the lossless compression test on. This should be a directory containing a set of TIFF images.",
    ),
    index: int = typer.Argument(
        ...,
        help="Index of the configuration to use for the lossless compression test. This should be an integer between 0 and 11, inclusive.",
    ),
    run_id: str = typer.Option(
        ...,
        help="ID for the run. This will be used to identify the run in the output.",
    ),
    output_path: Path = typer.Option(
        Path("output"),
        help="Path to the directory where the output will be saved.",
    ),
):
    match run_type:
        case RunType.LOSSLESS_CURATED:
            configs = CURATED_CONFIGS
        case RunType.LOSSLESS:
            configs = CONFIG_INSTANCES
        case _:
            raise ValueError(f"Unknown run type: {run_type}")

    config = configs[index]
    test = lossless_compression_test(dataset_path, config)

    output_dir = output_path / run_type.value / run_id / dataset_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"test_{test.name}.json"

    with output_file.open("w") as f:
        f.write(test.model_dump_json(indent=4, fallback=repr))
