"""Reproduce negative-float clipping in tifffile JPEG XL compression."""

from __future__ import annotations

import subprocess
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import imagecodecs
import matplotlib
import numpy as np
import tifffile
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

HERE = Path(__file__).resolve().parent
DISTANCE = 0.01
EFFORT = 7
NUM_THREADS = 1
NEGATIVE_TAIL_LIMIT = -0.004


def read_pfm(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image).copy()


def imagecodecs_round_trip(array: np.ndarray) -> np.ndarray:
    encoded = imagecodecs.jpegxl_encode(
        array,
        distance=DISTANCE,
        effort=EFFORT,
        numthreads=NUM_THREADS,
    )
    return imagecodecs.jpegxl_decode(encoded)


def cjxl_version() -> str:
    result = subprocess.run(
        ["cjxl", "--version"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.stdout.strip().splitlines()[0]


def cjxl_round_trip(
    input_path: Path,
    *,
    linear: bool = False,
    non_perceptual: bool = False,
) -> np.ndarray:
    with TemporaryDirectory(prefix="jxl-negativity-repro-") as temp_dir:
        output_path = Path(temp_dir) / "cjxl-output.jxl"
        command = [
            "cjxl",
            str(input_path),
            str(output_path),
            f"--distance={DISTANCE}",
            f"--effort={EFFORT}",
            "--quiet",
        ]
        if linear:
            command.extend(["-x", "color_space=Gra_D65_Rel_Lin"])
        if non_perceptual:
            command.append("--disable_perceptual_optimizations")
        subprocess.run(command, check=True)
        return imagecodecs.jpegxl_decode(output_path.read_bytes())


def tifffile_round_trip(array: np.ndarray) -> np.ndarray:
    buffer = BytesIO()
    tifffile.imwrite(
        buffer,
        array,
        photometric="minisblack",
        compression="jpegxl",
        compressionargs={
            "distance": DISTANCE,
            "effort": EFFORT,
            "numthreads": NUM_THREADS,
        },
    )
    buffer.seek(0)
    return tifffile.imread(buffer)


def normalize(array: np.ndarray) -> tuple[np.ndarray, float, float]:
    source_min = float(array.min())
    source_range = float(array.max()) - source_min
    return (array - source_min) / source_range, source_min, source_range


def print_result(name: str, array: np.ndarray, source: np.ndarray) -> None:
    error = np.abs(array - source)
    below_limit = np.count_nonzero(array < NEGATIVE_TAIL_LIMIT)
    print(
        f"{name:<28} {array.min():>12.8f} {array.max():>12.8f} "
        f"{below_limit:>9d} {error.mean():>12.8f} {error.max():>12.8f}"
    )


def save_diagnostic_figures(
    source: np.ndarray,
    imagecodecs_xyb: np.ndarray,
    cjxl_xyb: np.ndarray,
    non_perceptual: np.ndarray,
) -> None:
    cases = [
        ("Source", source),
        ("Lossy XYB\n(imagecodecs)", imagecodecs_xyb),
        ("Lossy XYB\n(cjxl)", cjxl_xyb),
        ("Lossy non-perceptual\n(cjxl)", non_perceptual),
    ]

    value_norm = TwoSlopeNorm(
        vmin=float(min(array.min() for _, array in cases)),
        vcenter=0.0,
        vmax=float(max(array.max() for _, array in cases)),
    )
    figure, axes = plt.subplots(1, 4, figsize=(17.5, 4.4), constrained_layout=True)
    for axis, (label, array) in zip(axes, cases, strict=True):
        image = axis.imshow(array, cmap="coolwarm", norm=value_norm)
        axis.set_title(f"{label}\nminimum = {array.min():.6f}")
        axis.set_axis_off()
    colorbar = figure.colorbar(image, ax=axes, shrink=0.86, pad=0.02)
    colorbar.set_label("Decoded sample value")
    figure.suptitle(
        "JPEG XL lossy float comparison (shared scale; linear grayscale input)"
    )
    figure.savefig(HERE / "lossy_value_comparison.png", dpi=180)
    plt.close(figure)

    min_y, min_x = np.unravel_index(np.argmin(source), source.shape)
    crop_radius = 100
    y0 = max(0, min_y - crop_radius)
    y1 = min(source.shape[0], min_y + crop_radius)
    x0 = max(0, min_x - crop_radius)
    x1 = min(source.shape[1], min_x + crop_radius)
    signed_errors = [array - source for _, array in cases]
    error_limit = float(max(np.abs(error).max() for error in signed_errors))
    error_norm = TwoSlopeNorm(vmin=-error_limit, vcenter=0.0, vmax=error_limit)

    figure, axes = plt.subplots(2, 4, figsize=(17.5, 8.4), constrained_layout=True)
    for column, ((label, array), error) in enumerate(
        zip(cases, signed_errors, strict=True)
    ):
        value_image = axes[0, column].imshow(
            array[y0:y1, x0:x1], cmap="coolwarm", norm=value_norm
        )
        axes[0, column].set_title(f"{label}\nminimum = {array.min():.6f}")
        axes[0, column].set_axis_off()

        error_image = axes[1, column].imshow(
            error[y0:y1, x0:x1], cmap="PuOr_r", norm=error_norm
        )
        axes[1, column].set_title(
            f"decoded − source\nmax |error| = {np.abs(error).max():.6f}"
        )
        axes[1, column].set_axis_off()

    value_colorbar = figure.colorbar(
        value_image, ax=axes[0, :], shrink=0.82, pad=0.02
    )
    value_colorbar.set_label("Decoded sample value")
    error_colorbar = figure.colorbar(
        error_image, ax=axes[1, :], shrink=0.82, pad=0.02
    )
    error_colorbar.set_label("Signed error")
    figure.suptitle(
        "Detail around the source minimum: XYB creates a hard negative floor"
    )
    figure.savefig(HERE / "lossy_negative_detail.png", dpi=180)
    plt.close(figure)


def main() -> None:
    source = read_pfm(HERE / "input.pfm")
    source_tiff = tifffile.imread(HERE / "input.tiff")
    supplied_jxl = imagecodecs.jpegxl_decode((HERE / "output.jxl").read_bytes())

    cjxl_jxl = cjxl_round_trip(HERE / "input.pfm")
    cjxl_xyb = cjxl_round_trip(HERE / "input.pfm", linear=True)
    cjxl_non_perceptual = cjxl_round_trip(
        HERE / "input.pfm", linear=True, non_perceptual=True
    )
    installed_cjxl = cjxl_version()
    direct_jxl = imagecodecs_round_trip(source)
    tiff_jxl = tifffile_round_trip(source)

    normalized, source_min, source_range = normalize(source)
    normalized_jxl = tifffile_round_trip(normalized)
    restored_jxl = normalized_jxl * source_range + source_min

    print(f"tifffile: {tifffile.__version__}")
    print(f"imagecodecs: {imagecodecs.__version__}")
    print(f"JPEG XL backend: {imagecodecs.jpegxl_version()}")
    print(f"cjxl binary: {installed_cjxl}")
    print(f"distance={DISTANCE}, effort={EFFORT}")
    print(
        "input.pfm vs input.tiff max abs difference: "
        f"{np.max(np.abs(source - source_tiff)):.10g}"
    )
    print()
    print(
        f"{'case':<28} {'minimum':>12} {'maximum':>12} "
        f"{'< -0.004':>9} {'mean error':>12} {'max error':>12}"
    )
    print_result("source input.pfm", source, source)
    print_result("supplied output.jxl", supplied_jxl, source)
    print_result("cjxl binary", cjxl_jxl, source)
    print_result("cjxl lossy XYB", cjxl_xyb, source)
    print_result("cjxl non-perceptual", cjxl_non_perceptual, source)
    print_result("direct imagecodecs", direct_jxl, source)
    print_result("tifffile JPEG XL", tiff_jxl, source)
    print_result("tifffile after [0, 1]", restored_jxl, source)

    assert source.min() < -0.03
    assert supplied_jxl.min() < -0.03
    assert cjxl_jxl.min() < -0.03
    assert cjxl_xyb.min() > NEGATIVE_TAIL_LIMIT
    assert cjxl_non_perceptual.min() < -0.03
    assert direct_jxl.min() > NEGATIVE_TAIL_LIMIT
    assert tiff_jxl.min() > NEGATIVE_TAIL_LIMIT
    assert restored_jxl.min() < -0.03
    save_diagnostic_figures(
        source, direct_jxl, cjxl_xyb, cjxl_non_perceptual
    )
    print("Generated: jxl_negativity_repro/lossy_value_comparison.png")
    print("Generated: jxl_negativity_repro/lossy_negative_detail.png")
    print("\nReproduced: unnormalized imagecodecs/tifffile JPEG XL clips the tail.")


if __name__ == "__main__":
    main()
