import importlib.metadata
import shutil
import sys

import numpy as np
import ome_zarr.writer
import zarr
import zarr.storage

print("Python version:", sys.version)
print("OME-Zarr version:", importlib.metadata.version("ome-zarr"))
print("Zarr version:", importlib.metadata.version("zarr"))

# Set up some test data
arr_np = np.random.randint(0, 256, size=(100, 100, 100), dtype=np.uint8)

# Test that it works with regular zarr
store = zarr.storage.MemoryStore()
z = zarr.create_array(
    store=store,
    shape=arr_np.shape,
    chunks=(1, 100, 100),
    shards="auto",
    dtype=arr_np.dtype,
    config={
        "array.target_shard_size_bytes": 1000  # 1 kB
    },
)
z[:] = arr_np
print("Zarr success!")

# Test ome-zarr-py:
out = "test_output.ome.zarr"
shutil.rmtree(out, ignore_errors=True)
ome_zarr.writer.write_image(
    image=arr_np,
    group="test_output.ome.zarr",
    axes="zyx",
    storage_options={
        "chunks": (1, 100, 100),
        "shards": "auto",
        "config": {
            "array.target_shard_size_bytes": 1000  # 1 kB
        },
    },
)
print("OME-Zarr success!")
