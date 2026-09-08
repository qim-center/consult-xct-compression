from typing import Any

import jax
import numpy.typing as npt
from picax.api.jax import psnr as _psnr, ssim_local as _ssim_local

# picax promotes to `jnp.result_type(x, y, jnp.float64)`, which silently
# collapses to float32 unless x64 is enabled
jax.config.update("jax_enable_x64", True)

SSIM_PRESET = "wang-2004-implementation"


def ssim_map(
    reference: npt.NDArray,
    distorted: npt.NDArray,
    *,
    data_range: float,
    preset: str = SSIM_PRESET,
    **kwargs: Any,
) -> npt.NDArray:
    """Local SSIM at every voxel, over as many axes as the inputs have.

    The returned map is float64 and the same shape as the inputs, so for a whole
    volume it is 8 bytes per voxel. Callers that only need the distribution
    should summarise it and drop it.

    Raises if any axis is shorter than `SSIM_MIN_EXTENT`, which is what a
    z-truncated smoke-test volume runs into.
    """
    return _ssim_local(
        reference, distorted, dynamic_range=data_range, preset=preset, **kwargs
    )


def psnr(
    reference: npt.NDArray,
    distorted: npt.NDArray,
    *,
    data_range: float,
) -> float:
    """Peak signal-to-noise ratio in dB over the whole array.

    `inf` for identical inputs, which is why callers test for a lossless round
    trip before asking.
    """
    return float(_psnr(reference, distorted, dynamic_range=data_range))


def rmse_from_psnr(psnr_db: float, *, data_range: float) -> float:
    """Invert `psnr = 20 log10(data_range / rmse)`.

    Exact, and saves a second pass over the volume just to re-accumulate the
    squared error that PSNR already reduced.
    """
    return data_range / 10 ** (psnr_db / 20)
