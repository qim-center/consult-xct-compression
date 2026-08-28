from __future__ import annotations
from cil.framework.image_geometry import ImageGeometry

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self, TypeVar

import imagecodecs.zarr
import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer
from scientific_pydantic import EllipsisLiteral as EllipsisTypeAdapted
from scientific_pydantic.numpy import DTypeAdapter
from skimage.metrics import structural_similarity
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
_CallableLike = tuple[_CompressorLike, tuple[Any, ...], dict[str, Any]]

DTYPE_BOOL = {np.bool_}
DTYPE_UINT8 = {np.uint8}
DTYPE_UINT16 = {np.uint16}
DTYPE_UINT8_UINT16 = {np.uint8, np.uint16}
DTYPE_UINT32 = {np.uint32}
DTYPE_UINT = {
    np.bool_,
    np.uint8,
    np.uint16,
    np.uint32,
    np.uint64,
}
DTYPE_SINT = {
    np.int8,
    np.int16,
    np.int32,
    np.int64,
}
DTYPE_INT = DTYPE_UINT.union(DTYPE_SINT)
DTYPE_FLOAT = {
    np.float16,
    np.float32,
    np.float64,
    np.float128,
}
DTYPE_COMPLEX = {
    np.complex64,
    np.complex128,
    np.complex256,
}
DTYPE_ANY = DTYPE_INT.union(DTYPE_FLOAT).union(DTYPE_COMPLEX)


class BaseCompressionConfig(BaseModel):
    name: str
    series: str
    subseries: str | None = None

    paradigm: Literal["file_stack", "zarr"]
    lossless: bool

    allowed_dtypes: set[DType]

    ### Groupings
    implementation: Literal[
        "libtiff/tiffcp", "imagemagick", "zarr/imagecodecs", "tifffile"
    ]
    # libtiff has this for some codecs
    differencing: Literal["none", "horizontal", "float"] | None = None
    predictor: int | None = None
    # General effort parameter
    effort_cat: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I"] | None = None
    effort: int | None = None
    # General quality parameter, usually 0-100, 100 is lossless
    quality: int | None = None
    # Used for zerror in ZERC for example
    tolerance: float | None = None
    # Subcodec, used by some libtiff, note 'none' and None are not the same!
    subcodec: Literal["none", "deflate", "zstd"] | str | None = None
    subcodec_index: int | None = None
    # Used to JPEGXL
    distance: float | None = None

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


