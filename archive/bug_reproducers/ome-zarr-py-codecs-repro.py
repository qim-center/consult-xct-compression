import ome_zarr.writer
import imagecodecs.zarr
import zarr
import numpy as np
import shutil

# Register this codec
imagecodecs.zarr.register_codecs(verbose=True)

# Set up some test data
arr_np = np.random.randint(0, 256, size=(1000, 1000, 1000), dtype=np.uint8)

# Test that it works with regular zarr
store = zarr.storage.MemoryStore()
z = zarr.create_array(
    store=store,
    shape=arr_np.shape,
    chunks=(1, 100, 100),
    dtype=arr_np.dtype,
    serializer=imagecodecs.zarr.Jpegxl(
        effort=5,
        distance=0.0,
        lossless=True,
        level=5,
    ),
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
        "chunks": (1, 1000, 1000),
        "serializer": imagecodecs.zarr.Jpegxl(
            effort=5,
            distance=0.0,
            lossless=True,
            level=5,
        )
    },
)
print("OME-Zarr success!")