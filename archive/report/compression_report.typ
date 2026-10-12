#import "@preview/codly:1.3.0": *
// #import "@preview/cetz:0.4.2"
#import "@preview/unify:0.7.1": num, qty, numrange, qtyrange, add-unit
#import "@preview/algorithmic:0.1.0"
#import "@preview/physica:0.9.8": TT, curl, dv, grad, pdv, tensor

#import "@preview/meander:0.4.1"
#import "@preview/algorithmic:1.0.7"
#import "@preview/subpar:0.2.2"
#import algorithmic: algorithm, algorithm-figure, style-algorithm


#import "preamble_funcs.typ": mathformatter, mref
#import "style.typ": frontpage-1, style
#import "tableaux.typ" as tableaux

#show: style-algorithm
#show: style
#set page(numbering: "i")
#show figure.caption: set text(size: 9.5pt)

// Fix smallcaps in math
#show math.equation: it => {
  show smallcaps: set text(font: "Libertinus Serif")
  it
}

#let num = num.with(multiplier: "×")

#let vv = mathformatter(underbars: 0, bold: true, upright: false)
#let mm = mathformatter(underbars: 0, bold: false, upright: true)
#let vvh = x => math.hat(vv(x))

#add-unit("pixel", "px", "upright(\"px\")")

#let SSIM = $"SSIM"$

#set math.mat(delim: "[")
#let _thinner-space = 1em / 9
#let _thin-space = 1em / 6
#let _med-space = 2em / 9
#let _thick-space = 5em / 18
#let _quad-space = 1em
#let _wide-space = 2em
#let _wider-space = 3em
#let wider = h(_wider-space)
#let ratio(ant, con) = $#ant#h(_thinner-space, weak: true)#sym.ratio#h(_thinner-space, weak: true)#con$


#let nobreak(body) = block(breakable: false)[#body]
#let steal-margin(body) = block[
  #show: pad.with(right: -10mm)
  #body
]
#let right-figs(inner) = steal-margin[#meander.reflow(inner)]

#set document(title: "Report on Compressibility of X-Ray CT Projections and Reconstructions")
#let authors = (
  [Jeppe Klitgaard #link("emailto:s250250@dtu.dk", raw("<s250250@dtu.dk>"))],
)

#let abstract = [
  #set heading(numbering: none)
  #show heading: set text(size: 16pt)
  #set par(justify: true)
  #set text(size: 12pt)
  = Abstract

  #lorem(100)
]

// -- Title Page ---
#frontpage-1(front-content: abstract, authors: authors, date: datetime(year: 2026, month: 7, day: 30))

// --- Frontmatter ---
#set page(numbering: "I")
#counter(page).update(1)
#counter(heading).update(0)
#outline()

// --- Content ---
#pagebreak(weak: true)
#set page(numbering: "1")
#counter(page).update(1)
= Introduction <sec:intro>
This report investigates compressibility of X-Ray CT data in the form of both projections and volumetric reconstructions with the goal of proposing compression schemes suitable for various applications, with the primary focus being on archival storage of large datasets.

The full source code for the data compression experiments, analysis and the report itself is available at #link("https://github.com/qim-center/consult-naturarv-compression").

= Background <sec:background>

The reader may benefit from the terse overview of the relevant background and terminology found in this section, or may skip ahead to @sec:projections.

The authoritative standard on medical imaging is the Digital Imaging and Communications in Medicine (DICOM) standard, which helpfully specifies a number of compression schemes that should be supported by software compliant with the DICOM standard @ref:DICOM-ps3.5-2026c, which includes:
- Various JPEG standards — JPEG 1, JPEG-LS, JPEG 2000, JPEG 2000 (HTJ2K), JPEG-XL
- Various MPEG (video) standards — MPEG-2, MPEG-4 AVC/H.264, HEVC/H.265
- Run Length Encoding (RLE)

== Compression Quantities <sec:compression-quantities>
We define the _compression ratio_, $η$, as the ratio of the uncompressed data size to the compressed data size,
$
  η ≔ B_"uncompressed" / B_"compressed"
$
which is also commonly expressed as a ratio, e.g. $η = ratio(10, 1)$, indicates that the compressed data is 10 times smaller than the uncompressed data.

A related quantity is the _space saving_, $σ$, which refers to the fraction of the uncompressed data size that is saved by compression,
$
  σ ≔ 1 - 1/η,
$
where the previous example of $η = ratio(10, 1)$ corresponds to a space saving of $σ = 90%$.



== Lossy and Lossless Compression <sec:lossy-lossless>
Within compression of media assets, we distinguish between two important schemes: _lossless_ and _lossy_ compression, where _lossless compression_ refers to compression methods which identically reproduce the original data upon decompression, whereas _lossy compression_ refers to methods that irreversibly discard information in order to achieve higher compression ratios.

Generally, both of these methods can be tuned to suit the application at hand. Within lossless compression algorithms, there is commonly a trade-off between higher compression ratios and the computational cost of compression and/or decompression, where higher computation cost generally offers diminishing returns in terms of the achieved compression ratio.

