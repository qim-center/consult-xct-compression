"""
ND Structural Similarity Index (SSIM) in JAX.

Follows Wang, Z., Bovik, A. C., Sheikh, H. R., & Simoncelli, E. P. (2004).
"Image quality assessment: from error visibility to structural similarity."
IEEE Transactions on Image Processing, 13(4), 600-612.
DOI: 10.1109/TIP.2003.819861

The maths mirrors :func:`skimage.metrics.structural_similarity`, but the
defaults here are Wang's canonical parametrisation (``gaussian_weights=True``,
``sigma=1.5``, ``use_sample_covariance=False``) rather than skimage's own
defaults (``gaussian_weights=False``, ``use_sample_covariance=True``) -- pass
skimage's values explicitly if you want a drop-in match to skimage's defaults.

Unlike skimage, these functions place no limit on dimensionality: every axis
(other than an optional leading batch axis) is treated as part of the
correlation window.
"""

from __future__ import annotations

from typing import NamedTuple

import jax.numpy as jnp
from jax import Array, lax

from _filters import (
    gaussian_kernel1d,
    gaussian_radius,
    separable_correlate,
    uniform_kernel1d,
)


class SSIMComponents(NamedTuple):
    """
    The two multiplicative terms of the SSIM index, kept separate so that
    :mod:`comptest.picax.msssim` can combine contrast-structure across scales
    without redoing the local statistics.
    """

    luminance: Array
    contrast_structure: Array

    @property
    def map(self) -> Array:
        """The full local SSIM map, i.e. ``luminance * contrast_structure``."""
        return self.luminance * self.contrast_structure


def _resolve_window(
    *, gaussian_weights: bool, sigma: float, win_size: int | None, dtype: jnp.dtype
) -> tuple[Array, int]:
    if gaussian_weights:
        kernel = gaussian_kernel1d(sigma, dtype=dtype)
        resolved_win_size = kernel.shape[0]
        if win_size is not None and win_size != resolved_win_size:
            raise ValueError(
                "win_size is ignored (and derived from sigma) when "
                "gaussian_weights=True; got an explicit win_size="
                f"{win_size} that disagrees with the derived value "
                f"{resolved_win_size}."
            )
        return kernel, resolved_win_size

    resolved_win_size = 7 if win_size is None else win_size
    if resolved_win_size % 2 == 0:
        raise ValueError(f"win_size must be odd, got {resolved_win_size}")
    return uniform_kernel1d(resolved_win_size, dtype=dtype), resolved_win_size


def _check_spatial_extent(shape: tuple[int, ...], win_size: int) -> None:
    for axis, extent in enumerate(shape):
        if extent < win_size:
            raise ValueError(
                f"win_size ({win_size}) exceeds the extent of axis {axis} "
                f"({extent}). Either ensure every spatial axis is at least "
                "win_size, or pass a smaller win_size / sigma."
            )


def _ssim_components_single(
    a: Array,
    b: Array,
    *,
    data_range: float,
    win_size: int | None,
    gaussian_weights: bool,
    sigma: float,
    use_sample_covariance: bool,
    K1: float,
    K2: float,
) -> SSIMComponents:
    """SSIM components for a single (non-batched) ND array pair."""
    dtype = jnp.result_type(a.dtype, b.dtype, jnp.float32)
    a = a.astype(dtype)
    b = b.astype(dtype)

    axes = tuple(range(a.ndim))
    kernel, resolved_win_size = _resolve_window(
        gaussian_weights=gaussian_weights, sigma=sigma, win_size=win_size, dtype=dtype
    )
    _check_spatial_extent(a.shape, resolved_win_size)

    n_points = resolved_win_size**a.ndim
    cov_norm = n_points / (n_points - 1) if use_sample_covariance else 1.0

    def filt(x: Array) -> Array:
        return separable_correlate(x, kernel, axes)

    ua = filt(a)
    ub = filt(b)
    uaa = filt(a * a)
    ubb = filt(b * b)
    uab = filt(a * b)

    var_a = cov_norm * (uaa - ua * ua)
    var_b = cov_norm * (ubb - ub * ub)
    cov_ab = cov_norm * (uab - ua * ub)

    C1 = (K1 * data_range) ** 2
    C2 = (K2 * data_range) ** 2

    luminance = (2 * ua * ub + C1) / (ua**2 + ub**2 + C1)
    contrast_structure = (2 * cov_ab + C2) / (var_a + var_b + C2)

    return SSIMComponents(luminance=luminance, contrast_structure=contrast_structure)


