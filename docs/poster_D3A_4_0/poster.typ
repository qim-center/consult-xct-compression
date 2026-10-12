#import "@local/dutten-poster:0.1.0": template
#import "@local/dutten:0.1.0": poster
#import "@local/jutils:0.1.0"
#import "attribution.typ": authors
#import "deps.typ": (
  deixis, dutten.colors-rgb, dutten.get-logo, dutten.poster, jutils.author.get-corresponding,
  jutils.author.render-affiliations, jutils.author.render-authors, jutils.author.render-corresponding,
  jutils.recolor-svg, sigfig.round, tiaoma, tiaoma.qrcode, unify.numrange, unify.qty, unify.qtyrange, zero.num,
  zero.quan,
)
#import deixis: *
#import "constants.typ": front-color, primary-color, qim-grey
#import "viz.typ": swoosh

#show: deixis-setup-notes

#let size-small = 24pt
#let size-extra-small = 20pt
#let size-body = 32pt
#let size-authors = 44pt

#set figure(numbering: none)
#show heading: set block(above: 1.0em)
#set list(spacing: 0.8em)

#set document(
  title: [Compression Strategies for High-Throughput X-Ray CT of Natural History Collections],
)
#let header-block = context block(
  fill: primary-color,
  outset: (
    left: page.margin.left,
    right: page.margin.right,
    top: page.margin.top,
  ),
  height: 45mm + page.margin.top,
  width: 100%,
  [
    #let qim-color = front-color
    #let dtu-color = front-color
    #let snm-color = front-color

    #pad(bottom: page.margin.left)[
      #grid(
        columns: (auto, 1fr, auto, 10mm, auto, 10mm, auto, 1fr, auto, 14mm, auto, 1fr, auto),
        align: horizon,

        recolor-svg(path("assets/SNM_logo.svg"), snm-color, height: 100%),
        none,
        recolor-svg(path("assets/QIM_logo.svg"), qim-color, height: 90%),
        none,
        line(angle: 90deg, length: 90%, stroke: (
          thickness: 4pt,
          cap: "round",
          paint: qim-color,
        )),
        none,
        [
          #set text(font: "Nunito", size: 40pt, fill: qim-color, weight: 700)
          #set par(leading: 0.55em)
          Center for Quantification of\
          Imaging Data from MAX IV
        ],
        none,
        get-logo(front-color, height: 100%),
        none,
        [
          #set align(top + left)
          #set text(font: "Neo Sans Pro", fill: dtu-color)
          #set par(leading: 0.50em, spacing: 0.5em)
          #set text(size: 28pt, weight: "medium")
          Technical\
          University of\
          Denmark
          // #set text(font: "Neo Sans Pro", fill: dtu-color)
          // #set par(leading: 0.50em, spacing: 0.5em)
          // #set text(size: 46pt, weight: "medium")
          // DTU Compute\
          // #set text(size: 38pt, weight: "regular")
          // #set par(leading: 0.45em)
          // Department of Applied Mathematics\
          // and Computer Science
        ],
        none,
        recolor-svg(path("assets/NNF_logo_vertical.svg"), qim-color, height: 100%),
      )
    ]
  ],
)

