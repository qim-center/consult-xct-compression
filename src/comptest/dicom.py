# All LLM :(

import io
import os
import resource
import sys
import weakref
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from math import prod
from multiprocessing import get_context
from multiprocessing.shared_memory import SharedMemory
from typing import Any

import numpy as np
import numpy.typing as npt
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.pixels import pixel_array
from pydicom.uid import (
    PYDICOM_IMPLEMENTATION_UID,
    UID,
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)

# A codec as the pool needs it: everything except the slice data.
# Keys: transfer_syntax_uid, encoding_plugin, decoding_plugin, encoder_kwargs.
CodecSpec = dict[str, Any]


def build_slice_dataset(
    rows: int,
    columns: int,
    dtype: npt.DTypeLike,
    *,
    study_uid: str,
    series_uid: str,
    instance_number: int,
) -> FileDataset:
    """
    The minimal valid single-frame Secondary Capture header for one slice.

    Only what the IOD requires: no geometry, since the files only need to be
    valid DICOM for the compression measurements, not useful for viewing.
    """
    dtype = np.dtype(dtype)

    if dtype not in (np.uint8, np.uint16):
        raise TypeError(f"Expected uint8 or uint16 slices, got {dtype}")

    bits = dtype.itemsize * 8
    sop_instance_uid = generate_uid()

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

    ds = FileDataset("", {}, file_meta=file_meta, preamble=b"\x00" * 128)

    # SOP Common
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = sop_instance_uid

    # Patient, General Study: Type 2 attributes may be empty but must exist.
    ds.PatientName = ""
    ds.PatientID = ""
    ds.PatientBirthDate = ""
    ds.PatientSex = ""
    ds.StudyInstanceUID = study_uid
    ds.StudyDate = ""
    ds.StudyTime = ""
    ds.StudyID = ""
    ds.AccessionNumber = ""
    ds.ReferringPhysicianName = ""

    # General Series: shared by every slice, which is what makes it a stack.
    ds.SeriesInstanceUID = series_uid
    ds.SeriesNumber = 1
    ds.Modality = "OT"

    # General Image, SC Equipment
    ds.InstanceNumber = instance_number
    ds.PatientOrientation = ""
    ds.ConversionType = "WSD"

    # Image Pixel
    ds.Rows = rows
    ds.Columns = columns
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = bits
    ds.BitsStored = bits
    ds.HighBit = bits - 1
    ds.PixelRepresentation = 0

    return ds


def encode_slice(
    arr: npt.NDArray,
    codec: CodecSpec,
    *,
    study_uid: str,
    series_uid: str,
    instance_number: int,
) -> tuple[bytes, int]:
    """One slice -> (complete DICOM file, encapsulated pixel data size)."""
    ds = build_slice_dataset(
        *arr.shape,
        arr.dtype,
        study_uid=study_uid,
        series_uid=series_uid,
        instance_number=instance_number,
    )
    ds.compress(
        UID(codec["transfer_syntax_uid"]),
        arr,
        encoding_plugin=codec["encoding_plugin"],
        **codec["encoder_kwargs"],
    )

    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)

    return buffer.getvalue(), len(ds.PixelData)


def decode_slice(raw: bytes, decoding_plugin: str) -> npt.NDArray:
    return pixel_array(io.BytesIO(raw), decoding_plugin=decoding_plugin)


# Worker side
#
# Module globals, set once per worker by `_init_worker`: the shared volumes are
# attached once rather than per task.

_worker_shms: list[SharedMemory] = []
_worker_reference: npt.NDArray | None = None
_worker_decoded: npt.NDArray | None = None
_worker_barrier: Any = None


def _cpu_times() -> tuple[float, float]:
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return usage.ru_utime, usage.ru_stime


def _init_worker(
    reference_name: str,
    decoded_name: str,
    shape: tuple[int, ...],
    dtype: str,
    barrier: Any,
    warm_up_codecs: Sequence[CodecSpec],
) -> None:
    global _worker_reference, _worker_decoded, _worker_barrier

    # track=False: the parent owns these and unlinks them. Tracking them here
    # too would have the resource tracker unlink them when a worker exits.
    for name in (reference_name, decoded_name):
        _worker_shms.append(SharedMemory(name=name, track=False))

    _worker_reference = np.ndarray(shape, dtype=dtype, buffer=_worker_shms[0].buf)
    _worker_decoded = np.ndarray(shape, dtype=dtype, buffer=_worker_shms[1].buf)
    _worker_barrier = barrier

    # pydicom imports its plugins on first use, so the first task would
    # otherwise pay for the imports inside a timed region.
    warm_up = np.arange(64 * 64, dtype=dtype).reshape(64, 64)
    for codec in warm_up_codecs:
        raw, _ = encode_slice(
            warm_up, codec, study_uid="1.2", series_uid="1.2.3", instance_number=1
        )
        decode_slice(raw, codec["decoding_plugin"])


def _wait_for_all_workers(timeout: float) -> int:
    _worker_barrier.wait(timeout)

    return os.getpid()


def _encode_task(
    z_start: int,
    z_stop: int,
    codec: CodecSpec,
    study_uid: str,
    series_uid: str,
) -> tuple[list[tuple[bytes, int]], float, float]:
    assert _worker_reference is not None
    user_start, system_start = _cpu_times()

    encoded = [
        encode_slice(
            _worker_reference[z],
            codec,
            study_uid=study_uid,
            series_uid=series_uid,
            instance_number=z + 1,
        )
        for z in range(z_start, z_stop)
    ]

    user_end, system_end = _cpu_times()

    return encoded, user_end - user_start, system_end - system_start


