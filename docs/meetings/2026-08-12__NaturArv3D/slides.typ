#import "@preview/touying:0.7.4": *
#import "@preview/grayness:0.7.0": image-transparency
#import "@preview/unify:0.8.1": add-unit, num, numrange, qty, qtyrange, unit
#import "@preview/suboutline:0.3.0": suboutline
#import "@local/dutten-slides:0.1.0": dutten-theme, progress-marker-both, progress-marker-lower, progress-marker-upper

#let footers = (
  utils.display-info-date,
  self => [#self.info.title – #self.info.subtitle],
  context [#utils.slide-counter.display() / #utils.last-slide-number],
)
#show: dutten-theme.with(
  title: [NaturArv3D],
  subtitle: [Compression Study],
  author: [Jeppe Klitgaard],
  date: [2026-08-04],
  institution: [Center for Quantification of Imaging Data from MAX IV],
  footers: footers,
  footer-style: "thick",
  // color: rgb(252, 115, 35),  // QIM Orange
  color: rgb(230, 63, 71),  // QIM Red
  background-color: rgb(248, 249, 250),  // QIM Background
  logo: image-transparency(read("qim_logo.png", encoding: none), width: 2.5cm, alpha: 50%),
)

#set text(size: 20pt)
#show figure.caption: set text(size: 16pt)
#show raw: it => highlight(it, extent: 2pt, fill: gray.transparentize(70%), radius: 3pt)
#show link: set text(font: "DejaVu Sans Mono", fill: navy.lighten(20%))
#show footnote.entry: set text(size: 14pt)
#let skip = (body) => {
  set text(fill: black.transparentize(50%))
  body
}

= <study>

#align(center)[
  #set text(size: 36pt, weight: "bold")
  NaturArv3D Compression Study

  #set text(size: 24pt, weight: "regular")
  Meeting 2026-08-12
]

== Outline <outline>
#outline(
  title: none,
  target: heading.where(outlined: true).after(<outline>, inclusive: false),
  depth: 2,
  indent: n => 1.2em * calc.max(0, n - 1),
)

== Introduction
- About me: Jeppe
  - MSc student in Mathematical Modelling and Computation at DTU
  - R&D Scientist in NMR sensor technology company
  - BA (MA) (Hons) Natural Science — Physics at Cambridge
- Started in QIM Center in July 2026
- Assigned to NaturArv3D project
  - Reachable at `s250250@dtu.dk`

== Motivation
- NaturArv3D will generate *lots* of data
  - Proj#footnote[Assumes 1572 projections (which seems ambitious given 500 samples/week)], 4(*2*)K\@16bit: ≈ 50(*13*)GB
  - Recon, 4K\@32(*16*)bit: = 128(*64*)GB
  - Recon, 2K\@32(*16*)bit: = 16(*8*)GB
  - × 500 samples/week ⇒ 10-50 TB/week!
  - ⇒ #num("1500") — #num("7500") DKK per week#footnote[Hand-wavey estimate of #num("150") DKK/TB for 5 years of redundant HDD storage]? ∼100 kDKK per year?
- *Finding correct compression scheme enables significant cost savings*
- No up-to-date, comprehensive studies available in the literature
- #skip[@ref:pambrunComputedTomographyImage2015, 2015: storage cost significant portion of \$3.5 billion rollout of Electronic Health Records in Canada]

== _Current_ Goals
Phase 0 (today, later slide?)
- Determine requirements around formats, compatibility, quality, speed, etc. for reconstructions (NHMD, QIM?), and projections (QIM)
  - #skip[TIFF-stack required, or Zarr acceptable for reconstructions?]
  - #skip[How exotic of a codec can we use?]


Phase 1 (soon)
- Study compression ratios (CR) and encoding/decoding speeds for different *lossless* codecs on *projection* _and maybe reconstruction_ data
- Study CRs, speeds, and _quality_ for different *lossy* codecs on *reconstruction* data

#skip[Phase 2 (optional?)
- Study effect of *lossy* compression of *projection* data on reconstruction quality for FDK, maybe iterative?]

== Literature Review
- Literature suggests @ref:wegenerRealtimeCompressionRaw2009, @ref:wegenerEffectsFixedrateCT2010:
  - Projections: $"CR" ∈ [1.7, 2]$ for lossless
  - #skip[Projections: $"CR" ≈ 3$ for near-lossless (indisguishable reconstructions)]
  - Reconstructions: National Medical Boards: $"CR" ∈ [5, 30]$ (lossy) @ref:liuCurrentRoleImage2017
- Recent JPEG-XL codec adopted by DICOM standard @ref:DICOM-ps3.5-2026c
#skip[
- LERC codec allows for guaranteed error bounds
  - Good candidate for lossy compression of projections
]

== Preliminary Experiments: Lossless

#cols(columns: (1.5fr, 1fr))[
- Lossless compression of projections
  - As a rule, 50% space saving is best case for 16-bit XCT data @ref:wegenerRealtimeCompressionRaw2009, @ref:maroneImpactLossyCompression2020
- Across 12 codecs and 506 configurations:
  - JPEG-XL (v0.12) performs best
    - CR ≈ 1.7 ⇒ 41% space saving
  - JPEG-2K, JPEG-LS close (CR ≈ 1.62)
  - PNG, ZStd, LERC, DEFLATE, … much worse (CR ≈ 1.3)
- JPEG-XL pros: u8/u16/f16/f32 support, #skip[tunable, high CR, open-source, adopted by DICOM]
#skip[
- JPEG-XL cons: very new, immature ecosystem, no support in older software]
][
  #figure(image("2026-08-11_lossless_plot_tall.png"))
]

== Preliminary Experiments: Lossy

#cols(columns: (1.25fr, 1fr))[
- 3D reconstructions take up bulk of storage
- Can be remade from archived projections
- This enables lossy compression
- Lossy JPEG-XL:
  - Distance 1 (middle row) gives 98.9% space saving
    - CR=90.5, SSIM=0.9992
  - Distances >1 produce noticeable artefacts and smoothening
  - Distance 0.1 gives 92.1% space saving
    - CR=12.7, SSIM=0.9995
#skip[
- No guaranteed error bounds in JPEG-XL
  - Future experiments include LERC for error bounds
]
][
  #figure(image("2026-08-11_jpegxl_quality_comparison.png"))
]

#progress-marker-upper
== Discussion: Scope
- NHMD requirements and desired output?
- NHMD wants only _reconstructions_ (?)
  - Desired/required format?
  - Note: TIFF is container format ⇒ _a TIFF is not just a TIFF_
    - _Many_ compression schemes available, *only few with wide-spread support*
      - DEFLATE, LZW — both lossless, bad CR
- Help me understand use-cases
  - How will data be used?
#skip[
- Archivability concerns
  - Offer: Produce x86_64 Linux container image with decoder
    - Should be runnable also in 50 years
]
- QIM/3DIM/DTU wants _projections_, maybe reconstructions
  - Wants to store as close to lossless as possible


== Bibliography
#bibliography("zotero_references.bib", title: none)