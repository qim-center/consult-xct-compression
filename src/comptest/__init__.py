from logging import DEBUG

from comptest import (
    imagemagick as imagemagick,
    libtiff as libtiff,
    tifffile as tifffile,
)
from comptest.logging import setup_logging

setup_logging(log_level=DEBUG)
