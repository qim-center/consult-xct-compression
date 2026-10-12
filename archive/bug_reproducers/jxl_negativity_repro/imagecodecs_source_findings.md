# Imagecodecs JPEG XL negative-float findings

## Scope

This investigation used the project reproducer with:

- tifffile 2026.7.14
- imagecodecs 2026.6.26
- libjxl and `cjxl` 0.12.0
- grayscale float32 input spanning approximately `[-0.03984, 0.13883]`
- JPEG XL `distance=0.01` and `effort=7`

The installed imagecodecs release was compared with current imagecodecs
`master`; the relevant JPEG XL encoder source was unchanged.

## Conclusion

The observed difference between imagecodecs/tifffile and `cjxl` is caused by
different transfer-function defaults:

- imagecodecs interprets float arrays as **linear sRGB**;
- the `cjxl` PFM loader interprets PFM samples as **nonlinear sRGB**.

Sufficiently negative linear-light samples are clipped during libjxl's default
lossy VarDCT linear-to-XYB conversion. Supplying the same transfer function
makes imagecodecs and `cjxl` exhibit the same behavior.

This is not inherent to lossy JPEG XL. Libjxl can perform lossy encoding in the
original profile with perceptual heuristics disabled, which bypasses XYB and
retains the negative tail. The `cjxl --disable_perceptual_optimizations`
option selects that path. Imagecodecs binds the underlying frame option but
does not expose it through `jpegxl_encode`.

Therefore, this is not a tifffile container bug. It is a combination of:

1. an imagecodecs default that selects linear-light input plus perceptual XYB;
2. missing validation for imagecodecs' documented float range;
3. a missing imagecodecs option for libjxl's non-perceptual encoding path; and
4. libjxl's default XYB path clipping sufficiently negative linear-light
   samples even though its public API permits finite float samples outside the
   nominal range.

## Controlled results

The direct codec experiment used the same source array and encoder settings:

| Encoder and declared transfer | Minimum after decode | Pixels below `-0.004` | Mean absolute error | Maximum error | Encoded bytes |
|---|---:|---:|---:|---:|---:|
| imagecodecs default | -0.00379309 | 0 | 0.00006751 | 0.03604802 | 537,202 |
| imagecodecs linear | -0.00379309 | 0 | 0.00006751 | 0.03604802 | 537,202 |
| `cjxl` forced linear | -0.00379309 | 0 | 0.00006751 | 0.03604802 | 537,202 |
| `cjxl` forced linear, non-perceptual | -0.04045153 | 8,615 | 0.00055427 | 0.00714181 | 147,164 |
| imagecodecs sRGB | -0.03998225 | 7,023 | 0.00028588 | 0.00301334 | 89,039 |
| `cjxl` default | -0.03998225 | 7,023 | 0.00028588 | 0.00301334 | 89,039 |
| `cjxl` forced sRGB | -0.03998225 | 7,023 | 0.00028588 | 0.00301334 | 89,039 |

The matching imagecodecs/cjxl rows demonstrate that transfer metadata, rather
than the Python array layout or TIFF container, determines the default
behavior. The non-perceptual row demonstrates separately that lossy libjxl can
bypass XYB and retain the negative tail.

The tifffile forwarding path was also tested:

| tifffile JPEG XL transfer | Minimum after decode | Pixels below `-0.004` | Maximum error |
|---|---:|---:|---:|
| linear | -0.00379308 | 0 | 0.03604802 |
| sRGB | -0.03991238 | 7,059 | 0.00266033 |

Tifffile therefore forwards the imagecodecs `transfer` argument correctly.
The small difference from the direct path is consistent with TIFF strip
segmentation.

## Diagnostic figures

![Full-image lossy value comparison](lossy_value_comparison.png)

The four decoded-value panels use a shared diverging colorbar centered on zero.
The imagecodecs and `cjxl` linear-light XYB outputs show the same hard floor
near `-0.00379`; the non-perceptual lossy output continues through the
source's negative range.

![Detail around the negative minimum](lossy_negative_detail.png)

The upper row shares the sample-value colorbar. The lower row shares a signed
error colorbar. Around the source minimum, the XYB path shows a large positive
error caused by its irreversible clamp, whereas the non-perceptual path shows
ordinary lossy error without that floor.

## Source trail

### 1. Imagecodecs defaults float input to linear sRGB

The JPEG XL encoder documents:

> Float must be in nominal range [0, 1].

