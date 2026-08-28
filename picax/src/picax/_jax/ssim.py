from types import EllipsisType
from typing import TypeVar, Literal, cast


import jax.numpy as jnp

from jaxtyping import Array, Real, Integer

FloatIntT = TypeVar("FloatIntT", float, int)


def _resolve_window_and_kernel(
    *,
    window_size: tuple[int, ...] | None,
    weights: Literal["gaussian", "uniform"] | None,
    sigma: float | None,
) -> tuple[int, Real[Array, "*window_shape"]]:
    if weights == "uniform" and sigma is not None:
        raise ValueError(
            "sigma must be None when weights is 'uniform', got "
            f"sigma={sigma}, weights={weights}"
        )

    ...


def ssim_local(
    x: Real[Array, "*shape"],
    y: Real[Array, "*shape"],
    *,
    dynamic_range: float | int | Literal["dtype", "range"],
    preset: Literal["wang-2004", "skimage-default"] | None = None,
    window_size: int | tuple[int, ...] | None | EllipsisType = ...,
    weights: Literal["gaussian", "uniform"] | EllipsisType = ...,
    covariance_normalization: Literal["sample", "population"] | EllipsisType = ...,
    sigma: float | tuple[float | int, ...] | None | EllipsisType = ...,
    K1: float = 0.01,
    K2: float = 0.03,
    C3: float | None = None,
    alpha: float | int = 1,
    beta: float | int = 1,
    gamma: float | int = 1,
):
    """
    TODO TEXT

    Args:
        x: First input image.
        y: Second input image.
        dynamic_range: The dynamic range of the images (i.e. the difference between
            the maximum and the minimum possible values). This is used to scale the
            K1 and K2 constants, which are defined as fractions of the dynamic range.
            If set to "dtype", the dynamic range is inferred from the dtype of `x`.
            If set to "range", the dynamic range is inferred from the actual range of
            `x` and `y`.

            Note that using "dtype" with floating point images is not supported
            as it would not be well-defined.
        preset: A preset configuration for the SSIM computation.
            This can be used to configurations that correctly match common
            implementations of SSIM.

            Available presets:
            - "wang-2004-implementation":  Matches the original SSIM implementation
                by Wang et al. (2004).
                This sets the window size to 11, uses a Gaussian window,
                and normalizes the covariance by the sample size (N).
                Note: the paper describes the unbiased estimator
                (N-1, Bessel's correction) in Eq. (4) and Eq. (11),
                but the implementation in the paper uses the biased estimator (N)
                in the implementation (https://www.cns.nyu.edu/~lcv/ssim/ssim_index.m).
                As such, this preset matches the _implementation_ by Wang et al. (2004).
            - "wang-2004-paper": Matches the original SSIM paper by Wang et al. (2004).
                This applies Bessel's correction (N-1) as in the paper,
                unlike the implementation.
                Otherwise this matches the "wang-2004-implementation" preset.
            - "skimage-default": Matches the default configuration used in `skimage`.
        window_size: TODO
        weights: TODO
        covariance_normalization:
            "sample" scales covariance by 1/(1-∑_i w_i^2) (Bessel's correction),
            which assumes the inputs are samples from a larger 'population'.
            "population" does not apply a degree-of-freedom compensation, thus
            assuming the inputs are the entire 'population'.
        sigma: TODO
        K1: Stabilising constant (<< 1) for when sum of first moments is close to zero.
            Defaults to 0.01 as in Wang et al. (2004)
        K2: Stabilising constant (<< 1) for when sum of second moments is close to zero.
            Defaults to 0.03 as in Wang et al. (2004)
        C3: Stabilising constant for when cross-correlation is close to zero.
            Defaults to $C_3 = C_2 / 2$ where $C_2 = (K_2 L)^2$
            with $L$ being the dynamic range.
        alpha: Exponent that controls influence of luminence.
            Defaults to 1 as in Wang et al. (2004)
        beta: Exponent that controls influence of constrast.
            Defaults to 1 as in Wang et al. (2004)
        gamma: Exponent that controls influence of structure.
            Defaults to 1 as in Wang et al. (2004)

    Raises:
        ValueError
    """
    # Validate constants
    if not alpha > 0:
        raise ValueError(f"alpha must be positive, got {alpha}")
    if not beta > 0:
        raise ValueError(f"beta must be positive, got {beta}")
    if not gamma > 0:
        raise ValueError(f"gamma must be positive, got {gamma}")

    # Validate preset
    if preset is not None and not all(
        val is ...
        for val in (
            window_size,
            weights,
            covariance_normalization,
            sigma,
        )
    ):
        raise ValueError(
            "When a preset is specified, all other parameters must be left as default"
        )

    # Apply preset
    match preset:
        case "wang-2004-implementation":
            window_size = 11
            weights = "gaussian"
            covariance_normalization = "population"
            sigma = 1.5
        case "wang-2004-paper":
            window_size = 11
            weights = "gaussian"
            covariance_normalization = "sample"
            sigma = 1.5
        case "skimage-default":
            ...
        case _:
            raise ValueError(f"Unknown preset: {preset}")

    # Check that all parameters have been set
    if window_size is ...:
        raise ValueError(
            "window_size must be specified, either directly or via a preset"
        )
    if weights is ...:
        raise ValueError("weights must be specified, either directly or via a preset")
    if covariance_normalization is ...:
        raise ValueError(
            "covariance_normalization must be specified, either directly or via a preset"
        )
    if sigma is ...:
        raise ValueError("sigma must be specified, either directly or via a preset")

    # Check shapes
    if not x.shape == y.shape:
        raise ValueError(
            f"x and y must have same shape. Their shapes are: {x.shape=}, {y.shape=}"
        )

    # Resolve window_size
    if isinstance(window_size, int):
        window_size = tuple(window_size for i in range(x.ndim))

    # Resolve sigma
    if isinstance(sigma, (float, int)):
        sigma = tuple(sigma for i in range(x.ndim))

    if sigma is not None:
        sigma = tuple(float(s) for s in sigma)
        # TODO: Does type narrowing correctly get inferred here?

    # Resolve dynamic range
    match dynamic_range:
        case "dtype":
            if not x.dtype == y.dtype:
                raise ValueError(
                    "When dynamic_range is 'dtype', x and y must have the same "
                    f"dtype. Dtypes are: {x.dtype=}, y.dtype={y.dtype=}"
                )

            if jnp.issubdtype(x.dtype, jnp.floating):
                raise ValueError(
                    "When dynamic_range is 'dtype', x and y must have an integer "
                    f"dtype. Got x.dtype={x.dtype}, y.dtype={y.dtype}"
                )

            min_val = jnp.iinfo(x.dtype).min
            max_val = jnp.iinfo(x.dtype).max
            dynamic_range = float(max_val - min_val)
        case "range":
            min_val = jnp.minimum(x.min(), y.min())
            max_val = jnp.maximum(x.max(), y.max())
            dynamic_range = float(max_val - min_val)
        case float() | int():
            dynamic_range = float(dynamic_range)
        case _:
            raise ValueError(
                "dynamic_range must be a float, int, 'dtype', or 'range'. "
                f"Got {dynamic_range} of type {type(dynamic_range)}"
            )

    # Resolve constants
    C1 = (K1 * dynamic_range) ** 2
    C2 = (K2 * dynamic_range) ** 2
    if C3 is None:
        C3 = C2 / 2

    # Type promotion for precision
    dtype = jnp.result_type(x, y, jnp.float64)
    x = x.astype(dtype)
    y = y.astype(dtype)
