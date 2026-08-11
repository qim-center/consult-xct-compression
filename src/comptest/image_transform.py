from typing import Self

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel


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