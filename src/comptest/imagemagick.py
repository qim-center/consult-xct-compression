from pathlib import Path
import subprocess


def imagemagick(
    input_path: Path, output_path: Path | None = None, args: list[str] | None = None
) -> Path:
    assert input_path.is_file()

    args = args or []

    if output_path is None:
        output_path = input_path.with_name(
            input_path.stem + "_args__" + " ".join(args) + "__.tif"
        )

    result = subprocess.run(
        ["magick", *args, str(input_path), str(output_path)], capture_output=True
    )

    if not result.returncode == 0:
        result.check_returncode()

    return output_path
