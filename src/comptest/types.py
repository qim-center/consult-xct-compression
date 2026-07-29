from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypeVar

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
    name: str | None = None
    series: str
    vary_var: str | None = None
    vary_value: str | int | None = None
    groupings: dict[str, Any] = Field(default_factory=dict)
    is_lossless: bool

    allowed_dtypes: set[DType]

    extra: dict[str, Any] = Field(default_factory=dict)

    def get_pathlike_str(self) -> str:
        """
        Serializes itself into something that can be used as a path-like string on Unix,
        not Windows!
        """
        return self.model_dump_json(indent=None, ensure_ascii=True)

    def get_name(self) -> str:
        if self.name is not None:
            return self.name
        else:
            return self.get_pathlike_str()

class FileStackCompressionConfig(BaseCompressionConfig):
    compressor: _CallableLike


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


class CompressionTest(BaseModel):
    name: str
    id: str
    series: str
    vary_var: str | None
    vary_value: str | int | None

    # Used to define other groupings in a series, i.e. distinguishing between compression executable or something like that.
    # These are essentially factors that are not general enough to be in the main model
    groupings: dict[str, Any] = Field(default_factory=dict)

    dataset_name: str
    dataset_path: Path

    start_dt: datetime
    end_dt: datetime
    total_time_seconds: float

    config: BaseCompressionConfig | ZarrCompressionConfig

    # A baseline to compare against
    # We run a simple test to ensure that compression of a known configuration is roughly the same
    # This is a sanity check to ensure we don't accidentally get affected by hardware changes, etc on the HPC cluster
    baseline_test: CompressionTest | None
    host: str

    compress_time_seconds: float

    nbytes: int
    nbytes_stored: int

    npixels: int

    bitrate: float
    bitrate_compressed: float

    compression_ratio: float
    space_saving: float

    lossless: bool
    # Needs to be _NDArraya since zarr.info_complete() can return _fill_value=numpy scalar
    # array_info: dict[str, Any]  # TODO MOVE TO EXTRA
    extra: dict[str, Any] = Field(default_factory=dict)
