#import "@preview/touying:0.7.4": *
#import "@preview/grayness:0.7.0": image-transparency
#import "@preview/unify:0.8.1": add-unit, num, numrange, qty, qtyrange, unit
#import "@preview/zero:0.7.0": num as znum, quan
#import "@preview/suboutline:0.3.0": suboutline
#import "@local/dutten-slides:0.1.0": dutten-theme, progress-marker-both, progress-marker-lower, progress-marker-upper
#import "tableaux.typ" as tableaux
#import calc: *

#set document(
  date: datetime(year: 2026, month: 09, day: 27),
  author: "Jeppe Klitgaard",
  title: "Data Pipeline",
)

#let footers = (
  utils.display-info-date,
  self => [#self.info.title – #self.info.subtitle],
  context [#utils.slide-counter.display() / #utils.last-slide-number],
)
#show: dutten-theme.with(
  title: [NaturArv3D],
  subtitle: context document.title,
  author: context document.author,
  date: context document.date.display(),
  institution: [Center for Quantification of Imaging Data from MAX IV],
  footers: footers,
  footer-style: "thick",
  // color: rgb(252, 115, 35),  // QIM Orange
  color: rgb(230, 63, 71), // QIM Red
  background-color: rgb(248, 249, 250), // QIM Background
  logo: image-transparency(read("qim_logo.png", encoding: none), width: 2.5cm, alpha: 50%),
)

#set text(size: 20pt)
#show figure.caption: set text(size: 16pt)
#show raw: it => highlight(it, extent: 2pt, fill: gray.transparentize(70%), radius: 3pt)
#show link: set text(fill: navy.lighten(20%))
#show link: it => {
  if it.body == it.dest {
    set text(fill: navy.lighten(20%))
  }
  it
}
#show link: underline.with(offset: 1.5pt)
#show footnote.entry: set text(size: 10pt)
#set footnote.entry(gap: 4pt, clearance: 2pt)

#let skip = body => {
  set text(fill: black.transparentize(50%))
  body
}

= <study>

#align(center)[
  #set text(size: 36pt, weight: "bold")
  NaturArv3D Data Pipeline

  #set text(size: 24pt, weight: "regular")
  Meeting #context document.date.display()
  #v(5cm)
  Jeppe Klitgaard\
  #[
    #set text(size: 0.7em)
    #link("mailto:s250250@dtu.dk")
  ]
]

== Outline <outline>
#outline(
  title: none,
  target: heading.where(outlined: true).after(<outline>, inclusive: false),
  depth: 2,
  indent: n => 1.2em * calc.max(0, n - 1),
)

== Introduction
- Compression study somewhat on hold
  - Until more details hashed out
  - Format requirements, data size expectations
- Very helpful input from SNM — _many thanks Mark, Christy, Thomas, Joni!_

== Format Support
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
    csv("format_support.csv")
      .enumerate()
      .map(((i, row)) => row.enumerate().map(((j, cell)) => evaler(cell, i, j, mode: "markup")))
  )
  #[

    #set text(size: 9pt)
    #show "Yes": set text(fill: olive)
    #show "No": set text(fill: red)

    #figure(
      tableaux.ez-table(
        format-support-data,
        inset: 3pt,
        header-transform: it => {
          std.strong(text(it, fill: black)) // To unset bold style from theme
        },
        fill: (x, y) => if calc.rem(y, 2) == 0 { black.transparentize(90%) },
      ),
    ) <tbl:encodings>
  ]
]
#progress-marker-lower

== Software Support: Summary
- Not widespread support for formats modern formats
  - Wonder how good support would actually be for a 256GB TIFF stack in practice?
- Large datasets have been rare, but is changing
- DICOM format very promising
  - Supports JPEG-LS, JPEG-2000
  - Only widely supported format with lossy compression
  - Even supports JPEG-XL as of 2025
    - Likely implementors do not yet comply
    - Can beat implementors over the head if they state DICOM support
  - Have been very impressed with JPEG-XL
    - Mayo: 50-60% size reductions over existing lossy compressions with no visual difference#footnote(link("https://www.dicomstandard.org/news-dir/current/docs/sups/sup232-slides.pdf"))
- Opinion: #strike("Insane") Silly to reduce bit-depth to 8-bit but not use (lossy) compression

== Example: Czeibart, UHR Skulls
Kalman Czeibart, 430 skull CT scans (Christy)
- Source: https://nc.elte.hu/s/doZnwPjgeBaZ7as
- NifTI, gzip, `int16`, $≈500 × 500 × 1000$
- Sample `001_A_AIRT`: 142MB compressed, 234M uncompressed
  - $"CR" = 1.65$, $"SS" = 39%$
- 430 samples = 47.9GB compressed
- Wide software support

*If we have similar size, no need to bother with lossy or non-standard compression!*

