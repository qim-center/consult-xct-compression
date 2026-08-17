from pathlib import Path
import numpy as np

import pillow_jxl
from PIL import Image

input_path = Path("output2.jxl")
assert input_path.exists()
img = Image.open(input_path)

arr = np.asarray(img)
print(arr.dtype)
print(arr.min(), arr.max())