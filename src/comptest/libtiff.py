from pathlib import Path

from comptest.sh import ProcessResult, run_process


def compress(
    input_path: Path, output_path: Path | None = None, args: list[str] | None = None
) -> tuple[Path, ProcessResult]:
    assert input_path.is_file()

    args = args or []

    if output_path is None:
        output_path = input_path.with_name(
            input_path.stem + "_args__" + " ".join(args) + "__.tif"
        )

    result = run_process("tiffcp", [*args, str(input_path), str(output_path)])

    if not result.returncode == 0:
        # libtiff creates the output file before it fails, so we need to delete it if the compression fails
        output_path.unlink(missing_ok=True)

        raise RuntimeError("tiffcp failed with return code: " + str(result.returncode))

    return output_path, result