See
[`imagecodecs/_jpegxl.pyx`, lines 170-174](https://github.com/cgohlke/imagecodecs/blob/v2026.6.26/imagecodecs/_jpegxl.pyx#L170-L174).

When no transfer is supplied, the encoder selects sRGB only for uint8 and
linear sRGB for every other supported type, including float32:

[`imagecodecs/_jpegxl.pyx`, lines 419-446](https://github.com/cgohlke/imagecodecs/blob/v2026.6.26/imagecodecs/_jpegxl.pyx#L419-L446).

The relevant branch is equivalent to:

```cython
elif pixel_format.data_type == JXL_TYPE_UINT8:
    JxlColorEncodingSetToSRGB(...)
else:
    JxlColorEncodingSetToLinearSRGB(...)
```

This agrees with libjxl's documented default for floating-point pixel buffers,
but it does not match `cjxl`'s treatment of PFM input.

### 2. The cjxl PFM path defaults to nonlinear sRGB

`cjxl` decodes PFM through libjxl's shared PNM/PFM reader. That reader applies
the PNM default color hint, which is nonlinear sRGB:

[`lib/extras/dec/pnm.cc`, lines 486-490](https://github.com/libjxl/libjxl/blob/v0.12.0/lib/extras/dec/pnm.cc#L486-L490).

This default also applies to PFM because no PFM-specific transfer function
overrides it.

The following controlled `cjxl` color hints confirmed the distinction:

```console
-x color_space=Gra_D65_Rel_Lin
-x color_space=Gra_D65_Rel_SRG
```

The linear hint reproduced imagecodecs' clipping exactly. The sRGB hint
reproduced normal `cjxl` behavior exactly.

### 3. Libjxl performs the actual clamp

Libjxl's lossy VarDCT path converts linear RGB to XYB. After calculating opsin
absorbance, it explicitly replaces negative absorbance values with zero:

[`lib/jxl/enc_xyb.cc`, lines 90-101](https://github.com/libjxl/libjxl/blob/v0.12.0/lib/jxl/enc_xyb.cc#L90-L101).

For sufficiently negative linear grayscale samples, this clamp destroys the
negative tail before quantization. Nonlinear sRGB maps the same numeric samples
to much smaller linear-light magnitudes before the XYB conversion, keeping them
above the clamp threshold.

This behavior is notable because the libjxl API says float samples may be
outside the nominal range, provided they are finite:

[`lib/include/jxl/encode.h`, lines 659-707](https://github.com/libjxl/libjxl/blob/v0.12.0/lib/include/jxl/encode.h#L659-L707).

## Imagecodecs issue boundary

There is no single incorrect pointer, dtype, endianness, or bit-depth assignment
in imagecodecs. Float32 is correctly passed as `JXL_TYPE_FLOAT` with 32 bits
and 8 exponent bits.

The actionable imagecodecs problems are instead:

### Silent handling of documented-invalid input

Imagecodecs documents float input as restricted to `[0, 1]` but does not
validate that range. It accepts negative values and silently returns a severely
clipped lossy result. If the range remains unsupported, the encoder should
raise `ValueError` for non-finite or out-of-range float samples.

### Non-perceptual mode is bound but not exposed

Imagecodecs' libjxl declarations include
`JXL_ENC_FRAME_SETTING_DISABLE_PERCEPTUAL_HEURISTICS`, but
`jpegxl_encode` does not expose or set it:

[`imagecodecs/libjxl.pxd`](https://github.com/cgohlke/imagecodecs/blob/v2026.6.26/imagecodecs/libjxl.pxd#L744-L784).

The `cjxl` implementation treats non-perceptual encoding like lossless
encoding for profile preservation by setting
`basic_info.uses_original_profile=true`:

[`lib/extras/enc/jxl.cc`, lines 259-267](https://github.com/libjxl/libjxl/blob/v0.12.0/lib/extras/enc/jxl.cc#L259-L267).

With explicit linear input and `--disable_perceptual_optimizations`, the test
retained the negative tail:

```text
minimum=-0.04045153
pixels below -0.004=8615
maximum error=0.00714181
```

An imagecodecs enhancement could expose a `disable_perceptual` option and,
when enabled:

1. set `basic_info.uses_original_profile = JXL_TRUE`; and
2. call `JxlEncoderFrameSettingsSetOption` with
   `JXL_ENC_FRAME_SETTING_DISABLE_PERCEPTUAL_HEURISTICS`.

A regression test should use a float32 grayscale array containing values below
zero and verify that the selected preservation mode does not introduce a hard
negative floor.

## Practical choices for this project

### Use native lossless float mode for exact arrays

Tifffile and imagecodecs already preserve this float32 input bit-for-bit:

```python
compressionargs={"lossless": True}
```

### Use non-perceptual lossy libjxl when numerical approximation is acceptable

Direct libjxl and `cjxl --disable_perceptual_optimizations` can encode the
original profile lossily without the XYB clamp. This is the appropriate JPEG XL
mode for the signed float case, but imagecodecs must expose both
`uses_original_profile` and the frame option before tifffile can select it.
JPEG XL distance remains a quality target, not a maximum-error guarantee.

### Continue normalizing to [0, 1]

The existing affine transform is the safest currently exposed lossy tifffile
option for arbitrary scientific scalar data. It avoids assigning physical color
semantics and provides the smallest maximum error in the current tests.

### Declare sRGB explicitly

This removes the negative-tail clamp and matches `cjxl`'s PFM behavior:

```python
compressionargs={
    "distance": 0.01,
    "effort": 7,
    "transfer": "SRGB",
}
```

However, this declares the numeric samples to be nonlinear sRGB. That may be
semantically incorrect for scientific data even though it improves numeric
round-trip behavior.

### Upstream reports

A useful imagecodecs report should focus on silent clipping, missing range
validation, and the absence of a non-perceptual/profile-preserving option.

A separate libjxl report can demonstrate that lossy VarDCT clips negative
linear-light values at the XYB absorbance clamp despite the C API allowing
finite values outside the nominal range.

## Reproduction

Run:

```console
pixi run python jxl_negativity_repro/reproduce.py
```

The reproducer compares the original input, supplied JXL, dynamically invoked
`cjxl` perceptual and non-perceptual lossy modes, direct imagecodecs,
tifffile JPEG XL, and the normalized tifffile path. It also regenerates both
diagnostic PNGs.
