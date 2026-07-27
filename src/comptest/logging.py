import logging


def setup_logging(log_file: str | None = None, log_level: int = logging.INFO) -> None:
    """
    Set up logging for the application.

    Args:
        log_file (str | None): Path to the log file. If None, logs will be printed to stdout.
        log_level (int): Logging level. Default is logging.INFO.
    """
    logger = logging.getLogger()
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logging.getLogger('numcodecs').setLevel(logging.WARNING)
    logging.getLogger('h5py').setLevel(logging.WARNING)
    logging.getLogger('zarr').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    else:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