#let footer-height = 70mm
#let footer-block = box(height: footer-height + 15mm, stack(
  grid(
    columns: (auto, 100mm, 1fr),
    align: (bottom, bottom + left, bottom + right),
    stack(
      block(place(
        bottom + left,
        dy: -10mm,
        block[
          #set text(size: size-small)
          #deixis-print-endnotes(gap: 0.6em)
        ],
      )),
      context block(
        height: footer-height,
        fill: primary-color,
        outset: (
          left: page.margin.left,
        ),
        inset: (
          top: 10mm,
          right: 10mm,
          bottom: 10mm,
        ),
        align(top)[
          #set text(fill: front-color, size: size-extra-small)
          #render-affiliations(authors, content-transform: x => x, address-transform: emph).join(linebreak())
        ],
      ),
    ),
    swoosh(footer-height),
    // = height of the block on the left
    stack(
      dir: ltr,
      spacing: 20mm,
      place(
        top,
        dx: 5mm,
        dy: 10mm,
        float: true,
        scale(x: -100%, image("assets/seal_skulls/RingedSeal-BrainFreeze-Prelim1.png", height: 80%)),
      ),
      align(
        horizon + center,
        stack(
          dir: ttb,
          spacing: 5mm,
          qrcode(
          "https://qim.dk/",
          height: 50%,
          options: (
            fg-color: black.transparentize(50%),
            output-options: (
              barcode-dotty-mode: true,
            ),
            dot-size: 1.0,
          ),
        ),
        [
          #set align(center)
          #set text(size: size-small, fill: black.transparentize(50%))
          QIM
        ]
        ),
      ),
      align(
        horizon + center,
        stack(
          dir: ttb,
          spacing: 5mm,
          qrcode(
          "https://www.linkedin.com/in/jeppeklitgaard/",
          height: 50%,
          options: (
            fg-color: black.transparentize(50%),
            output-options: (
              barcode-dotty-mode: true,
            ),
            dot-size: 1.0,
          ),
        ),
        [
          #set align(center)
          #set text(size: size-small, fill: black.transparentize(50%))
          LinkedIn
        ]
        ),
      ),
      image("assets/profile.webp", height: 100%),
    ),
  ),
  context block(
    width: 100%,
    fill: primary-color,
    outset: (
      left: page.margin.left,
      right: page.margin.right,
      bottom: page.margin.bottom,
    ),
    height: page.margin.bottom,
    inset: 10mm,
    grid(
      columns: (1fr, auto),
      align: (left, right),
      align(horizon)[
        #set text(fill: front-color, size: 24pt, weight: "semibold")
        Danish Digitalization Data Science and AI Conference, 8$thin$–$thin$9 October 2026
      ],
      align(horizon)[
        #set text(fill: front-color, size: 22pt, weight: "semibold")
        \*
        #set text(font: "DejaVu Sans Mono")
        #get-corresponding(authors).at(0).email
      ],
    ),
  ),
))


#show: poster.with(
  authors: render-authors(authors, corresponding-marker: "*").join(", "),
  header-block: header-block,
  footer-block: footer-block,
  size-title: 102pt,
  size-authors: size-authors,
  size-caption: size-small,
  size-body: size-body,
)


#let sc(body, scaling: 0.9) = {
  show regex("[\\p{Lu}\\p{Nd}]+"): it => context {
    set text(scaling * 1em, stroke: 0.01em + text.fill)
    it
  }
  body
}

#show "NHMD": sc[NHMD]
#show "3DIM": sc[3DIM]
#show "DICOM": sc[DICOM]
#show "CR": sc[CR]
#show "TIFF": sc[TIFF]
#show "OME-Zarr": sc[OME-Zarr]
#show "μCT": sc[μCT]
#show "JPEG-LS": sc[JPEG-LS]
#show "JPEG 2000": sc[JPEG 2000]
#show "DKK": sc[DKK]
#show "TB": sc[TB]
#show "GB": sc[GB]
#show "PB": sc[PB]
#show "PSNR": sc[PSNR]
#show "SSIM": sc[SSIM]
#show "HTJ2K": sc[HTJ2K]
#show "LERC": sc[LERC]
#show "ZFP": sc[ZFP]
#show "SZ3": sc[SZ3]
#show "SPERR": sc[SPERR]
#show "Pcodec": sc[Pcodec]

#let ratio(x) = {
  let (nom, denom) = x.split(":")
  [$nom#h(0.1em)∶#h(0.1em)#denom$]
}

= Introduction <sec:intro>
The _NaturArv3D_ pilot project aims to *digitise the vertebrate collection* at Natural History Museum Denmark (NHMD) in collaboration with the 3D Imaging Centre, Technical University of Denmark (3DIM).

As necessitated by the scale of the collection, a custom high-throughput X-ray μCT scanner with a robotic sample handling system is being developed at 3DIM with a designed capacity of *500 samples per week*.

