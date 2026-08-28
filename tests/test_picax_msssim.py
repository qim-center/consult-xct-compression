import jax
import numpy as np
import pytest
import sewar

from comptest.picax.msssim import ms_ssim
from comptest.picax.ssim import ssim


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_ms_ssim_single_scale_is_close_to_ssim():
    # Wang's MS-SSIM combines mean(l) * mean(cs), whereas single-scale SSIM
    # averages the pointwise product mean(l * cs); these coincide only when
    # l and cs are uncorrelated across the map, so this is an approximate
    # check, not exact equality.
    rng = _rng(0)
    shape = (64, 68)
    a = rng.standard_normal(shape)
    b = a + 0.1 * rng.standard_normal(shape)
    data_range = 6.0

    result = ms_ssim(
        jax.numpy.asarray(a), jax.numpy.asarray(b), data_range=data_range, weights=(1.0,)
    )
    single_scale = float(ssim(jax.numpy.asarray(a), jax.numpy.asarray(b), data_range=data_range))

    assert float(result.value) == pytest.approx(single_scale, abs=0.05)


def test_ms_ssim_matches_sewar_approximately():
    rng = _rng(1)
    shape = (161, 157)
    a = rng.integers(0, 256, size=shape).astype(np.uint8)
    noise = rng.normal(scale=8, size=shape)
    b = np.clip(a.astype(np.float64) + noise, 0, 255).astype(np.uint8)

    result = ms_ssim(
        jax.numpy.asarray(a.astype(np.float64)),
        jax.numpy.asarray(b.astype(np.float64)),
        data_range=255.0,
    )

    reference = float(np.real(sewar.msssim(a[..., None], b[..., None])))

    assert float(result.value) == pytest.approx(reference, abs=0.05)


def test_ms_ssim_identical_inputs_is_one():
    rng = _rng(2)
    a = rng.standard_normal((160, 164))

    result = ms_ssim(jax.numpy.asarray(a), jax.numpy.asarray(a), data_range=8.0)
    assert float(result.value) == pytest.approx(1.0, abs=1e-8)


def test_ms_ssim_decreases_with_noise():
    rng = _rng(3)
    a = rng.standard_normal((160, 164))
    data_range = 8.0

    values = []
    for noise_scale in (0.0, 0.5, 1.0, 2.0):
        b = a + noise_scale * rng.standard_normal(a.shape)
        result = ms_ssim(jax.numpy.asarray(a), jax.numpy.asarray(b), data_range=data_range)
        values.append(float(result.value))

    assert values == sorted(values, reverse=True)


def test_ms_ssim_cs_maps_shapes_halve_per_scale():
    rng = _rng(4)
    a = rng.standard_normal((160, 164))
    b = a + 0.1 * rng.standard_normal(a.shape)

    result = ms_ssim(
        jax.numpy.asarray(a), jax.numpy.asarray(b), data_range=8.0, weights=(0.3, 0.3, 0.4)
    )

    assert len(result.cs_maps) == 3
    shapes = [cs_map.shape for cs_map in result.cs_maps]
    for prev, cur in zip(shapes, shapes[1:], strict=True):
        for prev_dim, cur_dim in zip(prev, cur, strict=True):
            assert cur_dim == pytest.approx(prev_dim / 2, abs=1)


def test_ms_ssim_raises_for_too_small_input():
    a = jax.numpy.asarray(np.random.default_rng(5).standard_normal((20, 20)))
    b = jax.numpy.asarray(np.random.default_rng(6).standard_normal((20, 20)))

    with pytest.raises(ValueError, match="scale"):
        ms_ssim(a, b, data_range=8.0)