Lossless compression methods applied to X-Ray CT projection datasets achieve typically achieve compression ratios in the range $η ∈ [1.2, 2.0]$, with JPEG-LS (Goulomb-Rice) achieving a mean compression ratio of $η = ratio(1.70, 1)$ across 26 medical CT scans according to @ref:wegenerRealtimeCompressionRaw2009[Table 2], where a non-standard, proprietary algorithm is reported to achieve a mean compression ratio of $η = ratio(1.95, 1)$.

While this trade-off also exists for lossy compression methods, there is the additional trade-off between compression ratio and the quality of the reconstructed data, where lossier compression schemes are generally able to achieve higher compression ratios. Additionally, it is difficult to reason about the quality loss on the reconstructed volume associated with lossy compression of the projection data, particularly when iterative reconstruction methods are employed. Analysis of the effects of lossy compression is therefore often performed only on the reconstructed volume and only rarely across the entire pipeline from projection data to reconstructed volume. A notably exception to this is the work of @ref:wegenerEffectsFixedrateCT2010, wherein the authors find that a conpression ratio of $η = ratio(3, 1)$ on the projection data resulted in a minimal _local_ structure similarity index measure (SSIM) of $0.99$, which according to a small study of radiologists may be considered nigh imperceptible.

== Data Storage Formats <sec:data-storage-formats>

X-Ray CT projection data is most commonly stored as a series of 2D `TIFF` images corresponding to each projection alongside a metadata file describing the acquisition parameters. As an example, Nikon's CT systems store the projection data in a folder containing uncompressed TIFF images alongside a metadata file in their propritary `.xtekct` format. Storing the projections as regular image files is convenient, as it allows for easy inspection of the projections using standard images viewers, but limits the compression schemes to those supported by the image file format, and additionally does not allow for compression using information across projections.

`TIFF` is by far the most commonly used image file format for storing X-Ray CT projection data and natively supports many different bit-depths and data types, including up to 64-bit integers and 16/32/64-bit floating point numbers, while also supporting up to #num("65 535") channels. Through extensions, it supports a number of compression schemes including lossless and lossy JPEG, LZW, Deflate, PackBits, LERC, and others. It should be noted that some of the more exotic compression extensions, while supported by `libtiff`, are not supported widely supported by image viewers and other software.


== Image Quality Assessment <sec:iqa>

In order to evaluate the quality of lossy compression schemes, we employ a number of _full-reference image quality assessment_ (FR-IQA) metrics. We adopt TODO as our primary quality index, and additionally report several other commonly used measures to ease comparison with the existing literature.

// TOOD: I think this is probably a bad idea since it becomes very sensitive to outliers!
// In order to make the IQA metrics invariant to the dynamic range of the images, which may vary across datasets

=== Structural Similarity Index Measure (SSIM) <sec:ssim>

We employ the commonly used _structural similarity index measure_ (SSIM), which given a reference image $a$ and a distorted image $b$ of the same size computes a quality index $SSIM(a, b) ∈ [-1, 1]$ over local windows of the images:
$
  SSIM(a, b) = ((2μ_a μ_b + c_1) (2σ_(a b) + c_2)) / ((μ_a^2 + μ_b^2 + c_1) (σ_a^2 + σ_b^2 + c_2))
$ <eq:ssim>
where $μ_a, μ_b$ are the local means of the images, $σ_a^2, σ_b^2$ are the local variances, $σ_(a b)$ is the local covariance, and $c_1 ≔ (0.01 L)^2, c_2 ≔ (0.03 L)^2$ are small, stabilising constants given the dynamic range $L$ across images of each reference dataset — that is, across all projections or vertical slices of a reconstruction.

To match the canonical parametrisation of Wang et al. @ref:wangImageQualityAssessment2004, the local moments are computed as weighted sums using a circularly symmetric Gaussian kernel with standard deviation $σ_w = qty("1.5", "px")$ such that each window is normalised to unit mass.

Both the mean SSIM and summary statistics of the local SSIM values are computed, where use of the minimum local SSIM value is motivated by @ref:wegenerEffectsFixedrateCT2010.

===

== Encodings / Formats

#block(breakable: false)[
@tbl:encodings contains an overview of various encoding schemes that have been considered for inclusion in this study, along with their suitability for the task at hand.

As a minimal requirement, the codecs are required to support unsigned integers of 16 bit depth,
which excludes some older and web-focused codecs, as well as those only supporting floating-point numbers.

#let evaler(x, ..args) = {
  let pattern = regex("\|([^|]*)\|")
  let show-rule = it => {
    let inner = it.text.matches(pattern).at(0).captures.at(0)
    strong(inner)
  }
  let eval-str-lines = (
    "#show pattern: show-rule",
    x,
  )
  let eval-str = eval-str-lines.join("\n")
  let scope = (
    pattern: pattern,
    show-rule: show-rule,
    num: num,
  )

  eval(eval-str, scope: scope, mode: "markup")
}

