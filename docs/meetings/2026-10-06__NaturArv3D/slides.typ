#import "@preview/touying:0.8.0": *
#import "@preview/grayness:0.7.0": image-transparency
#import "@preview/unify:0.8.1": add-unit, num, numrange, qty, qtyrange, unit
#import "@preview/zero:0.7.0": num as znum, quan
#import "@preview/suboutline:0.3.0": suboutline
#import "@preview/mmdr:0.2.2": mermaid
#import "@local/dutten-slides:0.1.0": dutten-theme, progress-marker-both, progress-marker-lower, progress-marker-upper

#set document(
  date: datetime(year: 2026, month: 10, day: 06),
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
  subtitle: [Data Pipeline],
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

== Introduction to `ome_zarr` CLI concept
- Have made PRs to `ome-zarr-py` repo, $2\/4$ merged
  - TIFF stack export command: #link("https://github.com/ome/ome-zarr-py/pull/678", `ome-zarr-py#678`)
  - Built-in support for `imagecodecs` codecs: #link("https://github.com/ome/ome-zarr-py/pull/679", `ome-zarr-py#679`)
  - Even if not merged: shows how easily conversion tool can be made and maintained
- Reminder, importantly: many codecs are still not _standardised_ in Zarr 3
  - No standardised lossy codecs as of 2026-10-06
  - Current proposal relies on one specific codec implementation (`imagecodecs`)
  - Upgrade path to standardised codec is expected, but not guaranteed
  - Proposed JPEG XL Extension Specification: #link("https://github.com/zarr-developers/zarr-extensions/pull/70", `zarr-extensions#70`)

Alternatives remain:
- DICOM with JPEG-LS or JPEG 2000 compression
- Uncompressed (perhaps losslessly compressed) TIFF stack

== Demo `ome_zarr` CLI
+ Install #link("https://docs.astral.sh/uv/getting-started/installation/", `uv`):
  - #skip[
      #set text(size: 12pt)
      _Some Python people may already have it installed_
      - _≈ 30% market share in October 2025: caveats apply, see #link("https://wagtail.org/blog/uv-overtakes-pip-in-ci/", "source")._
      - _90.4K stars on GitHub (2026-10-05)_
    ]
  - Windows: `winget install --id=astral-sh.uv  -e`
  - Linux/MacOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
+ Install `ome-zarr-py` CLI:
  - `uv tool install --with imagecodecs-zarr git+https://github.com/JeppeKlitgaard/ome-zarr-py@feat-cli-convert`
+ Stream OME-Zarr and convert to TIFF stack (here we pick second level):
  - `ome_zarr export --format tiff-stack --level 2 --overwrite LINK_OR_LOC_OF_OME_ZARR output_tiffs`
  - #skip[
      Example:
      - #[
          #set text(size: 10pt)
          `ome_zarr export --format tiff-stack --level 2 --overwrite "https://s3.g.s4.mega.io/aidjqnzhivz2k6kyxukiymjgfb4wxowhengdp/naturarv3d/CIL_basic_binned_2x2/NaturArv3D_format_viability_study/OME-Zarr/Canislupus_CZM_712__jpegxl_l_0_5__scales_2_4_8_16.ome.zarr" output_tiffs`]
    ]
+ _Optional: Open in Napari (`uvx --with pyqt6 napari output_tiffs`)_

#pagebreak(weak: true)
#align(center + horizon, strong[
  #set text(size: 60pt, fill: black)
  Tool Demo
])

== Notes on tool
- Nice:
  - Streams in compressed format, so network friendly
  - Streams, so memory friendly
  - Emits standard TIFF stack
  - Preserves voxel size metadata

- Just a prototype
  - Intended to prove feasibility
  - Could just as well be a little graphical interface, or both

== Data Flow Chart
- Very rough flow chart of data pipeline
- Mostly just included for later reference
  - _Exact timing of conversions and where compression happens is still TBD_.
  - Right-most half may be instructive

#image("flow.png", height: 1fr)



== Summary
- Initially thought mostly about codecs
- Container format turned out to be more important
- May need to revisit codec when we get closer to implementation stage
- Don't have to make decision now?

== Aside: Poster at D3A 4.0 Conference (October 8 – 9)
#cols[
  - Bit last minute, _apologies_
  - Hopefully will be engaging to people
  - Non-finished version to the right
    - _(due to monotonicity of time)_
#image("flow_poster.svg", height: 1fr)
][#align(right)[
    #image("poster.png")
  ]
]

== Closing Remarks
- _Everything (?)_ available on private GitHub repo under `qim-center` org
  - #link("https://github.com/qim-center/consult-xct-compression")
    - QIM + Close friends already have access
    - Others can ask for inclusion
  - Slides and source code for every meeting presentation
  - Source code and outputs for all experiments and demos
    - Note: Obviously no volumetric data included
  - Poster including source code
  - Unfinished report that has been abandoned
