from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import imagecodecs.zarr
import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer
from scientific_pydantic import EllipsisLiteral as EllipsisTypeAdapted
from scientific_pydantic.numpy import DTypeAdapter
from zarr.abc.codec import BaseCodec


def _serialize_type(value: type[Any]) -> str:
    return value.__name__


DType = Annotated[np.dtype, DTypeAdapter()]
T = TypeVar("T")

JSONSerializableType = Annotated[
    type[T], PlainSerializer(_serialize_type, when_used="json-unless-none")
]


_CompressorLike = JSONSerializableType[BaseCodec] | Callable
# (callable, args, kwargs)
_CallableLike = tuple[
    _CompressorLike, tuple[Any, ...], dict[str, Any]
]



class BaseCompressionConfig(BaseModel):
    name: str
    series: str
    subseries: str | None = None

    paradigm: Literal["file_stack", "zarr"]
    lossless: bool

    allowed_dtypes: set[DType]

    ### Groupings
    implementation: Literal["libtiff/tiffcp", "imagemagick", "zarr/imagecodecs", "tifffile"]
    # libtiff has this for some codecs
    differencing: Literal["none", "horizontal", "float"] | None = None
    predictor: int | None = None
    # General effort parameter
    effort: int | None = None
    # General quality parameter, usually 0-100, 100 is lossless
    quality: int | None = None
    # Used for zerror in ZERC for example
    tolerance: float | None = None
    # Subcodec, used by some libtiff, note 'none' and None are not the same!
    subcodec: Literal["none", "deflate", "zstd"] | str | None = None
    subcodec_index: int | None = None


    # Put extra groupings here, but add them as optional if they are reused often
    extra: dict[str, Any] = Field(default_factory=dict)

    def get_pathlike_str(self) -> str:
        """
        Serializes itself into something that can be used as a path-like string on Unix,
        not Windows!
        """
        return self.model_dump_json(indent=None, ensure_ascii=True)


class FileStackCompressionConfig(BaseCompressionConfig):
    compressor: _CallableLike
    decompressor: _CallableLike
    comparer: _CallableLike


class ZarrCompressionConfig(BaseCompressionConfig):
    chunks: tuple[
        int | EllipsisTypeAdapted, ...
    ]  # Change EllipsisTypeAdapted -> typing.EllipsisType when below is fixed:
    # https://github.com/pydantic/pydantic/issues/13467
    # https://github.com/pydantic/pydantic/pull/13484

    filters: _CallableLike | None = None
    serializer: _CallableLike | None = None
    compressors: list[_CallableLike] | None = None

    # Extra fields are assumed to be additional kwargs for zarr
    model_config = ConfigDict(extra="allow")

    def get_zarr_kwargs(self, arr: npt.NDArray) -> dict[str, Any]:
        zarr_kwargs = {}

        # Resolve chunks
        chunks: tuple[int, ...] = tuple(
            arr.shape[i] if c is ... else c for i, c in enumerate(self.chunks)
        )

        # Fix for JPEGXL, see: https://github.com/cgohlke/imagecodecs/issues/145
        if (
            self.serializer is not None
            and self.serializer[0] is imagecodecs.zarr.Jpegxl
            and "planar" in self.serializer[1]
            and self.serializer[1]["planar"]
            and chunks[0] == 1
        ):
            self.serializer[1].pop("planar")

        zarr_kwargs |= {"chunks": chunks}

        # Resolve codecs
        if self.filters is not None:
            zarr_kwargs |= {
                "filters": self.filters[0](**self.filters[1]),
            }
        if self.serializer is not None:
            zarr_kwargs |= {"serializer": self.serializer[0](**self.serializer[1])}
        if self.compressors is not None:
            zarr_kwargs |= {"compressors": [c[0](**c[1]) for c in self.compressors]}

        zarr_kwargs |= self.__pydantic_extra__ or {}

        return zarr_kwargs


class CompressionTest(BaseCompressionConfig):
    id: str

    dataset_name: str
    dataset_path: Path

    start_wall_dt: datetime
    end_wall_dt: datetime
    total_wall_time_seconds: float

    config: FileStackCompressionConfig | ZarrCompressionConfig

    # A baseline to compare against
    # We run a simple test to ensure that compression of a known configuration is roughly the same
    # This is a sanity check to ensure we don't accidentally get affected by hardware changes, etc on the HPC cluster
    baseline_test: CompressionTest | None
    host: str

    compress_wall_time_seconds: float
    compress_user_time_seconds: float
    decompress_wall_time_seconds: float
    decompress_user_time_seconds: float

    uncompressed_size: int
    actual_uncompressed_size: int
    compressed_size: int

    n_elements: int

    compression_wall_rate: float  # In terms of uncompressed data over wall time, bytes/sec
    compression_user_rate: float  # In terms of uncompressed data over user time, bytes/sec
    decompression_wall_rate: float  # In terms of uncompressed data over wall time, bytes/sec
    decompression_user_rate: float  # In terms of uncompressed data over user time, bytes/sec

    bitrate_uncompressed: float
    bitrate_compressed: float

    compression_ratio: float
    space_saving: float

    was_actually_lossless: bool | None = None

    runner_extra: dict[str, Any] = Field(default_factory=dict)

    # Needs to be _NDArraya since zarr.info_complete() can return _fill_value=numpy scalar
    # array_info: dict[str, Any]  # TODO MOVE TO EXTRA
