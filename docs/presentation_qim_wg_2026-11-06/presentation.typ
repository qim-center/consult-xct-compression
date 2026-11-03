#import "deps.typ": grayness.image-transparency
// #import "deps.typ": ccicons.cc-by-nc-nd-badge
#import "deps.typ": typsium.ce
#import "deps.typ": semantrix.vv
#import "deps.typ": codly, codly-languages.codly-languages
#import "deps.typ": dtree.dtree
#import "deps.typ": unify, zero
#import unify: add-unit, num, numrange, qty, qtyrange, unit
#import zero: num as znum, quan
#import "tableaux.typ" as tableaux

// Slides
#import "deps.typ": dutten.slides, fletcher
#import fletcher: edge, node
#import slides: progress-marker-both, progress-marker-lower, progress-marker-upper, touying
#import touying: *

#import "qim.typ"
#import "utils.typ": *

#show: codly.lang-set_(languages: codly-languages)
#let fletcher-diagram = touying-reducer.with(reduce: fletcher.diagram, cover: fletcher.hide)

#let title = "NaturArv3D and Compression Strategies"
#set document(
  date: datetime(year: 2026, month: 10, day: 28),
  author: "Jeppe Klitgaard",
  title: title,
)

#let footers = (
  utils.display-info-date,
  self => self.info.title,
  context [#utils.slide-counter.display() / #utils.last-slide-number],
)
#show: slides.theme.with(
  title: title,
  subtitle: [NaturArv3D and Compression Strategies],
  author: context document.author,
  date: context document.date.display(),
  institution: [Center for Quantification of Imaging Data from MAX IV],
  footers: footers,
  footer-style: "thick",
  color: qim.red,
  background-color: white,
  logo: image-transparency(read(qim.logo, encoding: none), width: 2.5cm, alpha: 50%),
  config-common(show-bibliography-as-footnote: true, enable-pdfpc: true),
  pympress: true,
  pympress-prioritise-sys-inputs: true,
)

#set text(size: 20pt, font: ("Liberation Sans", "Noto Emoji"))
// #set text(size: 20pt, font: ("Liberation Sans", "Noto Color Emoji", "Noto Emoji"))
#show figure.caption: set text(size: 16pt)
#set highlight(extent: 2pt, fill: gray.transparentize(70%), radius: 3pt)
#show raw: highlight
#show link: set text(fill: navy.lighten(20%))
#show link: it => {
  if it.body == it.dest {
    set text(fill: navy.lighten(20%))
  }
  it
}
#show link: underline.with(offset: 2.5pt)
#show footnote.entry: set text(size: 10pt)
#set footnote.entry(gap: 4pt, clearance: 2pt)
// Footnote entry numbers as plain "[1]" rather than superscript
#show footnote.entry: it => {
  show super: s => s.body + h(0.3em)
  it
}

#let skip = body => {
  set text(fill: black.transparentize(50%))
  body
}

=

#align(center)[
  #set text(size: 36pt, weight: "bold")
  #title

  #set text(size: 24pt, weight: "regular")
  Qim Working Group\
  #context document.date.display()
  #v(3cm)
  Jeppe Klitgaard\
  #[
    #set text(size: 0.7em)
    #link("mailto:s250250@dtu.dk")
  ]
]

== Outline <outline>
#speaker-note[
- NaturArv3D: Why storage is a problem
]

- Brief introduction to NaturArv3D Project
  - Estimated data size and cost

- Format considerations

- Compression
  - Lossless
  - Lossy

== Poster at D3A 4.0
#cols(columns: (1fr, auto))[
- Presented this work at D3A 4.0 conference recently

  - Compression of XCT volumes

  - Within context of NaturArv3D project
][
  #image("assets/poster.png")
]

== NaturArv3D
Joint project between Natural History Museum Denmark (NHMD) and 3D Imaging Centre (3DIM)