class StructuralSimilarityIndexMetrics(BaseModel):
    mean: float
    min: float
    max: float
    std: float
    median: float
    percentile_25th: float
    percentile_75th: float
    histogram_values: list[float]
    histogram_bin_edges: list[float]

    @staticmethod
    def get_ssim(
        reference: npt.NDArray,
        distorted: npt.NDArray,
        *,
        data_range: float | None,
        gaussian_weights: bool = True,
        sigma: float = 1.5,
        use_sample_covariance: bool = False,
        win_size: int | None = None,
        gradient: bool = False,
        channel_axis: int | None = None,
        **kwargs: Any
    ) -> npt.NDArray:
        """
        Follows Wang et al. (2004) if default parameters are left.
        """
        _ssim_mean, ssim_full_part = structural_similarity(
            reference,
            distorted,
            full=True,
            data_range=data_range,
            gaussian_weights=gaussian_weights,
            sigma=sigma,
            use_sample_covariance=use_sample_covariance,
            win_size=win_size,
            gradient=gradient,
            channel_axis=channel_axis,
            **kwargs
        )

        return ssim_full_part


    @classmethod
    def from_ndarray(cls, arr: npt.NDArray) -> Self:
        hist_range = (0.0, 1.0)
        edges = np.linspace(*hist_range, num=101)
        hist, bin_edges = np.histogram(arr, bins=edges, range=hist_range, density=True)

        return cls(
            mean=float(np.mean(arr)),
            min=float(np.min(arr)),
            max=float(np.max(arr)),
            std=float(np.std(arr)),
            median=float(np.median(arr)),
            percentile_25th=float(np.percentile(arr, 25)),
            percentile_75th=float(np.percentile(arr, 75)),
            histogram_values=list(hist),
            histogram_bin_edges=list(bin_edges),
        )


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
    compress_system_time_seconds: float
    decompress_wall_time_seconds: float
    decompress_user_time_seconds: float
    decompress_system_time_seconds: float

    uncompressed_size: int
    actual_uncompressed_size: int
    compressed_size: int

    n_elements: int

    compression_wall_rate: (
        float  # In terms of uncompressed data over wall time, bytes/sec
    )
    compression_user_rate: (
        float  # In terms of uncompressed data over user time, bytes/sec
    )
    decompression_wall_rate: (
        float  # In terms of uncompressed data over wall time, bytes/sec
    )
    decompression_user_rate: (
        float  # In terms of uncompressed data over user time, bytes/sec
    )

    bitrate_uncompressed: float
    bitrate_compressed: float

    compression_ratio: float
    space_saving: float

    # Image quality metrics
    was_actually_lossless: bool
    ssim: StructuralSimilarityIndexMetrics | None

    # Useful for computing summary statistics later, all in bytes
    images_input_sizes: dict[str, int] | None
    images_uncompressed_sizes: dict[str, int] | None
    images_compressed_sizes: dict[str, int] | None

    runner_extra: dict[str, Any] = Field(default_factory=dict)

    # Needs to be _NDArraya since zarr.info_complete() can return _fill_value=numpy scalar
    # array_info: dict[str, Any]  # TODO MOVE TO EXTRA

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dataset_name": self.dataset_name,
            "lossless": self.lossless,
            "total_wall_time_seconds": self.total_wall_time_seconds,
            "compress_wall_time_seconds": self.compress_wall_time_seconds,
            "compress_user_time_seconds": self.compress_user_time_seconds,
            "compress_system_time_seconds": self.compress_system_time_seconds,
            "decompress_wall_time_seconds": self.decompress_wall_time_seconds,
            "decompress_user_time_seconds": self.decompress_user_time_seconds,
            "decompress_system_time_seconds": self.decompress_system_time_seconds,
            "uncompressed_size": self.uncompressed_size,
            "actual_uncompressed_size": self.actual_uncompressed_size,
            "compressed_size": self.compressed_size,
            "compression_wall_rate": self.compression_wall_rate,
            "compression_user_rate": self.compression_user_rate,
            "decompression_wall_rate": self.decompression_wall_rate,
            "decompression_user_rate": self.decompression_user_rate,
            "bitrate_uncompressed": self.bitrate_uncompressed,
            "bitrate_compressed": self.bitrate_compressed,
            "compression_ratio": self.compression_ratio,
            "space_saving": self.space_saving,
        }


class ReconstructionGeometry(BaseModel):
    voxel_num_x: int
    voxel_num_y: int
    voxel_num_z: int
    voxel_size_x_m: float
    voxel_size_y_m: float
    voxel_size_z_m: float
    center_x_m: float
    center_y_m: float
    center_z_m: float

    @classmethod
    def from_cil_image_geometry(
        cls, ig: ImageGeometry, physical_unit_scale_to_m: float = 1.0
    ) -> Self:
        return cls(
            voxel_num_x=ig.voxel_num_x,
            voxel_num_y=ig.voxel_num_y,
            voxel_num_z=ig.voxel_num_z,
            voxel_size_x_m=ig.voxel_size_x * physical_unit_scale_to_m,
            voxel_size_y_m=ig.voxel_size_y * physical_unit_scale_to_m,
            voxel_size_z_m=ig.voxel_size_z * physical_unit_scale_to_m,
            center_x_m=ig.center_x * physical_unit_scale_to_m,
            center_y_m=ig.center_y * physical_unit_scale_to_m,
            center_z_m=ig.center_z * physical_unit_scale_to_m,
        )

    @classmethod
    def load_json(cls, path: str | Path) -> Self:
        path = Path(path)
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save_as_json(self, path: str | Path) -> None:
        path = Path(path)
        path.write_text(self.model_dump_json(indent=4, ensure_ascii=True), encoding="utf-8")