#figure(
  image("assets/flow/flow.svg", width: 100%),
  caption: [
    #set text(size: 28pt)
    The proposed _NaturArv3D_ pipeline for high-throughput X-ray μCT of museum artefacts.],
) <fig:workflow>


= Background <sec:background>
#let facility-utilisation-rate = 0.5
#let crop-rate = 0.5
#let middle-3k-fraction = 0.7 // Fraction of samples that are scanned with small detector

#let _lower-factor = calc.pow(3072, 3)
#let _upper-factor = 4800 * 5606 * 5606
#let _middle-factor = _lower-factor * middle-3k-fraction + _upper-factor * (1 - middle-3k-fraction)

#let data-f32-lower = _lower-factor * 4
#let data-f32-middle = _middle-factor * 4
#let data-f32-upper = _upper-factor * 4

#let data-u16-lower = _lower-factor * 2
#let data-u16-middle = _middle-factor * 2
#let data-u16-upper = _upper-factor * 2
#let samples-per-year = 500 / 7 * 365.2425

#let realistic-annual-output-bytes = data-u16-middle * crop-rate * facility-utilisation-rate * samples-per-year


#let DKK_per_GBP = 8.70
#let cambridge_RCS_RDS_GBP_per_TB_per_year = 95.0
#let storage-cost-DKK-5-year-per-byte-cambridge = cambridge_RCS_RDS_GBP_per_TB_per_year * 5 * DKK_per_GBP * 1e-12
#let cambridge_RCS_RDS_DKK_per_TB_per_year = cambridge_RCS_RDS_GBP_per_TB_per_year * DKK_per_GBP

#let DKK_per_USD = 6.39
#let backblaze_B2_USD_per_TB_per_year = 83.0
#let storage-cost-DKK-5-year-per-byte-backblaze = backblaze_B2_USD_per_TB_per_year * 5 * DKK_per_USD * 1e-12
#let backblaze_B2_DKK_per_TB_per_year = backblaze_B2_USD_per_TB_per_year * DKK_per_USD

#let estimated_DKK_per_TB_per_year = 600
#let storage-cost-DKK-5-year-per-byte-estimate = estimated_DKK_per_TB_per_year * 1e-12 * 5

#let estimated-amortised-cost-DKK-per-year = realistic-annual-output-bytes * storage-cost-DKK-5-year-per-byte-estimate

// #{ storage-cost-DKK-5-year-per-byte-cambridge * 4 * 1e9 }

// #{ estimated-amortised-cost-DKK-per-year }

// #samples-per-year

- Up to #num("26000") samples per year
- sub-#quan[10 mum] resolution at $3072^3$ to $4800×5606^2$ voxels per sample
  - #numrange(round(data-u16-lower / 1e9, 2), round(data-u16-upper / 1e9, 3)) $"GB"\/"sample"$ for 16-bit data; #numrange(round(data-f32-lower / 1e9, 3), round(data-f32-upper / 1e9, 3)) for 32-bit
- #num[#{ calc.round(realistic-annual-output-bytes / 1e15) }] PB of raw data per year in optimistic scenario#deixis-inline-mark(marker: "†", id: <note:data-assumption>)
// - #{data-u16-middle * 0.5 * 0.6 * samples-per-year / 1e12}
// - 16-bit, $#{ crop-rate * 100 }%$ crop
// - $#{ facility-utilisation-rate * 100 }%$ facility utilisation rate, $#{ middle-3k-fraction * 100 }%$ scanned with small detector

#deixis-endnote(id: <note:data-assumption>)[
  16-bit,
  $#{ crop-rate * 100 }%$ crop,
  $#{ facility-utilisation-rate * 100 }%$ facility utilisation rate,
  $#{ middle-3k-fraction * 100 }%$ scans with small detector.
]

Assuming a storage cost of $#estimated_DKK_per_TB_per_year "DKK"\/ ("TB" "year")$, the amortised *cost of storing 1 year's worth of data is #num(round(estimated-amortised-cost-DKK-per-year / 1e6, 2)) million DKK*. #deixis-inline-mark(marker: "‡", id: <note:storage-cost-assumption>)

