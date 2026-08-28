import jax
import numpy as np
import pytest
from skimage.metrics import structural_similarity

from comptest.picax.ssim import ssim, ssim_map


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


@pytest.mark.parametrize("shape", [(37, 41), (17, 19, 23), (9, 11, 13, 7)])
@pytest.mark.parametrize("use_sample_covariance", [False, True])
def test_ssim_map_matches_skimage_gaussian(shape, use_sample_covariance):
    rng = _rng(0)
    a = rng.standard_normal(shape)
    b = a + 0.1 * rng.standard_normal(shape)
    data_range = 6.0

    ours = np.asarray(
        ssim_map(
            jax.numpy.asarray(a),
            jax.numpy.asarray(b),
            data_range=data_range,
            gaussian_weights=True,
            sigma=1.5,
            use_sample_covariance=use_sample_covariance,
        )
    )
    _, theirs = structural_similarity(
        a,
        b,
        full=True,
        data_range=data_range,
        gaussian_weights=True,
        sigma=1.5,
        use_sample_covariance=use_sample_covariance,
    )

    np.testing.assert_allclose(ours, theirs, atol=1e-10)


def test_ssim_map_matches_skimage_uniform_window():
    rng = _rng(1)
    shape = (33, 29)
    a = rng.standard_normal(shape)
    b = a + 0.1 * rng.standard_normal(shape)
    data_range = 6.0

    ours = np.asarray(
        ssim_map(
            jax.numpy.asarray(a),
            jax.numpy.asarray(b),
            data_range=data_range,
            gaussian_weights=False,
            win_size=7,
            use_sample_covariance=False,
        )
    )
    _, theirs = structural_similarity(
        a,
        b,
        full=True,
        data_range=data_range,
        gaussian_weights=False,
        win_size=7,
        use_sample_covariance=False,
    )

    np.testing.assert_allclose(ours, theirs, atol=1e-10)


def test_ssim_scalar_matches_skimage_mean():
    rng = _rng(2)
    shape = (40, 44)
    a = rng.standard_normal(shape)
    b = a + 0.2 * rng.standard_normal(shape)
    data_range = 8.0

    our_value = float(
        ssim(
            jax.numpy.asarray(a),
            jax.numpy.asarray(b),
            data_range=data_range,
            use_sample_covariance=False,
        )
    )
    their_value = structural_similarity(
        a,
        b,
        data_range=data_range,
        gaussian_weights=True,
        sigma=1.5,
        use_sample_covariance=False,
    )

    assert our_value == pytest.approx(their_value, abs=1e-10)


def test_ssim_batch_matches_per_slice_skimage():
    rng = _rng(3)
    stack_shape = (5, 48, 52)
    a = rng.standard_normal(stack_shape)
    b = a + 0.15 * rng.standard_normal(stack_shape)
    data_range = 8.0

    ours = np.asarray(
        ssim(
            jax.numpy.asarray(a),
            jax.numpy.asarray(b),
            data_range=data_range,
            use_sample_covariance=False,
            batch=True,
        )
    )

    theirs = np.array(
        [
            structural_similarity(
                a[i],
                b[i],
                data_range=data_range,
                gaussian_weights=True,
                sigma=1.5,
                use_sample_covariance=False,
            )
            for i in range(stack_shape[0])
        ]
    )

    np.testing.assert_allclose(ours, theirs, atol=1e-10)


def test_ssim_identical_inputs_is_one():
    rng = _rng(4)
    a = rng.standard_normal((30, 34))

    value = float(
        ssim(jax.numpy.asarray(a), jax.numpy.asarray(a), data_range=8.0)
    )
    assert value == pytest.approx(1.0, abs=1e-10)


def test_ssim_is_symmetric():
    rng = _rng(5)
    a = rng.standard_normal((30, 34))
    b = rng.standard_normal((30, 34))

    ab = float(ssim(jax.numpy.asarray(a), jax.numpy.asarray(b), data_range=8.0))
    ba = float(ssim(jax.numpy.asarray(b), jax.numpy.asarray(a), data_range=8.0))
    assert ab == pytest.approx(ba, abs=1e-10)


def test_ssim_map_is_jittable():
    rng = _rng(6)
    a = jax.numpy.asarray(rng.standard_normal((28, 32)))
    b = jax.numpy.asarray(rng.standard_normal((28, 32)))

    eager = ssim_map(a, b, data_range=8.0)
    jitted = jax.jit(lambda x, y: ssim_map(x, y, data_range=8.0))(a, b)

    np.testing.assert_allclose(np.asarray(eager), np.asarray(jitted), atol=1e-10)
