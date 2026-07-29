from pathlib import Path

from comptest.sh import ProcessResult, run_process


def imagemagick(
    input_path: Path, output_path: Path | None = None, *args: str
) -> tuple[Path, ProcessResult]:
    assert input_path.is_file()

    if output_path is None:
        output_path = input_path.with_name(
            input_path.stem + "_args__" + " ".join(args) + "__.tif"
        )

    result = run_process("magick", [*args, str(input_path), str(output_path)])

    if not result.returncode == 0:
        raise RuntimeError(
            "imagemagick failed with return code: " + str(result.returncode)
        )

    return output_path, result
