"""
Separable ND correlation filters implemented in JAX.

These mirror the behaviour of :mod:`scipy.ndimage` closely enough that the SSIM
implementations built on top of them reproduce
:func:`skimage.metrics.structural_similarity` to floating point precision.
"""

from __future__ import annotations

from collections.abc import Sequence

import jax.numpy as jnp
from jax import Array, lax

# scipy.ndimage's boundary mode names do not agree with numpy's/jax's:
#   scipy 'reflect' == numpy 'symmetric'  (d c b a | a b c d | d c b a)
#   scipy 'mirror'  == numpy 'reflect'    (d c b   | a b c d |   c b a)
# skimage filters SSIM with scipy's 'reflect', so 'symmetric' is what we need.
SCIPY_REFLECT = "symmetric"


def gaussian_radius(sigma: float, truncate: float = 3.5) -> int:
    """
    Kernel radius used by :func:`scipy.ndimage.gaussian_filter`.

    With Wang et al. (2004) defaults (``sigma=1.5``, ``truncate=3.5``) this gives
    a radius of 5, i.e. the canonical 11-tap filter.
    """
    return int(truncate * sigma + 0.5)


def gaussian_kernel1d(
    sigma: float, truncate: float = 3.5, *, dtype: jnp.dtype
) -> Array:
    """
    Normalised 1D Gaussian kernel of length ``2 * gaussian_radius(...) + 1``.
    """
    if sigma <= 0:
        raise ValueError(f"sigma must be positive, got {sigma}")

    radius = gaussian_radius(sigma, truncate)
    x = jnp.arange(-radius, radius + 1, dtype=dtype)
    kernel = jnp.exp(-0.5 * (x / sigma) ** 2)

    return kernel / kernel.sum()


def uniform_kernel1d(size: int, *, dtype: jnp.dtype) -> Array:
    """Normalised 1D box kernel of length ``size``."""
    if size < 1:
        raise ValueError(f"size must be at least 1, got {size}")

    return jnp.full((size,), 1 / size, dtype=dtype)


def correlate1d(
    x: Array, kernel: Array, axis: int, *, mode: str = SCIPY_REFLECT
) -> Array:
    """
    Correlate ``x`` with a 1D ``kernel`` along ``axis``, preserving shape.

    Implemented as a padded sum of shifted slices rather than
    :func:`jax.lax.conv_general_dilated`, which XLA limits to three spatial
    dimensions. This formulation is rank-agnostic and XLA fuses the taps into a
    single loop under ``jit``.
    """
    (taps,) = kernel.shape
    axis = axis % x.ndim

    # An even-length kernel has no exact centre; scipy places the origin at
    # taps // 2, so the left pad is one smaller than the right.
    pad_left = (taps - 1) // 2
    pad_right = taps // 2

    pad_width = [(0, 0)] * x.ndim
    pad_width[axis] = (pad_left, pad_right)
    padded = jnp.pad(x, pad_width, mode=mode)

    length = x.shape[axis]
    out = kernel[0] * lax.slice_in_dim(padded, 0, length, axis=axis)
    for i in range(1, taps):
        out = out + kernel[i] * lax.slice_in_dim(padded, i, i + length, axis=axis)

    return out


def separable_correlate(
    x: Array,
    kernel: Array,
    axes: Sequence[int],
    *,
    mode: str = SCIPY_REFLECT,
) -> Array:
    """
    Apply the same 1D ``kernel`` along each axis in ``axes`` in turn.

    A separable ND filter is the composition of its 1D passes, so this is
    equivalent to correlating with the outer product of the kernel with itself
    over ``axes`` -- at a fraction of the cost.
    """
    for axis in axes:
        x = correlate1d(x, kernel, axis, mode=mode)

    return x
