"""
ND Multi-Scale Structural Similarity Index (MS-SSIM) in JAX.

Follows Wang, Z., Simoncelli, E. P., & Bovik, A. C. (2003). "Multiscale
structural similarity for image quality assessment." 37th Asilomar
Conference on Signals, Systems & Computers, vol. 2, 1398-1402.
DOI: 10.1109/ACSSC.2003.1292216

Note this is *not* algebraically equal to :func:`comptest.picax.ssim.ssim`
even at a single scale: Wang's MS-SSIM combines the scalar means of the
luminance and contrast-structure maps (``mean(l) * mean(cs)``), whereas
single-scale SSIM averages their pointwise product (``mean(l * cs)``). The
two only coincide when ``l`` and ``cs`` are uncorrelated across the map,
which is not generally true -- so expect close, not exact, agreement between
``ms_ssim(a, b, weights=(1.0,))`` and ``ssim(a, b)``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import jax.numpy as jnp
from jax import Array

from comptest.picax._filters import gaussian_radius, separable_correlate, uniform_kernel1d
from comptest.picax.ssim import _crop_width, crop_map, ssim_components

# Wang et al. (2003), Table 1.
MS_SSIM_WEIGHTS = (0.0448, 0.2856, 0.3001, 0.2363, 0.1333)


class MSSSIMResult(NamedTuple):
    value: Array
    cs_maps: tuple[Array, ...]
    l_map: Array
    weights: tuple[float, ...]


def downsample(x: Array, axes: Sequence[int]) -> Array:
    """
    ND generalisation of Wang's ``imfilter(x, ones(2)/4, 'symmetric', 'same')``
    followed by a stride-2 decimation: a 2-tap box mean along each of
    ``axes``, then every other sample kept along those same axes.
    """
    kernel = uniform_kernel1d(2, dtype=x.dtype)
    filtered = separable_correlate(x, kernel, axes)

    slices: list[slice] = [slice(None)] * x.ndim
    for axis in axes:
        slices[axis] = slice(None, None, 2)
    return filtered[tuple(slices)]


def _resolved_win_size(
    *, gaussian_weights: bool, sigma: float, win_size: int | None
) -> int:
    if gaussian_weights:
        return 2 * gaussian_radius(sigma) + 1
    return 7 if win_size is None else win_size


def _max_scales(extent: int, win_size: int) -> int:
    scales = 0
    size = extent
    while size >= win_size:
        scales += 1
        size = -(-size // 2)  # ceil division, matching downsample's decimation
    return scales


def ms_ssim(
    a: Array,
    b: Array,
    *,
    data_range: float,
    weights: Sequence[float] = MS_SSIM_WEIGHTS,
    win_size: int | None = None,
    gaussian_weights: bool = True,
    sigma: float = 1.5,
    use_sample_covariance: bool = False,
    K1: float = 0.01,
    K2: float = 0.03,
    batch: bool = False,
    batch_size: int = 1,
    crop: bool = True,
    eps: float = 1e-8,
) -> MSSSIMResult:
    """
    Multi-scale SSIM.

    At each of ``len(weights)`` scales the local SSIM components are computed
    (see :func:`comptest.picax.ssim.ssim_components`), then the inputs are
    box-downsampled by 2 (:func:`downsample`) for the next scale. The scalar
    result combines the per-scale means as in Wang et al. (2003), Eq. 7::

        MS-SSIM = mean(l_M)**weights[-1] * prod_j mean(cs_j)**weights[j]

    where ``M`` is the coarsest scale and the product runs over all scales
    (including ``M``).

    Parameters
    ----------
    a, b, data_range, win_size, gaussian_weights, sigma, use_sample_covariance,
    K1, K2, batch, batch_size, crop:
        As in :func:`comptest.picax.ssim.ssim_components` / ``ssim``.
    weights:
        Per-scale exponents, finest scale first. The last weight is applied
        to both the coarsest scale's contrast-structure mean and its
        luminance mean, per Wang et al. Defaults to the 5-scale weights from
        Table 1 of Wang et al. (2003); pass fewer entries (e.g. 3) for
        smaller inputs.
    eps:
        Per-scale means are clamped to at least ``eps`` before being raised
        to a (generally fractional) power, since natural images can produce
        slightly negative local SSIM components, which would otherwise raise
        a negative base to a fractional exponent (NaN).

    Returns
    -------
    MSSSIMResult
        ``value`` (scalar, or shape ``(batch,)`` when ``batch=True``),
        ``cs_maps`` (one uncropped, unclamped contrast-structure map per
        scale, finest first, decreasing spatial size), ``l_map`` (the
        uncropped luminance map at the coarsest scale), and ``weights`` as
        passed.

    Raises
    ------
    ValueError
        If any spatial axis is too small to support ``len(weights)`` scales
        at the resolved window size.
    """
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} != {b.shape}")

    weights = tuple(weights)
    n_scales = len(weights)
    if n_scales < 1:
        raise ValueError("weights must be non-empty")

    spatial_axes = tuple(range(1, a.ndim)) if batch else tuple(range(a.ndim))
    resolved_win_size = _resolved_win_size(
        gaussian_weights=gaussian_weights, sigma=sigma, win_size=win_size
    )

    for axis in spatial_axes:
        extent = a.shape[axis]
        max_scales = _max_scales(extent, resolved_win_size)
        if max_scales < n_scales:
            raise ValueError(
                f"axis {axis} has extent {extent}, which supports at most "
                f"{max_scales} scale(s) at win_size={resolved_win_size}; "
                f"requested {n_scales} scales (len(weights)={n_scales}). "
                "Pass fewer weights, a smaller sigma/win_size, or crop the "
                "input."
            )

    dtype = jnp.result_type(a.dtype, b.dtype, jnp.float32)
    cur_a = a.astype(dtype)
    cur_b = b.astype(dtype)

    pad = _crop_width(win_size=win_size, gaussian_weights=gaussian_weights, sigma=sigma)

    cs_maps: list[Array] = []
    cs_means: list[Array] = []
    l_map: Array | None = None
    l_mean: Array | None = None

    for scale in range(n_scales):
        components = ssim_components(
            cur_a,
            cur_b,
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

        cs_map = components.contrast_structure
        cs_maps.append(cs_map)
        cs_cropped = crop_map(cs_map, pad=pad, batch=batch) if crop else cs_map
        cs_means.append(jnp.mean(cs_cropped, axis=spatial_axes, dtype=jnp.float64))

        if scale == n_scales - 1:
            l_map = components.luminance
            l_cropped = crop_map(l_map, pad=pad, batch=batch) if crop else l_map
            l_mean = jnp.mean(l_cropped, axis=spatial_axes, dtype=jnp.float64)
        else:
            cur_a = downsample(cur_a, spatial_axes)
            cur_b = downsample(cur_b, spatial_axes)

    assert l_map is not None and l_mean is not None  # guaranteed by n_scales >= 1

    value = jnp.clip(l_mean, eps, None) ** weights[-1]
    for weight, cs_mean in zip(weights, cs_means, strict=True):
        value = value * jnp.clip(cs_mean, eps, None) ** weight

    return MSSSIMResult(
        value=value,
        cs_maps=tuple(cs_maps),
        l_map=l_map,
        weights=weights,
    )