def _decode_task(
    z_start: int,
    raws: list[bytes],
    decoding_plugin: str,
) -> tuple[float, float]:
    assert _worker_decoded is not None
    user_start, system_start = _cpu_times()

    for z, raw in enumerate(raws, start=z_start):
        decoded = decode_slice(raw, decoding_plugin)

        if decoded.shape != _worker_decoded.shape[1:]:
            raise ValueError(
                f"Slice {z} decoded to {decoded.shape}, "
                f"expected {_worker_decoded.shape[1:]}"
            )

        _worker_decoded[z] = decoded

    user_end, system_end = _cpu_times()

    return user_end - user_start, system_end - system_start


# Parent side


@contextmanager
def _main_script_hidden() -> Iterator[None]:
    """
    Stop spawned workers from re-running the script that started them.

    A spawn child imports the parent's `__main__` from its `__file__` before it
    unpickles anything. The test notebooks run as plain `python script.py` with
    no `if __name__ == "__main__"` guard, so each worker would rerun the whole
    test. The task functions live in this module and do not need the parent's
    `__main__`, so hiding `__file__` while the workers start is enough. Under
    Jupyter `__main__` has no `__file__` and this does nothing.
    """
    main = sys.modules["__main__"]
    main_file = main.__dict__.pop("__file__", None)

    try:
        yield
    finally:
        if main_file is not None:
            main.__file__ = main_file


def _release_shared_memory(shms: list[SharedMemory]) -> None:
    for shm in shms:
        shm.unlink()

        # Fails while a numpy view of the buffer is still alive somewhere; the
        # segment is already unlinked, so it goes away when that view does.
        try:
            shm.close()
        except BufferError:
            pass


class SliceStackPool:
    """
    Worker processes that encode and decode the z slices of one volume.

    `reference` and `decoded` are numpy views of shared memory: fill
    `reference` once, and each `decode` call overwrites `decoded`. All workers
    are started, and have imported their codecs, before the constructor
    returns, so neither process startup nor plugin imports land inside a timed
    `encode`/`decode`.
    """

    def __init__(
        self,
        shape: tuple[int, int, int],
        dtype: npt.DTypeLike,
        *,
        n_workers: int,
        batch_size: int,
        warm_up_codecs: Sequence[CodecSpec],
        startup_timeout: float = 600.0,
    ) -> None:
        self.shape = shape
        self.dtype = np.dtype(dtype)
        self.n_workers = n_workers
        self.batch_size = batch_size

        nbytes = prod(shape) * self.dtype.itemsize
        self._shms = [SharedMemory(create=True, size=nbytes) for _ in range(2)]
        self._finalizer = weakref.finalize(self, _release_shared_memory, self._shms)

        self.reference = np.ndarray(shape, dtype=self.dtype, buffer=self._shms[0].buf)
        self.decoded = np.ndarray(shape, dtype=self.dtype, buffer=self._shms[1].buf)

        context = get_context("spawn")
        barrier = context.Barrier(n_workers)

        self._executor = ProcessPoolExecutor(
            max_workers=n_workers,
            mp_context=context,
            initializer=_init_worker,
            initargs=(
                self._shms[0].name,
                self._shms[1].name,
                shape,
                self.dtype.str,
                barrier,
                list(warm_up_codecs),
            ),
        )

        # The executor starts workers on demand. Tasks that block until all
        # n_workers have arrived force every one of them to start now.
        with _main_script_hidden():
            futures = [
                self._executor.submit(_wait_for_all_workers, startup_timeout)
                for _ in range(n_workers)
            ]
            pids = {future.result() for future in futures}

        assert len(pids) == n_workers, f"Expected {n_workers} workers, got {pids}"

    def _batches(self) -> Iterator[tuple[int, int]]:
        for z_start in range(0, self.shape[0], self.batch_size):
            yield z_start, min(z_start + self.batch_size, self.shape[0])

    def encode(
        self, codec: CodecSpec, *, study_uid: str, series_uid: str
    ) -> tuple[list[bytes], list[int], float, float]:
        """
        Every slice of `reference` -> (files, pixel data sizes, user s, system s).

        CPU times are the workers' only; the caller adds its own process's.
        """
        futures = [
            self._executor.submit(
                _encode_task, z_start, z_stop, codec, study_uid, series_uid
            )
            for z_start, z_stop in self._batches()
        ]

        files: list[bytes] = []
        pixel_data_sizes: list[int] = []
        user = system = 0.0

        # In submission order, so files[z] is slice z.
        for future in futures:
            encoded, task_user, task_system = future.result()
            files.extend(raw for raw, _ in encoded)
            pixel_data_sizes.extend(size for _, size in encoded)
            user += task_user
            system += task_system

        return files, pixel_data_sizes, user, system

    def decode(
        self, files: Sequence[bytes], decoding_plugin: str
    ) -> tuple[float, float]:
        """Decode `files` into `decoded` -> (user s, system s) of the workers."""
        if len(files) != self.shape[0]:
            raise ValueError(f"Expected {self.shape[0]} files, got {len(files)}")

        futures = [
            self._executor.submit(
                _decode_task, z_start, list(files[z_start:z_stop]), decoding_plugin
            )
            for z_start, z_stop in self._batches()
        ]

        user = system = 0.0
        for future in futures:
            task_user, task_system = future.result()
            user += task_user
            system += task_system

        return user, system

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        del self.reference, self.decoded
        self._finalizer()

    def __enter__(self) -> "SliceStackPool":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