#deixis-endnote(id: <note:storage-cost-assumption>)[
  Amortisation of storage over 5 years assuming fixed price.
]
This calls for compression, which must generally be lossy to exceed a compression ratio (CR) of #ratio("2:1") @ref:maroneImpactLossyCompression2020. The archival format must further be *future-proof, scalable, and supported by the scientific community*.
= Methods <sec:methods>

Three representative specimens, each as both a 16-bit unsigned-integer and a 32-bit floating-point volume
- Downscaled to $1000^3$ voxels for computational feasibility
- 106 combinations of container format and compression configurations
  - DICOM, *OME-Zarr*
  - #sc[*JPEG-LS*, *JPEG 2000*], *HTJ2K*, #sc[*JPEG XL*], LERC, ZFP, *SZ3*, SPERR, Pcodec
- Uncompressed 16-bit TIFF stacks provide baseline for comparison
- Fidelity via full-reference measures: $ℓ_∞$; *PSNR*; 3D SSIM, #sc[MS]-SSIM  @ref:wangMultiscaleStructuralSimilarity2003

= Results <sec:results>
#grid(
  columns: (1fr, 1fr),
)[
  #set par(justify: false)
  - *High CR at modest quality loss*
  - Transform coders (#sc[JPEG XL/2000], HTJ2K) superior in PSNR
  - Error-bounded codecs (JPEG-LS, SZ3) superior in $ℓ_∞$
  - Only SZ3 supports 3D chunks
    - Moderate improvement over 2D
  - Float representation has no cost when compressed
  - _Similar performance across specimens_
  - _(#sc[MS]-)SSIM follow PSNR (not shown)_
][
#figure(
  image("assets/plots/selected_codecs_half/rd_stack_psnr_db+linf_by_specimen.svg"),
)
]

#figure(
  image("assets/plots/jpegxl_errors_z.svg", width: 100%),
)
#let d1_CR = 111.7
#let d1_SS = (1 - 1/d1_CR) * 100

For the #sc[JPEG XL] codec (`effort=7`) we observe:
- Errors  _across_ compression planes show no significant artefacts due to slicewise compression
- Perceptible loss in quality at higher compression levels ($d=5$)
- Acceptable fidelity at $d≤1$, still offers impressive performance
  - $"CR" = #d1_CR$ equivalent to *$#round(d1_SS, 3)%$ space saving*


= Findings and Conclusion <sec:findings>

DICOM is currently the only _widely_ supported container with lossy compression (#sc[JPEG 2000/LS/XL]).

Modern formats like OME-Zarr are seeing rapid adoption and improve scalability through *chunking, streaming, and multi-resolution hierarchies*.

#let s = json("summary_stats.json")
#let mu = s.metrics.compression_ratio.mean
#let sd = s.metrics.compression_ratio.std
#let summary_CR_mean = mu
#let summary_CR_std  = sd
#let summary_SS_mean = 1 - 1/mu - calc.pow(sd, 2)/calc.pow(mu, 3)
#let summary_SS_std  = sd / calc.pow(mu, 2)
As an example, #sc[JPEG XL] with $d=#s.filters.distance$ offers a space saving of #calc.round(summary_SS_mean * 100, digits: 1)% ± #calc.round(summary_SS_std * 100, digits: 1)% ($N=6, "CR" = #calc.round(summary_CR_mean, digits: 1)thin±thin#calc.round(summary_CR_std, digits: 1)$) without a significant reduction in quality.

For Natural History Museum Denmark, this conservatively corresponds to an estimated *annual cost saving of #round(estimated-amortised-cost-DKK-per-year * summary_SS_mean / 1e6, 2) million DKK* from the _NaturArv3D_ project alone.

#v(1fr)
#[
  #set text(size: size-small)
  This work was supported by the _Infrastructure for Quantitative AI-based Tomography_, QUAITOM, funded by the Novo Nordisk Foundation Data Science Programme, grant `NNF21OC0069766`.
]

// #v(1fr)
= References <sec:references>
#[
  #set text(size: 18pt)
  #set par(spacing: 0.7em, leading: 0.4em)
  #bibliography("zotero_references.bib", title: none)
]
