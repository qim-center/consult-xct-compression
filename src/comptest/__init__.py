from logging import DEBUG

from comptest import libtiff as libtiff
from comptest.imagemagick import imagemagick as imagemagick
from comptest.logging import setup_logging
from comptest.sh import (
    ProcessMemoryUsage as ProcessMemoryUsage,
    ProcessResult as ProcessResult,
    ProcessTiming as ProcessTiming,
    run_process as run_process,
)

setup_logging(log_level=DEBUG)