== Examples: Beamlines
- EMBL/DESY P14 beamline: TIFF/OME-Zarr/WEBKNOSSOS, see #link("https://www.embl.org/groups/x-ray-imaging/after-your-beamtime/#vf-tabs__section-data_format_and_access", "here")
- MAX IV: HDF5
- Most beamlines store data uncompressed/losslessy compressed
  - Those that have switched to Zarr likely use Blosc (lossless)

*Even beamlines with huge data storage requirements have not yet adopted lossy compression widely.*

*But note*: they have switched to chunked storage formats, likely out of necessity!

== MorphoSource
- Samples in their CT collections seem to be mostly in 50MB – 2GB range
- Supports formats: TIFF, JPEG-1, BMP, DICOM#footnote(link("https://duke.atlassian.net/wiki/spaces/MD/pages/35422892/Critical+Formatting+Details"))
  - Not even NifTI support
- Institutions with deposits over 1TB expected to pay
  - Fee is 3.47 USD/GB + 30 USD flat fee#footnote(link("https://duke.atlassian.net/wiki/spaces/MD/pages/274268722/Data+Deposit+Costs"))
- *Question*: _Is this the intended/expected/desired storage solution for NaturArv3D?_

== Size Considerations
- Detectors:
  - Large samples: Spectrumlogic, $5606 × 4800 "px"$, pixel size #qty("50", "um")
  - Smaller samples: Varex, $3072×3072 "px"$, pixel size #qty("139", "um")
- _Optimistic_ canonical volume: $3072^3 "vx" = #znum(pow(3072, 3) / pow(10, 9), digits: 1) "Gvx"$ (assuming 16-bit)
- Assume 50% (?) crop as an average: $#znum(pow(3072, 3) / pow(10, 9) * 0.5, digits: 1) "Gvx"$
  - 16-bit: #qty("28.8", "GB") uncompressed

Cloud storage cost: Backblaze B2 Object Storage#footnote[#link("https://www.backblaze.com/cloud-storage/pricing"), accessed 2026-08-26]:
- Includes 300% monthly egress (data can be downloaded 3 times per month for before additional fees)
- Price is for 5 years of redundant, 'active archive' storage
- $83 "USD" \/ "TB" \/ "year" quad ⇒ quad 0.415 "USD" \/ "GB" (2.65 "DKK")$
  - Significantly cheaper than MorphoSource, though this is only for 5 years

== Size Consideration Table
#progress-marker-lower
#let sizes = (
  (
    name: [Czeibart],
    shape: (500, 500, 1000),
    crop: 0.0,
    bitdepth: 16,
  ),
  (
    name: [$2^3 ×$ Czeibart],
    shape: (1000, 1000, 2000),
    crop: 0.0,
    bitdepth: 16,
  ),
  (
    name: [*Small Detector*],
    shape: (3072, 3072, 3072),
    crop: 0.5,
    bitdepth: 16,
  ),
  (
    name: [Large Detector],
    shape: (5606, 5606, 4800),
    crop: 0.5,
    bitdepth: 16,
  ),
)

#let compressions = (
  (
    name: [Uncompressed],
    ratio: 1.0,
  ),
  (
    name: [*Lossless*],
    ratio: 1.7,
  ),
  (
    name: [Lossy],
    ratio: 25.0,
  ),
  (
    name: [*Lossy*],
    ratio: 50.0,
  ),
  (
    name: [Lossy],
    ratio: 100.0,
  ),
)

#let num_to_human_si(bytes, unit: "", unit-transform: x => x, ..num-args) = {
  let factors = (
    "P": pow(10, 15),
    "T": pow(10, 12),
    "G": pow(10, 9),
    "M": pow(10, 6),
    "k": pow(10, 3),
    "": pow(10, 0),
    "m": pow(10, -3),
    "μ": pow(10, -6),
    "n": pow(10, -9),
    "p": pow(10, -12),
  )

  for (prefix, factor) in factors {
    if bytes >= factor {
      let value = bytes / factor
      let unit = prefix + unit
      let transformed-unit = unit-transform(unit)
      return [#znum(value, ..num-args) #transformed-unit]
    }
  }
}

