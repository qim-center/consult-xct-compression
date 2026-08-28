import jax

# The variance/covariance terms in SSIM subtract near-equal quantities, so
# tests compare against skimage's float64 computation at matching precision.
jax.config.update("jax_enable_x64", True)