def ssim_components(
    a: Array,
    b: Array,
    *,
    data_range: float,
    win_size: int | None = None,
    gaussian_weights: bool = True,
    sigma: float = 1.5,
    use_sample_covariance: bool = False,
    K1: float = 0.01,
    K2: float = 0.03,
    batch: bool = False,
    batch_size: int = 1,
) -> SSIMComponents:
    """
    Compute the local luminance and contrast-structure terms of SSIM.

    Parameters
    ----------
    a, b:
        Arrays of identical shape. If ``batch`` is True, axis 0 is treated as
        a batch axis and every other axis is spatial; otherwise every axis is
        spatial (a genuine ND window).
    data_range:
        The difference between the maximum and minimum possible values in
        ``a``/``b``. Unlike skimage, this is not inferred from dtype -- it
        must always be supplied explicitly.
    win_size:
        Side length of the (uniform) window. Ignored when
        ``gaussian_weights=True``, in which case the window size is derived
        from ``sigma`` to match :func:`scipy.ndimage.gaussian_filter`.
    gaussian_weights, sigma, use_sample_covariance, K1, K2:
        As in Wang et al. (2004) / :func:`skimage.metrics.structural_similarity`.
    batch_size:
        Only used when ``batch=True``. Number of batch elements processed at
        once via :func:`jax.lax.map`, so peak memory stays proportional to
        ``batch_size`` full-size arrays rather than the whole batch -- e.g.
        for a ``(1000, 1000, 1000)`` float32 stack, computing all batch
        elements at once would need on the order of 10 full-size float32
        temporaries (~40 GB); ``batch_size=1`` keeps this to a single slice.

    Returns
    -------
    SSIMComponents
        ``luminance`` and ``contrast_structure``. Each has the input's shape
        (or, when ``batch=True``, the input's shape with the spatial part
        unchanged and axis 0 equal to the batch size). ``.map`` gives their
        product, the full local SSIM map.

    Notes
    -----
    Precision: results are computed at (at least) float32. The variance/
    covariance terms involve a subtraction of near-equal quantities, so for
    parity with skimage's float64 accumulation, callers should
    ``jax.config.update("jax_enable_x64", True)`` -- this module never
    mutates global JAX configuration itself.
    """
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} != {b.shape}")
    if a.ndim < 1:
        raise ValueError("inputs must have at least one dimension")
    if batch and a.ndim < 2:
        raise ValueError("batch=True requires at least one spatial axis beyond axis 0")

    def per_sample(sample_a: Array, sample_b: Array) -> SSIMComponents:
        return _ssim_components_single(
            sample_a,
            sample_b,
            data_range=data_range,
            win_size=win_size,
            gaussian_weights=gaussian_weights,
            sigma=sigma,
            use_sample_covariance=use_sample_covariance,
            K1=K1,
            K2=K2,
        )

    if not batch:
        return per_sample(a, b)

    return lax.map(
        lambda pair: per_sample(*pair), (a, b), batch_size=batch_size
    )


def ssim_map(
    a: Array,
    b: Array,
    *,
    data_range: float,
    win_size: int | None = None,
    gaussian_weights: bool = True,
    sigma: float = 1.5,
    use_sample_covariance: bool = False,
    K1: float = 0.01,
    K2: float = 0.03,
    batch: bool = False,
    batch_size: int = 1,
) -> Array:
    """The full local SSIM map. See :func:`ssim_components` for parameters."""
    components = ssim_components(
        a,
        b,
        data_range=data_range,
        win_size=win_size,
        gaussian_weights=gaussian_weights,
        sigma=sigma,
        use_sample_covariance=use_sample_covariance,
        K1=K1,
        K2=K2,
        batch=batch,
        batch_size=batch_size,
    )
    return components.map


def _crop_width(*, win_size: int | None, gaussian_weights: bool, sigma: float) -> int:
    if gaussian_weights:
        return gaussian_radius(sigma)
    resolved = 7 if win_size is None else win_size
    return (resolved - 1) // 2


def crop_map(smap: Array, *, pad: int, batch: bool) -> Array:
    """Drop ``pad`` samples from each spatial edge, as skimage does before averaging."""
    if pad == 0:
        return smap
    spatial_axes = range(1, smap.ndim) if batch else range(smap.ndim)
    slices: list[slice] = [slice(None)] * smap.ndim
    for axis in spatial_axes:
        slices[axis] = slice(pad, smap.shape[axis] - pad)
    return smap[tuple(slices)]


def ssim(
    a: Array,
    b: Array,
    *,
    data_range: float,
    win_size: int | None = None,
    gaussian_weights: bool = True,
    sigma: float = 1.5,
    use_sample_covariance: bool = False,
    K1: float = 0.01,
    K2: float = 0.03,
    batch: bool = False,
    batch_size: int = 1,
    crop: bool = True,
) -> Array:
    """
    Mean SSIM index.

    Returns a scalar, or an array of shape ``(batch,)`` when ``batch=True``.
    See :func:`ssim_components` for parameter documentation.

    ``crop`` mirrors skimage: edge windows are contaminated by boundary
    padding, so by default ``(win_size - 1) // 2`` samples are dropped from
    each spatial edge before averaging.
    """
    smap = ssim_map(
        a,
        b,
        data_range=data_range,
        win_size=win_size,
        gaussian_weights=gaussian_weights,
        sigma=sigma,
        use_sample_covariance=use_sample_covariance,
        K1=K1,
        K2=K2,
        batch=batch,
        batch_size=batch_size,
    )

    if crop:
        pad = _crop_width(win_size=win_size, gaussian_weights=gaussian_weights, sigma=sigma)
        smap = crop_map(smap, pad=pad, batch=batch)

    spatial_axes = tuple(range(1, smap.ndim)) if batch else tuple(range(smap.ndim))
    return jnp.mean(smap, axis=spatial_axes, dtype=jnp.float64)