// Sources:
// https://en.wikipedia.org/w/index.php?title=TIFF&oldid=1362557219&useskin=vector#TIFF_Compression_Tag

#let encodings-data = csv("encodings.csv").map(row => row.map(cell => evaler(cell, mode: "markup")))
#[
  #set text(size: 9pt)
  #figure(
    tableaux.ez-table(encodings-data, inset: 3pt, header-transform: it => {
      show text: set text(size: 1.1em)
      std.strong(it)
    }),
    caption: include("encodings_caption.typ"),
  ) <tbl:encodings>
]
]

=== JPEG-XL <sec:jpeg-xl>

@ref:jpeg-xl

// codex://threads/019f9fed-af7e-7f50-8d06-9f35b5d49920
- Must use `LINEAR` transfer function
  - Important for lossy mode
  - For lossless mode this just ensures correct metadata
- Photometric: Grayscale
- Planar: Just depends on input shape, but generally should be TRUE if (P, X, Y) used
- Primaries: ??
- Transfer: Linear
- Level: Always 5 or 10
  - 5: Standard, only 16 bit depth, smaller image sizes
  - 10: Extended, supports 32 bit depth, larger image sizes
- Note: A lot more options available that are not exposed via `imagecodecs` interface, but could be exposed with patches.
- `libjxl 0.12` currently broken for f32 data, see:
  - https://github.com/cgohlke/tifffile/issues/332
  - https://github.com/libjxl/libjxl/issues/4902
  - https://github.com/libjxl/libjxl/issues/4905
  - Hopefully fixed in `libjxl 0.13` (not yet released at time of writing), see: https://github.com/libjxl/libjxl/issues/4894

== Data Collection Methodology <sec:data-collection>

// Find using `bmgroup -w -r`
#let bmgroup-output = "n-62-11-67 n-62-11-56 n-62-11-68 n-62-11-57 n-62-11-69 n-62-11-58 n-62-11-59 n-62-11-60 n-62-11-61 n-62-11-50 n-62-11-62 n-62-11-51 n-62-11-63 n-62-11-52 n-62-11-64 n-62-11-53 n-62-11-65 n-62-11-54 n-62-11-66 n-62-11-55"
#let num-hosts-in-group = bmgroup-output.split(" ").len()

To promote reproducibility of the results, all data was collected in August of 2026 on the DTU HPC cluster using nodes belonging to the `rhpccascadelaker` host group consisting of #num-hosts-in-group nodes with `XeonGold6226R` CPUs.

To ensure the benchmarks measure the encoding and decoding speeds as accurately as possible,
the datasets were first loaded into memory either within the Python interpreter for `zarr`-based tests, or by loading the data into the node-local RAM disk (`tmpfs`) located at `/dev/shm` for executable-based tests.



= Projection Data <sec:projections>

== Data Layout Considerations
For reconstruction and inspection, the preferred data layout is _projection-major_ where each projection is stored contiguously in memory, corresponding to an array shape of $(P, X, Y)$, where $P$ is the projection index, and $X$ and $Y$ are the horizontal and vertical pixel coordinates, respectively. If the projections were to be considered as _channels_, this layout is often referred to as _planar_ within the context of image processing, and differs from the _interleaved_ layout that is default for many image file formats.

Most image codecs

== File Format Considerations
TODO

Options:
- TIFF stack (few codecs, image viewer (even fewer with non-standard formats)
- Non-TIFF stack (many/any codec, image viewer)
- HDF5 (supports many codecs, no/few image viewer)
- ZARR (supports many codecs, no/few image viewer)
- Other container format (no advantages, not widely supported by image viewers)

= Reconstruction Data <sec:reconstructions>

= Discussion <sec:discussion>

= Conclusions <sec:conclusions>

// --- Backmatter ---
#pagebreak(weak: true)
#set page(numbering: "i")
#counter(page).update(1)
#bibliography(
  ("references.bib", "zotero_references.bib"),
)

// Appendix
#set heading(numbering: none, supplement: [Appendix])
= Appendix <app>
#set heading(numbering: "A.1", supplement: [Appendix])
#counter(heading).update(1)

== A note of TIFF stacks <app:tiff-size>

While TIFF is just a container format and can in fact contain multiple images in a single container,
we rarely see this in XCT due to the fact that the total TIFF file size is limited to 4 GiB due to the 32-bit offset used in the TIFF file format.

This limitation is present in the standard `libtiff` library, but removed in the `BigTIFF` library.
Unfortunately, choosing to use BigTIFF means that the produced files are no longer compatible with the
much more widely used `libtiff` library.

For this reason, we and others usually opt for storing each projection or layer as a separate TIFF file in a directory.

== Note on HPC Host Groups <app:hpc-host-groups>

The hostgroup was chosen by running `bmgroup -w -r` and `nodestat -F` to find a host group with a relatively large number of nodes with the same, modern CPU architecture.
