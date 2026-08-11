import numpy as np
from bidict import bidict

from comptest import imagemagick, libtiff, tifffile
from comptest.types import (
    DTYPE_ANY,
    DTYPE_BOOL,
    DTYPE_FLOAT,
    DTYPE_UINT8,
    DTYPE_UINT8_UINT16,
    DTYPE_UINT32,
    FileStackCompressionConfig,
)


def _lt_comp(*args: str):
    return (libtiff.compress_bulk, args, {})


def _im_comp(*args: str):
    return (imagemagick.compress_bulk, args, {})


def _tf_comp(compression: str, **kwargs):
    return (tifffile.compress_bulk, (compression,), kwargs)


_C = FileStackCompressionConfig

_BC = {"paradigm": "file_stack"}
_BC_LIBTIFF = _BC | {
    "implementation": "libtiff/tiffcp",
    "decompressor": (libtiff.decompress_bulk, (), {}),
    "comparer": (libtiff.compare_bulk, ("-t",), {}),
}
_BC_IMAGEMAGICK = _BC | {
    "implementation": "imagemagick",
    "decompressor": (imagemagick.decompress_bulk, (), {}),
    "comparer": (imagemagick.compare_bulk, (), {}),
}
_BC_TIFFFILE = _BC | {
    "implementation": "tifffile",
    "decompressor": (tifffile.decompress_bulk, (), {}),
    "comparer": (tifffile.compare_bulk, (), {}),
}
_BC_LOSSLESS_LIBTIFF = _BC_LIBTIFF | {"lossless": True}
_BC_LOSSLESS_IMAGEMAGICK = _BC_IMAGEMAGICK | {"lossless": True}
_BC_LOSSLESS_TIFFFILE = _BC_TIFFFILE | {"lossless": True}

_PREDICTORS = {1: "none", 2: "horizontal", 3: "float"}
_JPEG_1_QUALITIES = [25, 50, 75, 90, 100]
_JPEG_XR_QUALITIES = [25, 50, 75, 90, 100]
_JPEG2000_QUALITIES = [25, 50, 75, 90, 100]

# ABCDEFGHI = 9 levels + 1 for None
__EFFORTS_9 = bidict(
    {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8, "I": 9}
)
__EFFORTS_12 = bidict(
    {"A": 1, "B": 2, "C": 4, "D": 5, "E": 7, "F": 8, "G": 9, "H": 11, "I": 12}
)
__EFFORTS_22 = bidict(
    {"A": 1, "B": 4, "C": 6, "D": 9, "E": 12, "F": 14, "G": 17, "H": 19, "I": 22}
)
# DEFLATE/zip: 1-12 inclusive
_EFFORTS_DEFLATE = __EFFORTS_12.copy()
_EFFORTS_DEFLATE_SELECT = [1, 2, 4, 5, 7, 9, 12]
efforts_deflate = {
    num: _EFFORTS_DEFLATE.inverse[num] for num in _EFFORTS_DEFLATE_SELECT
}
# LZMA: 1-9 inclusive, note: 9 quite slow, ≈ 1500s
_EFFORTS_LZMA = __EFFORTS_9.copy()
_EFFORTS_LZMA_SELECT = [1, 2, 3, 4, 5, 7]
efforts_lzma = {num: _EFFORTS_LZMA.inverse[num] for num in _EFFORTS_LZMA_SELECT}
# ZStd: 1-22 inclusive, note: 22 quite slow, ≈ 1500s, 19 much faster
_EFFORTS_ZSTD = __EFFORTS_22.copy()
_EFFORTS_ZSTD_SELECT = [1, 4, 6, 9, 12, 14, 17, 19]
efforts_zstd = {num: _EFFORTS_ZSTD.inverse[num] for num in _EFFORTS_ZSTD_SELECT}
# PNG: 1-9 inclusive
_EFFORTS_PNG = __EFFORTS_9.copy()
_EFFORTS_PNG_SELECT = [1, 2, 3, 4, 5, 6, 7, 9]
efforts_png = {num: _EFFORTS_PNG.inverse[num] for num in _EFFORTS_PNG_SELECT}
# JPEGXL: 1-9 inclusive, note: 9 quite slow, ≈ 20000s
_JPEGXL_EFFORTS = __EFFORTS_9.copy()
_JPEGXL_EFFORTS_SELECT = [1, 2, 3, 4, 5, 6, 7]
efforts_jpegxl = {num: _JPEGXL_EFFORTS.inverse[num] for num in _JPEGXL_EFFORTS_SELECT}
# LERC: Depends on subcodec used
_LERC_SUBCODECS = {
    0: "none",
    1: "deflate",
    2: "zstd",
}
_LERC_EFFORTS_SUBCODEC_NONE = bidict({None: None})
_LERC_EFFORTS_SUBCODEC_DEFLATE = __EFFORTS_12.copy()
_LERC_EFFORTS_SUBCODEC_ZSTD = __EFFORTS_22.copy()
_LERC_EFFORTS_SUBCODEC_NONE_SELECT = [None]
_LERC_EFFORTS_SUBCODEC_DEFLATE_SELECT = _EFFORTS_DEFLATE_SELECT.copy()
_LERC_EFFORTS_SUBCODEC_ZSTD_SELECT = _EFFORTS_ZSTD_SELECT.copy()
efforts_lerc = {
    0: {
        num: _LERC_EFFORTS_SUBCODEC_NONE.inverse[num]
        for num in _LERC_EFFORTS_SUBCODEC_NONE_SELECT
    },
    1: {
        num: _LERC_EFFORTS_SUBCODEC_DEFLATE.inverse[num]
        for num in _LERC_EFFORTS_SUBCODEC_DEFLATE_SELECT
    },
    2: {
        num: _LERC_EFFORTS_SUBCODEC_ZSTD.inverse[num]
        for num in _LERC_EFFORTS_SUBCODEC_ZSTD_SELECT
    },
}