New X-ray scanner and infrastructure:
- *High throughput*: 500 samples/week (≈15 min per sample)
- *High resolution*: resolution below 10 μm, 3K – 5.6K images
- Samples prepared in cardboard boxes
- *Autonomous sample handling* using robot mounted in ceiling gantry

Purpose: Digitize large specimen collections
- Pilot: Seal skulls, vertebrate collection

#pb

#figure(
  image("assets/flow_storage.svg"),
  caption: none,
)


== Data Size Matters
#speaker-note[
  Go fast over these
]

// How many projections per image???
// #let proj_gb_per_small_16u = 3072 * 3072 * 16 / 8 / calc.pow(10, 9)
// #let proj_gb_per_big_16u = 5606 * 4800 * 16 / 8 / calc.pow(10, 9)
#let vol_gb_per_small_f32 = 3072 * 3072 * 3072 * 32 / 8 / calc.pow(10, 9)
#let vol_gb_per_big_f32 = 5606 * 4800 * 5606 * 32 / 8 / calc.pow(10, 9)
Problem: Data is (very) large!
#skip[
- Projections: not sure, likely fairly undersampled (15 minutes per sample!)
  - Most people wouldn't save these anyway
]

- Small detector: $3072×3072$ pixels
  - Reconstruction, 32-bit float: #calc.round(vol_gb_per_small_f32) GB per sample

- Big detector: $5606×4800$ pixels
  - Reconstruction, 32-bit float: #calc.round(vol_gb_per_big_f32) GB per sample

#pause
#let samples_per_year = 500 / 7 * 365.2425
#let vol_mixed_use_tb_per_year_f32 = (samples_per_year / 2) * (vol_gb_per_small_f32 + vol_gb_per_big_f32) / 1000
Assume 50/50% small/big detector usage, 500 samples/week:
  - Recons: #calc.round(vol_mixed_use_tb_per_year_f32 ) TB per year (!!)

#pause
#let dkk_per_tb_per_year = 600
#let years_stored = 5
Assume storage cost of #dkk_per_tb_per_year DKK / (TB yr)
- Assume data must be stored for 5 years: #calc.round(vol_mixed_use_tb_per_year_f32 * years_stored * dkk_per_tb_per_year / calc.pow(10, 6), digits: 1) MDKK / yr

#pause
#v(1fr)
#align(center)[
  🌀 _Money clearly better spent giving Jeppe salary bump_ 🌀
]
#v(1fr)

== Low-hanging fruit
+ 50/50% mix, 500 samples/week, f32, no crop:
  - #calc.round(vol_mixed_use_tb_per_year_f32 ) TB / yr (#calc.round(dkk_per_tb_per_year * years_stored * vol_mixed_use_tb_per_year_f32 / calc.pow(10, 6), digits: 1) MDKK / yr)

#let vol_mixed_use_tb_per_year_u16 = vol_mixed_use_tb_per_year_f32 / 2
+ 16-bit representation:
  - #calc.round(vol_mixed_use_tb_per_year_u16) TB / yr (#calc.round(dkk_per_tb_per_year * years_stored * vol_mixed_use_tb_per_year_u16 / calc.pow(10, 6), digits: 1) MDKK / yr)

#let vol_mixed_use_tb_per_year_u16_cropped = vol_mixed_use_tb_per_year_u16 * 0.5
#let cost_vol_mixed_use_per_year_u16_cropped = dkk_per_tb_per_year * years_stored * vol_mixed_use_tb_per_year_u16_cropped
+ Crop 50% of volume:
  - #calc.round(vol_mixed_use_tb_per_year_u16_cropped) TB / yr (#calc.round(cost_vol_mixed_use_per_year_u16_cropped / calc.pow(10, 6), digits: 1) MDKK / yr)

#let vol_mixed_use_tb_per_year_u16_cropped_utility_rated = vol_mixed_use_tb_per_year_u16_cropped * 0.5
#let cost_vol_mixed_use_per_year_u16_cropped_utility_rated = dkk_per_tb_per_year * years_stored * vol_mixed_use_tb_per_year_u16_cropped_utility_rated
+ Maybe actually scanner utilisation is only 250 samples / week (50%):
  - #calc.round(vol_mixed_use_tb_per_year_u16_cropped_utility_rated) TB / yr (#calc.round(cost_vol_mixed_use_per_year_u16_cropped_utility_rated / calc.pow(10, 6), digits: 1) MDKK / yr)