#let entries = {
  let out_rows = ()
  for compression in compressions {
    let out_cells = ()
    for size in sizes {
      let uncompressed = size.shape.at(0) * size.shape.at(1) * size.shape.at(2) * (size.bitdepth / 8) * (1 - size.crop)
      let compressed = uncompressed / compression.ratio
      let compressed_GB = compressed / pow(10, 9)
      let morphsource_USD_per_GB = 3.47
      let DKK_per_USD = 6.39
      let backblaze_B2_USD_per_GB_per_year = 83.0 / 1000

      let ms_ratio = pow(10, -9) * morphsource_USD_per_GB * DKK_per_USD
      let bb_ratio = pow(10, -9) * backblaze_B2_USD_per_GB_per_year * DKK_per_USD * 5
      let week_coeff = 500
      let year_coeff = 500 / 7 * 365.2425

      let num-disp = num_to_human_si.with(round: (precision: 3, mode: "figures"))

      out_cells.push([
        #set text(size: 12pt)
        #grid(
          columns: (1fr, 1fr, 1fr),
          align: (left, left, left),
          inset: 4pt,
          stroke: (x, y) => {
            let out = (:)
            if x in (1,) { out += (x: (thickness: 0.7pt, dash: "dotted")) }
            if y in (1,) { out += (y: (thickness: 0.7pt, dash: "dotted")) }
            out
          },
          fill: (x, y) => if x == 1 { black.transparentize(95%) },

          num-disp(compressed, unit: "B"),
          num-disp(compressed * 500, unit: "B"),
          num-disp(compressed * (500 / 7 * 365.2425), unit: "B"),

          num-disp(compressed * ms_ratio, unit: "kr"),
          num-disp(compressed * week_coeff * ms_ratio, unit: "kr"),
          num-disp(compressed * year_coeff * ms_ratio, unit: "kr"),

          num-disp(compressed * bb_ratio, unit: "kr"),
          num-disp(compressed * week_coeff * bb_ratio, unit: "kr"),
          num-disp(compressed * year_coeff * bb_ratio, unit: "kr"),
        )
      ])
    }

    out_rows.push(out_cells)
  }
  out_rows
}

#let sizes-header = ()
#for size in sizes {
  sizes-header.push([
    #emph(size.name)\
    $#size.shape.map(str).join("×")$\
    #{ size.crop * 100 }% crop #h(1cm) #{ size.bitdepth }-bit\

  ])
}

#let compressions-header = ()
#for compression in compressions {
  compressions-header.push([
    #compression.name\
    $"CR"=#compression.ratio$\
    $"SS"=#znum((1 - 1 / compression.ratio) * 100, digits: 2)%$
  ])
}

#let diagonal(body-r, body-l, width: auto, height: auto) = {
  box(
    width: width,
    height: height,
  )[
    #place(top + right, body-r)
    #place(bottom + left, body-l)
    #line(start: (0%, 0%), end: (100%, 100%), stroke: 0.5pt)
  ]
}

#[
  #set text(size: 12pt)
  #table(
    columns: (3.0cm, ..(1fr,) * sizes.len()),
    align: center,
    table.header(diagonal(width: auto)[*Data*][*Scheme*], ..sizes-header),
    ..compressions-header
      .zip(entries)
      .map(((header, row)) => (header, ..row.map(x => table.cell(x, inset: 0pt))))
      .flatten(),
  )
]
#[
  #set text(size: 14pt)
  - Cell rows: data size, storage cost (MorphSource), storage cost (Backblaze B2)
  - Cell columns: 1 recon., 1 week of recons. (shaded, 500), 1 year of recons. (26089)
  - Units have been SI-ified: mkr = milli-kroner, Mkr = mega-kroner/million, etc.
]

== Potential Storage Solutions
- Lowest Common Denominator
  - Appears to be uncompressed TIFF/DICOM/JPEG-1/PNG
  - Note: Likely that many of them don't support JPEG-XL in DICOM yet?
- Zarr + Objects (+ Local Conversion)
  - Build or find small tool that can convert Zarr from object storage to TIFF locally
- A Reasonably Common Denominator
  - HDF5 (like MAX IV and others, likely still spotty codec support)
- Zarr/OME-Zarr/TIFF/... + REST API
- ...?

== The Case for Zarr
- Zarr has seen rapid adoption
  - NASA is commited — #link("https://github.com/NASA-IMPACT/veda-odd", "VEDA/ODD team")
  - OME-Zarr is #link("https://ngff.openmicroscopy.org/index.html", "leading NGFF (Next Generation File Format)") selected by OME
  - EMBL is adopter (DESY beamlines, #link("https://idr.openmicroscopy.org/", "Image Data Resource (IDR)"))
  - Janelia is adopter (#link("https://openorganelle.janelia.org/", "OpenOrganelle"), other projects)
  - \+ Many other prestigious and important institutions
- Zarr is vastly technologically superior to legacy formats
  - Access: Chunking, parallel access, multi-dimensional, cloud friendly (object storage)
  - Efficiency: *Codecs*, streaming/async, performant
  - Open: *Open standard, open governance*, highly interoperable
- Opinion: *Zarr/OME-Zarr is the correct long-term solution*
  - _May not be acceptable here due to legacy software support and data repository requirements_

== Extra: JPEG-XL Lossy from Last Meeting

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
  - Demonstrates how good lossy compression is
    - mostly for SNM's benefit
][
  #figure(image("2026-08-11_jpegxl_quality_comparison.png"))
]