BASELINE_CONFIGS = [
    _C(
        name="libtiff_baseline",
        series="tiff-baseline",
        allowed_dtypes=DTYPE_ANY,
        compressor=_lt_comp("-c", "none"),
        **_BC_LOSSLESS_LIBTIFF,
    ),
    _C(
        name="imagemagick_baseline",
        series="tiff-baseline",
        allowed_dtypes=DTYPE_ANY,
        compressor=_im_comp("-compress", "None"),
        **_BC_LOSSLESS_IMAGEMAGICK,
    ),
    _C(
        name="tifffile_baseline",
        series="tiff-baseline",
        allowed_dtypes=DTYPE_ANY,
        compressor=(tifffile.compress_bulk, (), {}),
        **_BC_LOSSLESS_TIFFFILE,
    ),
]

# --- LZW ---
LIBTIFF_LZW_CONFIGS = [
    _C(
        name=f"libtiff_lzw_pred{pred_idx}",
        series="tiff-lzw",
        differencing=pred_name,
        predictor=pred_idx,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_lt_comp("-c", f"lzw:{pred_idx}"),
        **_BC_LOSSLESS_LIBTIFF,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
]
IMAGEMAGICK_LZW_CONFIGS = [
    _C(
        name=f"imagemagick_lzw_pred{pred_idx}",
        series="tiff-lzw",
        differencing=pred_name,
        predictor=pred_idx,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_im_comp(
            "-compress", "LZW", "-define", f"tiff:predictor={pred_idx}"
        ),
        **_BC_LOSSLESS_IMAGEMAGICK,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
]
TIFFFILE_LZW_CONFIGS = [
    _C(
        name=f"tifffile_lzw_pred{pred_idx}",
        series="tiff-lzw",
        differencing=pred_name,
        predictor=pred_idx,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=(tifffile.compress_bulk, ("lzw",), {"predictor": pred_idx}),
        **_BC_LOSSLESS_TIFFFILE,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
]
LZW_CONFIGS = LIBTIFF_LZW_CONFIGS + IMAGEMAGICK_LZW_CONFIGS + TIFFFILE_LZW_CONFIGS

# --- DEFLATE ---
LIBTIFF_DEFLATE_CONFIGS = [
    _C(
        name=f"libtiff_deflate_pred{pred_idx}_s{subcodec_idx}_p{effort}",
        series="tiff-deflate",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        subcodec=subcodec_name,
        subcodec_index=subcodec_idx,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_lt_comp("-c", f"zip:{pred_idx}:s{subcodec_idx}:p{effort}"),
        **_BC_LOSSLESS_LIBTIFF,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_deflate.items()
    for subcodec_idx, subcodec_name in {0: "zlib", 1: "libdeflate"}.items()
]

IMAGEMAGICK_DEFLATE_CONFIGS = [
    _C(
        name=f"imagemagick_deflate_pred{pred_idx}_p{effort}",
        series="tiff-deflate",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        subcodec=None,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_im_comp(
            "-compress",
            "Zip",
            "-define",
            f"tiff:predictor={pred_idx}",
            "-quality",
            f"{effort * 10}",
        ),
        **_BC_LOSSLESS_IMAGEMAGICK,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_deflate.items()
    # Note: No subcodec available in ImageMagick, so no s=0/1 loop here
]

TIFFFILE_DEFLATE_CONFIGS = [
    _C(
        name=f"tifffile_deflate_pred{pred_idx}_p{effort}",
        series="tiff-deflate",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        subcodec=None,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=(
            tifffile.compress_bulk,
            ("zlib",),
            {"compressionargs": {"level": effort}, "predictor": pred_idx},
        ),
        **_BC_LOSSLESS_TIFFFILE,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_deflate.items()
]

DEFLATE_CONFIGS = (
    LIBTIFF_DEFLATE_CONFIGS + IMAGEMAGICK_DEFLATE_CONFIGS + TIFFFILE_DEFLATE_CONFIGS
)

# --- LZMA ---
LIBTIFF_LZMA_CONFIGS = [
    _C(
        name=f"libtiff_lzma_pred{pred_idx}_p{effort}",
        series="tiff-lzma",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_lt_comp("-c", f"lzma:{pred_idx}:p{effort}"),
        **_BC_LOSSLESS_LIBTIFF,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_lzma.items()
]
IMAGEMAGICK_LZMA_CONFIGS = [
    _C(
        name=f"imagemagick_lzma_pred{pred_idx}_p{effort}",
        series="tiff-lzma",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_im_comp(
            "-compress",
            "LZMA",
            "-define",
            f"tiff:predictor={pred_idx}",
            "-quality",
            f"{effort * 10}",
        ),
        **_BC_LOSSLESS_IMAGEMAGICK,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_lzma.items()
]
TIFFFILE_LZMA_CONFIGS = [
    _C(
        name=f"tifffile_lzma_pred{pred_idx}_p{effort}",
        series="tiff-lzma",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=(
            tifffile.compress_bulk,
            ("lzma",),
            {"compressionargs": {"level": effort}, "predictor": pred_idx},
        ),
        **_BC_LOSSLESS_TIFFFILE,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_lzma.items()
]
LZMA_CONFIGS = LIBTIFF_LZMA_CONFIGS + IMAGEMAGICK_LZMA_CONFIGS + TIFFFILE_LZMA_CONFIGS

# --- Zstd ---
LIBTIFF_ZSTD_CONFIGS = [
    _C(
        name=f"libtiff_zstd_pred{pred_idx}_p{effort}",
        series="tiff-zstd",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_lt_comp("-c", f"zstd:{pred_idx}:p{effort}"),
        **_BC_LOSSLESS_LIBTIFF,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_zstd.items()
]

IMAGEMAGICK_ZSTD_CONFIGS = [
    _C(
        name=f"imagemagick_zstd_pred{pred_idx}_p{effort}",
        series="tiff-zstd",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=_im_comp(
            "-compress",
            "Zstd",
            "-define",
            f"tiff:predictor={pred_idx}",
            "-quality",
            f"{effort * 5}",  # Roughly!
        ),
        **_BC_LOSSLESS_IMAGEMAGICK,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_zstd.items()
]
TIFFFILE_ZSTD_CONFIGS = [
    _C(
        name=f"tifffile_zstd_pred{pred_idx}_p{effort}",
        series="tiff-zstd",
        differencing=pred_name,
        predictor=pred_idx,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_FLOAT if pred_idx == 3 else DTYPE_ANY,
        compressor=(
            tifffile.compress_bulk,
            ("zstd",),
            {"compressionargs": {"level": effort}, "predictor": pred_idx},
        ),
        **_BC_LOSSLESS_TIFFFILE,
    )
    for pred_idx, pred_name in _PREDICTORS.items()
    for effort, effort_cat in efforts_zstd.items()
]
ZSTD_CONFIGS = LIBTIFF_ZSTD_CONFIGS + IMAGEMAGICK_ZSTD_CONFIGS + TIFFFILE_ZSTD_CONFIGS

# --- LERC ---
_LERC_COMBINATIONS = []
for effort, effort_cat in efforts_lerc.items():
    for s in [0, 1, 2]:
        if s == 1 and effort > 12:
            continue
        _LERC_COMBINATIONS.append(
            {"z": 0, "s": s, "effort": effort, "effort_cat": effort_cat}
        )

LIBTIFF_LERC_CONFIGS = [
    _C(
        name=f"libtiff_lerc_effort_z{z}_s{s}_p{effort}",
        series="tiff-lerc",
        subseries="tiff-lerc-libtiff",
        effort=effort,
        effort_cat=effort_cat,
        subcodec=_LERC_SUBCODECS[s],
        subcodec_index=s,
        z_max_error=z,
        allowed_dtypes=DTYPE_ANY,
        compressor=_lt_comp("-c", f"lerc:{z}:s{s}:p{effort}"),
        **_BC_LOSSLESS_LIBTIFF,
    )
    for s, efforts in efforts_lerc.items()
    for effort, effort_cat in efforts.items()
    for z in [0]
]

# LIBTIFF_LERC_CONFIGS = [
#     _C(
#         name=f"libtiff_lerc_effort_z{c['z']}_s{c['s']}_p{c['effort']}",
#         series="tiff-lerc",
#         subseries="tiff-lerc-libtiff",
#         effort=c["effort"],
#         effort_cat=c["effort_cat"],
#         subcodec=_LIBTIFF_LERC_SUBCODECS[c["s"]],
#         subcodec_index=c["s"],
#         z_max_error=c["z"],
#         allowed_dtypes=DTYPE_ANY,
#         compressor=_lt_comp("-c", f"lerc:{c['z']}:s{c['s']}:p{c['effort']}"),
#         **_BC_LOSSLESS_LIBTIFF,
#     )
#     for c in _LERC_COMBINATIONS
# ]


# ImageMagick does not support passing in LERC parameters it appears
IMAGEMAGICK_LERC_CONFIGS = [
    _C(
        name="imagemagick_lerc_effort_z0",
        series="tiff-lerc",
        z_max_error=0.0,
        allowed_dtypes=DTYPE_ANY,
        compressor=_im_comp(
            "-compress",
            "LERC",
        ),
        **_BC_LOSSLESS_IMAGEMAGICK,
    )
]


def _resolve_tifffile_lerc(z, s, p):
    compressionargs = {"level": z}
    if s != 0:
        compressionargs |= {
            "compression": _LERC_SUBCODECS[s],
            "compressionargs": {"level": p},
        }
    return {"compressionargs": compressionargs}


TIFFFILE_LERC_CONFIGS = [
    _C(
        name=f"tifffile_lerc_effort_z{z}_s{s}_p{effort}",
        series="tiff-lerc",
        subcodec=_LERC_SUBCODECS[s],
        effort=effort,
        effort_cat=effort_cat,
        subcodec_index=s,
        z_max_error=z,
        allowed_dtypes=DTYPE_ANY,
        compressor=(
            tifffile.compress_bulk,
            ("lerc",),
            _resolve_tifffile_lerc(z, s, effort),
        ),
        **_BC_LOSSLESS_TIFFFILE,
    )
    for s, efforts in efforts_lerc.items()
    for effort, effort_cat in efforts.items()
    for z in [0]
]

LERC_LOSSLESS_CONFIGS = (
    LIBTIFF_LERC_CONFIGS + IMAGEMAGICK_LERC_CONFIGS + TIFFFILE_LERC_CONFIGS
)

# --- RLE ---
RLE_CONFIGS = [
    _C(
        name="libtiff_rle",
        series="tiff-rle",
        allowed_dtypes=DTYPE_ANY,
        compressor=_lt_comp("-c", "packbits"),
        **_BC_LOSSLESS_LIBTIFF,
    ),
    _C(
        name="imagemagick_rle",
        series="tiff-rle",
        allowed_dtypes=DTYPE_ANY,
        compressor=_im_comp("-compress", "RLE"),
        **_BC_LOSSLESS_IMAGEMAGICK,
    ),
    _C(
        name="tifffile_rle",
        series="tiff-rle",
        allowed_dtypes=DTYPE_ANY,
        compressor=(tifffile.compress_bulk, ("packbits",), {}),
        **_BC_LOSSLESS_TIFFFILE,
    ),
]


# Codec-specific combinations built from the shared dtype constants.
DTYPE_JPEG2000 = (
    DTYPE_UINT8_UINT16
    | DTYPE_UINT32
    | {
        np.int8,
        np.int16,
        np.int32,
    }
)
DTYPE_JPEGXL = {np.uint8, np.uint16, np.float16, np.float32}
DTYPE_JPEGXR = {np.uint8, np.uint16, np.float16, np.float32}
DTYPE_JPEGXR_LOSSLESS = {np.uint8, np.uint16, np.float16}
DTYPE_LERC = (
    DTYPE_UINT8_UINT16
    | DTYPE_UINT32
    | {np.int8, np.int16, np.int32, np.float32, np.float64}
)
DTYPE_LERC_IMAGEMAGICK = DTYPE_UINT8_UINT16 | {np.float32, np.float64}
DTYPE_SGILOG = {np.float32}


# # --- Lossy LERC ---
# _LERC_LOSSY_TOLERANCES = [0.5, 1.0, 2.0, 4.0, 8.0]
# _LERC_LOSSY_SUBCODECS = [
#     (0, "none", None),
#     (1, "deflate", 6),
#     (2, "zstd", 9),
# ]
# _LERC_LOSSY_COMBINATIONS = [
#     {"z": tolerance, "s": subcodec_index, "effort": effort}
#     for tolerance in _LERC_LOSSY_TOLERANCES
#     for subcodec_index, _, effort in _LERC_LOSSY_SUBCODECS
# ]


# def _lerc_lossy_name(implementation, combination):
#     tolerance = f"{combination['z']:g}".replace(".", "p")
#     effort = "" if combination["p"] is None else f"_p{combination['p']}"
#     return f"{implementation}_lerc_lossy_z{tolerance}_s{combination['s']}{effort}"


# def _resolve_libtiff_lerc(z, s, p):
#     argument = f"lerc:{z:g}"
#     if s != 0:
#         argument += f":s{s}:p{p}"
#     return _lt_comp("-c", argument)


# LIBTIFF_LERC_LOSSY_CONFIGS = [
#     _C(
#         name=_lerc_lossy_name("libtiff", c),
#         series="tiff-lerc",
#         subseries="tiff-lerc-lossy-libtiff",
#         lossless=False,
#         tolerance=c["z"],
#         effort=c["p"],
#         subcodec=_LIBTIFF_LERC_SUBCODECS[c["s"]],
#         subcodec_index=c["s"],
#         allowed_dtypes=DTYPE_LERC,
#         compressor=_resolve_libtiff_lerc(c["z"], c["s"], c["p"]),
#         **_BC_LIBTIFF,
#     )
#     for c in _LERC_LOSSY_COMBINATIONS
# ]

# IMAGEMAGICK_LERC_LOSSY_CONFIGS = [
#     _C(
#         name=_lerc_lossy_name("imagemagick", c),
#         series="tiff-lerc",
#         subseries="tiff-lerc-lossy-imagemagick",
#         lossless=False,
#         tolerance=c["z"],
#         effort=c["p"],
#         subcodec=_LIBTIFF_LERC_SUBCODECS[c["s"]],
#         subcodec_index=c["s"],
#         allowed_dtypes=DTYPE_LERC_IMAGEMAGICK,
#         compressor=_im_comp(
#             *_resolve_imagemagick_lerc(c["z"], c["s"], c["p"]),
#         ),
#         **_BC_IMAGEMAGICK,
#     )
#     for c in _LERC_LOSSY_COMBINATIONS
# ]

# TIFFFILE_LERC_LOSSY_CONFIGS = [
#     _C(
#         name=_lerc_lossy_name("tifffile", c),
#         series="tiff-lerc",
#         subseries="tiff-lerc-lossy-tifffile",
#         lossless=False,
#         tolerance=c["z"],
#         effort=c["p"],
#         subcodec=_LIBTIFF_LERC_SUBCODECS[c["s"]],
#         subcodec_index=c["s"],
#         allowed_dtypes=DTYPE_LERC,
#         compressor=(
#             tifffile.compress_bulk,
#             ("lerc",),
#             _resolve_tifffile_lerc(c["z"], c["s"], c["p"]),
#         ),
#         **_BC_TIFFFILE,
#     )
#     for c in _LERC_LOSSY_COMBINATIONS
# ]

# LERC_LOSSY_CONFIGS = (
#     LIBTIFF_LERC_LOSSY_CONFIGS
#     + IMAGEMAGICK_LERC_LOSSY_CONFIGS
#     + TIFFFILE_LERC_LOSSY_CONFIGS
# )
# LERC_CONFIGS = LERC_LOSSLESS_CONFIGS + LERC_LOSSY_CONFIGS
LERC_CONFIGS = LERC_LOSSLESS_CONFIGS + []

# --- CCITT bilevel encodings (libtiff) ---
LIBTIFF_CCITT_CONFIGS = [
    _C(
        name=f"libtiff_ccitt_{name}",
        series="tiff-ccitt",
        subseries=f"tiff-ccitt-{name}",
        lossless=True,
        allowed_dtypes=DTYPE_BOOL,
        compressor=_lt_comp("-c", argument),
        **_BC_LIBTIFF,
    )
    for name, argument in (
        ("g3_1d", "g3:1d"),
        ("g3_2d", "g3:2d"),
        ("g3_2d_fill", "g3:2d:fill"),
        ("g4", "g4"),
    )
]


# --- JPEG (libtiff and tifffile/imagecodecs) ---
_JPEG_QUALITIES = [25, 50, 75, 90, 100]

LIBTIFF_JPEG_CONFIGS = [
    _C(
        name=f"libtiff_jpeg_q{quality}",
        series="tiff-jpeg",
        subseries="tiff-jpeg-lossy",
        lossless=False,
        quality=quality,
        allowed_dtypes=DTYPE_UINT8,
        compressor=_lt_comp("-c", f"jpeg:{quality}"),
        **_BC_LIBTIFF,
    )
    for quality in _JPEG_QUALITIES
]

TIFFFILE_JPEG_CONFIGS = [
    _C(
        name=f"tifffile_jpeg_q{quality}",
        series="tiff-jpeg",
        subseries="tiff-jpeg-lossy",
        lossless=False,
        quality=quality,
        allowed_dtypes=DTYPE_UINT8,
        compressor=_tf_comp("jpeg", compressionargs={"level": quality}),
        **_BC_TIFFFILE,
    )
    for quality in _JPEG_QUALITIES
]

# imagecodecs exposes JPEG lossless mode and predictors 1 through 7.  This is
# distinct from TIFF's top-level horizontal/floating-point predictor.
TIFFFILE_JPEG_LOSSLESS_CONFIGS = [
    _C(
        name=f"tifffile_jpeg_lossless_pred{predictor}",
        series="tiff-jpeg",
        subseries="tiff-jpeg-lossless",
        lossless=True,
        predictor=predictor,
        allowed_dtypes=(DTYPE_UINT8_UINT16 if predictor <= 4 else DTYPE_UINT8),
        compressor=_tf_comp(
            "jpeg",
            compressionargs={"lossless": True, "predictor": predictor},
        ),
        **_BC_TIFFFILE,
    )
    for predictor in range(1, 8)
]

JPEG_CONFIGS = (
    LIBTIFF_JPEG_CONFIGS + TIFFFILE_JPEG_CONFIGS + TIFFFILE_JPEG_LOSSLESS_CONFIGS
)


# --- JPEG 2000 (tifffile/imagecodecs) ---
TIFFFILE_JPEG2000_LOSSLESS_CONFIGS = [
    _C(
        name="tifffile_jpeg2000_lossless",
        series="tiff-jpeg2000",
        subseries="tiff-jpeg2000-lossless",
        lossless=True,
        allowed_dtypes=DTYPE_JPEG2000,
        compressor=_tf_comp("jpeg2000", compressionargs={"reversible": True}),
        **_BC_TIFFFILE,
    )
]

TIFFFILE_JPEG2000_LOSSY_CONFIGS = [
    _C(
        name=f"tifffile_jpeg2000_q{quality}",
        series="tiff-jpeg2000",
        subseries="tiff-jpeg2000-lossy",
        lossless=False,
        quality=quality,
        allowed_dtypes=DTYPE_JPEG2000,
        compressor=_tf_comp(
            "jpeg2000",
            compressionargs={"level": quality, "reversible": False},
        ),
        **_BC_TIFFFILE,
    )
    for quality in _JPEG2000_QUALITIES
]

TIFFFILE_JPEG2000_CONFIGS = (
    TIFFFILE_JPEG2000_LOSSLESS_CONFIGS + TIFFFILE_JPEG2000_LOSSY_CONFIGS
)


# --- JPEG XL (tifffile/imagecodecs) ---
_JPEGXL_DISTANCES = [
    0.01,
    0.02,
    0.03,
    0.05,
    0.075,
    0.1,
    0.2,
    0.3,
    0.5,
    0.75,
    1.0,
]
TIFFFILE_JPEGXL_LOSSLESS_CONFIGS = [
    _C(
        name=f"tifffile_jpegxl_lossless_e{effort}",
        series="tiff-jpegxl",
        subseries="tiff-jpegxl-lossless",
        lossless=True,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_JPEGXL,
        compressor=_tf_comp(
            "jpegxl",
            compressionargs={"lossless": True, "effort": effort},
        ),
        **_BC_TIFFFILE,
    )
    for effort, effort_cat in efforts_jpegxl.items()
]

TIFFFILE_JPEGXL_LOSSY_CONFIGS = [
    _C(
        name=f"tifffile_jpegxl_d{distance:g}_e{effort}",
        series="tiff-jpegxl",
        subseries="tiff-jpegxl-lossy",
        lossless=False,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_JPEGXL,
        distance=distance,
        compressor=_tf_comp(
            "jpegxl",
            compressionargs={"distance": distance, "effort": effort},
        ),
        **_BC_TIFFFILE,
    )
    for distance in _JPEGXL_DISTANCES
    for effort, effort_cat in efforts_jpegxl.items()
]

TIFFFILE_JPEGXL_LOSSY_CONFIGS_EFFORT_7_BIG = [
    _C(
        name=f"tifffile_jpegxl_d{distance:g}_e7",
        series="tiff-jpegxl",
        subseries="tiff-jpegxl-lossy",
        lossless=False,
        effort=7,
        effort_cat=efforts_jpegxl[7],
        allowed_dtypes=DTYPE_JPEGXL,
        distance=distance,
        compressor=_tf_comp(
            "jpegxl",
            compressionargs={"distance": distance, "effort": effort},
        ),
        **_BC_TIFFFILE,
    )
    for distance in [
        0.001,
        0.002,
        0.003,
        0.005,
        0.0075,
        0.01,
        0.02,
        0.03,
        0.05,
        0.075,
        0.1,
        0.2,
        0.3,
        0.5,
        0.75,
        1.0,
        2.0,
        3.0,
        5.0,
        7.5,
        10.0,
    ]
]


TIFFFILE_JPEGXL_CONFIGS = (
    TIFFFILE_JPEGXL_LOSSLESS_CONFIGS + TIFFFILE_JPEGXL_LOSSY_CONFIGS
)


# --- JPEG XR (tifffile/imagecodecs) ---
# Level 0 selects lossless coding.  Float32 is excluded from the lossless entry
# because the JPEG XR round trip quantizes it slightly; float16 is exact.
TIFFFILE_JPEGXR_LOSSLESS_CONFIGS = [
    _C(
        name="tifffile_jpegxr_lossless",
        series="tiff-jpegxr",
        subseries="tiff-jpegxr-lossless",
        lossless=True,
        quality=100,
        allowed_dtypes=DTYPE_JPEGXR_LOSSLESS,
        compressor=_tf_comp("jpegxr", compressionargs={"level": 0}),
        **_BC_TIFFFILE,
    )
]

TIFFFILE_JPEGXR_LOSSY_CONFIGS = [
    _C(
        name=f"tifffile_jpegxr_q{quality}",
        series="tiff-jpegxr",
        subseries="tiff-jpegxr-lossy",
        lossless=False,
        quality=quality,
        allowed_dtypes=DTYPE_JPEGXR,
        compressor=_tf_comp("jpegxr", compressionargs={"level": quality / 100}),
        **_BC_TIFFFILE,
    )
    for quality in _JPEG_XR_QUALITIES
]

TIFFFILE_JPEGXR_CONFIGS = (
    TIFFFILE_JPEGXR_LOSSLESS_CONFIGS + TIFFFILE_JPEGXR_LOSSY_CONFIGS
)


# --- PNG-in-TIFF (tifffile/imagecodecs) ---
TIFFFILE_PNG_CONFIGS = [
    _C(
        name=f"tifffile_png_p{effort}",
        series="tiff-png",
        lossless=True,
        effort=effort,
        effort_cat=effort_cat,
        allowed_dtypes=DTYPE_UINT8_UINT16,
        compressor=_tf_comp("png", compressionargs={"level": effort}),
        **_BC_TIFFFILE,
    )
    for effort, effort_cat in efforts_png.items()
]


# --- SGILog (libtiff) ---
# SGILog stores floating-point luminance in a logarithmic integer
# representation.  It is therefore lossy and is only useful here for float32
# input.  Replace the overly broad inherited configs.py definition in CONFIGS.
LIBTIFF_SGILOG_CONFIGS = [
    _C(
        name="libtiff_sgilog",
        series="tiff-sgilog",
        lossless=False,
        allowed_dtypes=DTYPE_SGILOG,
        compressor=_lt_comp("-c", "sgilog"),
        **_BC_LIBTIFF,
    )
]

CONFIGS = (
    []
    + BASELINE_CONFIGS
    + LZW_CONFIGS
    + DEFLATE_CONFIGS
    + LZMA_CONFIGS
    + ZSTD_CONFIGS
    + LIBTIFF_SGILOG_CONFIGS
    + RLE_CONFIGS
    + LERC_CONFIGS
    + LIBTIFF_CCITT_CONFIGS
    + JPEG_CONFIGS
    + TIFFFILE_JPEG2000_CONFIGS
    + TIFFFILE_JPEGXL_CONFIGS
    + TIFFFILE_JPEGXR_CONFIGS
    + TIFFFILE_PNG_CONFIGS
)

CONFIGS_LOSSY = [c for c in CONFIGS if not c.lossless]
CONFIGS_LOSSLESS = [c for c in CONFIGS if c.lossless]

CONFIGS_VARIABILITY = [
    _C(
        name="libtiff_zstd_pred2_p12",
        series="tiff-zstd",
        differencing="horizontal",
        predictor=2,
        effort=12,
        effort_cat=_EFFORTS_ZSTD.inverse[12],
        allowed_dtypes=DTYPE_ANY,
        compressor=_lt_comp("-c", "zstd:2:p12"),
        **_BC_LOSSLESS_LIBTIFF,
    ),
    _C(
        name="imagemagick_zstd_pred2_p12",
        series="tiff-zstd",
        differencing="horizontal",
        predictor=2,
        effort=12,
        effort_cat=_EFFORTS_ZSTD.inverse[12],
        allowed_dtypes=DTYPE_ANY,
        compressor=_im_comp(
            "-compress",
            "Zstd",
            "-define",
            f"tiff:predictor={2}",
            "-quality",
            f"{12 * 5}",  # Roughly!
        ),
        **_BC_LOSSLESS_IMAGEMAGICK,
    ),
    _C(
        name="tifffile_zstd_pred2_p12",
        series="tiff-zstd",
        differencing="horizontal",
        predictor=2,
        effort=12,
        effort_cat=_EFFORTS_ZSTD.inverse[12],
        allowed_dtypes=DTYPE_ANY,
        compressor=(
            tifffile.compress_bulk,
            ("zstd",),
            {"compressionargs": {"level": 12}, "predictor": 2},
        ),
        **_BC_LOSSLESS_TIFFFILE,
    ),
] * 4