#v(1fr)
#let price_yatai_padak = 78
#let dkk_per_usd = 6.66
#let anthropic_loss_per_half_year_usd = 80.7 * calc.pow(10, 9)
#let anthropic_loss_per_half_year_dkk = anthropic_loss_per_half_year_usd * dkk_per_usd
#let anthropic_loss_per_day_dkk = anthropic_loss_per_half_year_dkk / (365.2425 / 2)
#let anthropic_loss_per_second_dkk = anthropic_loss_per_day_dkk / (24 * 60 * 60)
#let cost_vol_mixed_use_anthropic_seconds = cost_vol_mixed_use_per_year_u16_cropped_utility_rated / anthropic_loss_per_second_dkk

// #anthropic_loss_per_day_dkk

// #anthropic_loss_per_second_dkk

// #cost_vol_mixed_use_anthropic_seconds

#align(center)[
  #alternatives[

  ][
  _*That is still an awful lot of data/money!*_\
  #calc.round(cost_vol_mixed_use_per_year_u16_cropped_utility_rated / price_yatai_padak) Yatai Padaks per year (without discount)!
  ][
  1 minute and #calc.round(cost_vol_mixed_use_anthropic_seconds - 60) seconds of Anthropic net loss 2026-H1\
  _*That is really not that much money!*_
  ]
]
#v(1fr)

== Going Further
#let jeppe_salary_dkk_per_month = 12853.78
#let jeppe_work_pension = 2/3 * 0.1668 * jeppe_salary_dkk_per_month
#let jeppe_work_insurance = 108.35
#let jeppe_cost_per_year_dkk = 12 * (jeppe_salary_dkk_per_month + jeppe_work_pension + jeppe_work_insurance)
#let cost_per_sample_vol_mixed_use_tb_per_year_u16_cropped = cost_vol_mixed_use_per_year_u16_cropped / samples_per_year
#let jeppe_cost_per_year_samples = jeppe_cost_per_year_dkk / cost_per_sample_vol_mixed_use_tb_per_year_u16_cropped

How to get around this?
- Reduce bit depth further: 16-bit ⟶ 8-bit
  - Saves 50% of cost, but *99.6% reduction in bit depth*!

#pause

- Downsample images?

- Crop more?

- Use big detector less?

- Just scan fewer samples?

#pause

#alternatives[
- _Fire Jeppe, he costs #calc.round(jeppe_cost_per_year_samples) (cropped) samples per year!_
][
- #strike[_Fire Jeppe, he costs #calc.round(jeppe_cost_per_year_samples) (cropped) samples per year!_]
][
#v(1fr)
#align(center)[
  💡 _*What about compression?*_ 💡
]
#v(1fr)
]

== Compression

#figure(
  image("assets/flow.svg"),
  caption: none,
)

// == Criteria
#pb
#speaker-note[
  Skip slide
]
#skip[
- Criteria
  - Ideally lossless, otherwise as little quality loss as possible
  - Decompression speed must not be bottleneck
  - Format must be suitable for archival and research
    - Wide software support
    - Format stable over time
  - Format should support metadata (voxel size, etc)
  - Worthwhile compression ratio
]

- Dataset
  - 3 volumes of seal skulls, downsampled to 1K
  - Both `uint16` and `float32` versions tried
