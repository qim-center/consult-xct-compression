from typing import Self

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, field_validator


class DataTransform(BaseModel):
    # transformed = (data - offset) * scale
    offset: float
    scale: float

    @classmethod
    def infer(
        cls,
        data: npt.NDArray,
        target_range: tuple[float, float],
    ) -> Self:
        """
        Infers the linear transformation parameters (offset and scale) that map
        the input data to the specified target range."""
        data_min = float(np.min(data))
        data_max = float(np.max(data))
        target_min, target_max = target_range

        if data_max == data_min:
            raise ValueError("Cannot infer a linear transform from constant data.")
        if target_max <= target_min:
            raise ValueError("target_range must satisfy min < max.")

        scale = (target_max - target_min) / (data_max - data_min)
        offset = data_min - target_min / scale

        return cls(offset=offset, scale=scale)

    def apply(self, data: npt.NDArray) -> npt.NDArray:
        return (data - self.offset) * self.scale

    def inverse(self, data: npt.NDArray) -> npt.NDArray:
        return (data / self.scale) + self.offset

class DtypeDataTransform(DataTransform):
    # transformed = cast((data - offset) * scale, target_dtype), rounding and clipping
    # to the representable range when target_dtype is an integer type.
    target_dtype: str

    @field_validator("target_dtype", mode="before")
    @classmethod
    def _normalise_dtype(cls, value: npt.DTypeLike) -> str:
        return np.dtype(value).name

    @classmethod
    def infer(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        data: npt.NDArray,
        target_dtype: npt.DTypeLike,
        target_range: tuple[float, float] | None = None,
    ) -> Self:
        """
        Infers the linear transformation that maps the input data to target_range
        in target_dtype. For integer dtypes target_range defaults to the full
        representable range; for float dtypes it must be given."""
        dtype = np.dtype(target_dtype)

        if target_range is None:
            if not np.issubdtype(dtype, np.integer):
                raise ValueError("target_range is required for non-integer dtypes.")
            info = np.iinfo(dtype)
            target_range = (float(info.min), float(info.max))

        base = DataTransform.infer(data, target_range)
        return cls(offset=base.offset, scale=base.scale, target_dtype=dtype)

    def apply(self, data: npt.NDArray) -> npt.NDArray:
        transformed = super().apply(data)
        dtype = np.dtype(self.target_dtype)

        if np.issubdtype(dtype, np.integer):
            # Clip to ensure no funny business with floating point rounding errors
            info = np.iinfo(dtype)
            transformed = np.clip(np.rint(transformed), info.min, info.max)

        return transformed.astype(dtype)