== Formats
#[
  #let evaler(x, row, col, ..args) = {
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

    if (col != 0 and row in (20, 21, 22)) or (row != 0 and col in (9, 10)) {
      set text(size: 7pt)
      eval(eval-str, scope: scope, mode: "markup")
    } else {
      eval(eval-str, scope: scope, mode: "markup")
    }
  }
  #let format-support-data = (
    csv("assets/format_support.csv")
      .enumerate()
      .map(((i, row)) => row.enumerate().map(((j, cell)) => evaler(cell, i, j, mode: "markup")))
  )
  #[

    #set text(size: 9pt)
    #show "Yes": set text(fill: std.olive)
    #show "No": set text(fill: std.red)

    #figure(
      tableaux.ez-table(
        format-support-data,
        inset: 3pt,
        header-transform: it => {
          std.strong(text(it, fill: black)) // To unset bold style from theme
        },
        fill: (x, y) => if calc.rem(y, 2) == 0 { black.transparentize(90%) },
      ),
      caption: none,
    ) <tbl:encodings>
  ]
]

#pb
#speaker-note[
  Skip details
]
- TIFF
  - Extremely common, almost always without compression
  - Supports many codecs through _extensions_
    - Almost no software support in practice

- DICOM
  - Widely supported, popular in medical field
  - Natively supports JPEG 2000, HTJ2K, JPEG-LS, (JPEG XL)
  - Cumbersome format to deal with, 3DIM strongly dislikes

- Bitmap stacks
  - Stacks of PNG, JPEG, JPEG 2000, ...
  - Either low bit-depth or not widely supported

#pb
#speaker-note[
- Aside:
  - Curse of dimensionality:
    - 4K HDR TV at home: Fine
    - 4K 16-bit volume at work: Decidedly not fine!
]
- Conclusion:
  - DICOM is the only widely supported format supporting lossy compression!
  - #skip[(with $>8$ bit depth)]

- Generally lossy required to exceed $"CR"≈#ratio[2:1]$ @ref:maroneImpactLossyCompression2020 @ref:wegenerRealtimeCompressionRaw2009

#alternatives[
Leaves us with 3 options:
+ Wide support + low/no compression: TIFF stacks
+ Wide support + lossy compression: DICOM
+ Limited support + lossy compression: Free to choose modern format
][
Leaves us with #strike[3] #alert[2] options:
+ #strike[Wide support + low/no compression: TIFF stacks] #alert[Can't afford]
+ Wide support + lossy compression: DICOM
+ Limited support + lossy compression: Free to choose modern format
][
Leaves us with #strike[3] #alert[1] option:
+ #strike[Wide support + low/no compression: TIFF stacks] #alert[Can't afford]
+ #strike[Wide support + lossy compression: DICOM] #alert[3DIM says no] (cumbersome)
+ Limited support + lossy compression: Free to choose modern format
][
Leaves us with #strike[3] #alert[1] option:
+ #strike[Wide support + low/no compression: TIFF stacks] #alert[Can't afford]
+ #strike[Wide support + lossy compression: DICOM] #alert[3DIM says no] (cumbersome)
+ Limited support + lossy compression: Free to choose modern format
#v(1fr)
#align(center)[
  #alert[OME-Zarr]\
  (or other NGFF)
]
#v(1fr)
]


// #boxed[
// #alert[Aside]: For these matrix and data sizes, advanced formats required anyway?
// - _Curse of dimensionality_
// - Multiscale required for interactive use
// - Streaming and chunking required to avoid memory and IO bottlenecks
// ]
#pb
- OME-Zarr
  - #red[Sparse software support], but #green[rapidly improving] (FOSS especially)
  - #green[Excellent support in Python] (and Rust)
  - #green[Advanced features]
    #alternatives[
    - #green[chunking, sharding]
    - #green[multiscale]
    ][
    #brace-right[
    - #green[chunking, sharding]
    - #green[multiscale]
    ][Important for large datasets]
    ]
    - #green[streaming]
    - #green[metadata]
  - Comes from microscopy community, #red[some features not relevant]

== Lossless compression
#cols(columns: (1fr, auto))[
- JPEG codecs perform well, #skip[including JPEG XL]
  #skip[
  - Very recent format
    - Adopted by browsers in last 2 months
    - Next PDF standard, latest DICOM spec. @ref:DICOM-ps3.5-2026c
  ]
- Generally
][
  #image("assets/lossless_plot_tall_uint16.svg", height: 90%)
]

== Lossy compression
- For our $2×3$ seal skull datasets try a bunch of different codecs in *DICOM* and *OME-Zarr*
  - JPEG-LS, JPEG 2000, HTJ2K, JPEG XL, LERC, ZFP, SZ3, SPERR
- Compute full-reference measures against original data
  - $ℓ_∞$, PSNR, 3D SSIM, MS-SSIM

#pb
#cols(columns: (1fr, 1fr))[
- *Large CR with relatively modest quality loss!*
  - SZ3: $ℓ_∞ < 10^(-2)$ gives $"CR">100$

- Transform coders superior in PSNR
  - JPEG XL, JPEG 2000, HTJ2K

- Error bounded codecs superior in $ℓ_∞$
  - JPEG-LS, SZ3

- `f32` representation is 'free' (see JPEG XL)

- SZ3 performs _a bit_ better in 3D than in 2D
  - ⇒ 2D codecs don't leave that much on table
][
  #image("assets/rd_stack_psnr_db+linf_by_specimen.svg")
]

#pb
#speaker-note[
Sample: CZM 712
  - Note: samples compress differently, so CR with grain of salt

JPEG XL compresses in 2D, errors _across_ compression slices

These are for increasing 'distances' -> right
- $d=0.1$: almost no visible artefacts
- $d=1.0$: Artefacts just imperceptible: $"CR"=117.1$!
- $d=5.0$: Visible artefacts, pores smoothed out
]
#figure(
  image("assets/jpegxl_errors_x.svg"),
  caption: [
    Compression artefacts from JPEG XL (2D) compression of 3D volume (CZM 712) _across_ compression slices for different quality settings.
  ]
)

#pb
- As an example, JPEG XL with $d=0.5$

- No perceptible errors (abundance of caution)

- For dataset $N=6$ gives $"CR"=62.4 ± 16.3$

- *$⇒ 98.3% ± 0.4%$ space savings!*

#pause
#let ss = 0.983
#v(1fr)
#align(center)[
#alert[
  #set text(size: 1.5em)
$#calc.round(cost_vol_mixed_use_per_year_u16_cropped_utility_rated / calc.pow(10, 6), digits: 1) "MDKK" → #znum[#calc.round(cost_vol_mixed_use_per_year_u16_cropped_utility_rated * (1-ss) / calc.pow(10, 0), digits: 0)] "DKK"$
]
]
#v(1fr)
Caveat: for the datasets provided by museum
- Seems to compress better than CIL reconstructed wolf skulls; lossless CR ≈ 2.8!

= NaturArv3D Considerations
- Support for most codecs not yet standardised in Zarr (ongoing work)
  #skip[
  - Without standardisation: ecosystem split between Python and Rust implementations
  ]

- Most software doesn't support OME-Zarr yet
  - Workaround: use Zarr streaming + local tool
  - Stream Zarr but split out TIFF stacks locally
    - Compressed during transfer
    - Can access specific slices or resolutions
  - Currently trying to get this into `py-ome-zarr`
    - Open PRs, ongoing work

#pb
#image("assets/flow_data_v2.svg")
- Store in modern, compressed format
- Streaming export to TIFF stack (supporting older tools)
- Streaming to modern tools

= Future Work
- When first data + infrastructure for scanner becomes available:
  - Pick specific codec and parameters

- Consider evaluating some task-specific metrics
  - Segmentation accuracy, etc

- Similar study is pursued by Human Organ Atlas (HOA)
  - Suraj Pathak (HOA, UCL) attended hackathon last week and discussed this
  - They have similar problems and interests
  - Potentially some future collaboration

== Questions?

== Bibliography
#bibliography("references.bib", title: none)

== Meta
- Slides and source code available at: TODO

- Study on compression strategies available:
  - #link("https://github.com/qim-center/consult-xct-compression/", "github.com/qim-center/consult-xct-compression")
