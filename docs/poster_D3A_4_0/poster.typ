#import "@local/dutten-poster:0.1.0": template
#import "@local/dutten:0.1.0": poster
#import "@local/jutils:0.1.0"
#import "attribution.typ": authors
#import "deps.typ": (
  dutten.colors-rgb, dutten.get-logo, dutten.poster, jutils.author.render-authors, jutils.author.render-corresponding,
  jutils.author.render-affiliations, jutils.recolor-svg, tiaoma.qrcode, jutils.author.get-corresponding, tiaoma
)
#import "constants.typ": front-color, primary-color, qim-grey
#import "viz.typ": swoosh

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
        columns: (auto, 1fr, auto, 10mm, auto, 10mm, auto, 1fr, auto, 16mm, auto),
        align: horizon,

        recolor-svg(path("assets/snm_logo.svg"), snm-color, height: 100%),
        none,
        recolor-svg(path("assets/qim_logo.svg"), qim-color, height: 90%),
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
          #set text(font: "Neo Sans Pro", fill: dtu-color)
          #set par(leading: 0.50em, spacing: 0.5em)
          #set text(size: 46pt, weight: "medium")
          DTU Compute\
          #set text(size: 38pt, weight: "regular")
          #set par(leading: 0.45em)
          Department of Applied Mathematics\
          and Computer Science
        ],
      )
    ]
  ],
)


// #let footer-block = context block(
//   fill: primary-color,
//   outset: (
//     left: page.margin.left,
//     right: page.margin.right,
//     bottom: page.margin.bottom,
//   ),
//   pad(top: 10mm)[

//     #set text(fill: front-color)
//     #lorem(100)
//   ]
// )
#let footer-height = 70mm
#let footer-block = box(height: 85mm, stack(
  grid(
    columns: (auto, 100mm, 1fr),
    align: (bottom, bottom + left, bottom + right),
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
        #set text(fill: front-color, size: 20pt)
        #render-affiliations(authors, content-transform: x => x, address-transform: emph).join(linebreak())
      ]
    ),
    swoosh(footer-height), // = height of the block on the left
    stack(
      dir: ltr,
      spacing: 15mm,
      align(
        horizon,

        qrcode(
          "https://www.linkedin.com/in/jeppeklitgaard/",
          height: 50%,
          options: (
            fg-color: black.transparentize(50%),
            output-options: (
              barcode-dotty-mode: true,
            ),
            dot-size: 1.0,
          )
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
        #set text(fill: front-color, size: 22pt, weight: "semibold", font: "DejaVu Sans Mono")
        #get-corresponding(authors).at(0).email
      ]
    )
  )
))

// context block(
//   fill: primary-color,
//   outset: (
//     left: page.margin.left,
//     right: page.margin.right,
//     bottom: page.margin.bottom,
//   ),
//   pad(top: 10mm)[

//     #set text(fill: front-color)
//     #lorem(100)
//   ]
// )



#show: poster.with(
  authors: render-authors(authors).join(", "),
  header-block: header-block,
  footer-block: footer-block,
  size-title: 102pt,
  size-authors: 44pt,
)


#let sc(x, scaling: 0.85) = context [#set text(scaling * 1em, stroke: 0.01em + text.fill)
  #upper(x)]

#show "NHMD": sc[nhmd]
#show "3DIM": sc[3dim]
#show "DICOM": sc[dicom]
#show "CR": sc[cr]
#show "TIFF": sc[tiff]
#show "OME-Zarr": [#sc[ome-z]arr]
#show "JPEG": sc[jpeg]
#show "2K": sc[2k]
#show "LS": sc[ls]
#show "XL": sc[xl]
#show "PSNR": sc[psnr]
#show "SSIM": sc[ssim]
#show "MS-SSIM": sc[ms-ssim]

#let ratio(x) = {
  let (nom, denom) = x.split(":")
  [$nom#h(0.1em)∶#h(0.1em)#denom$]
}

= Introduction <sec:intro>
The _NaturArv3D_ pilot project aims to digitize the vertebrate collection at Natural History Museum Denmark (NHMD) in collaboration with the 3D Imaging Centre, Technical University of Denmark (3DIM). As necessitated by the scale of the collection, a custom high-throughput X-ray μCT scanner with a robotic sample handling system is being developed at 3DIM with a designed capacity of *500 samples per week*. Due to the high resolution of the reconstructed volumes, the project is expected to produce approximately *1 PB of data annually*, which presents significant challenges for network infrastructure and data storage that may be mitigated by data compression.

#figure(
  image("assets/flow/flow.svg", width: 100%),
  caption: [The proposed _NaturArv3D_ pipeline for high-throughput X-ray μCT of museum artefacts.],
) <fig:workflow>

= Methods <sec:methods>

An initial survey of software support across container formats revealed that the DICOM format as the only widely supported format featuring lossy compression (JPEG 2K/LS/XL), which is generally required to acheieve compression ratios above #ratio("2:1") @ref:maroneImpactLossyCompression2020. Uncompressed TIFF stacks provide a baseline for comparison, while the OME-Zarr format with a vast selection of codecs were studied to gauge the performance of modern, less widely supported formats.

A set of TODO representative 16-bit unsigned integer and 32-bit float volumes were compressed for TODO combinations of container format and compression configurations while recording their (de)compression speeds and compression ratio (CR) against the 16-bit uncompressed baseline. Additionally, the fidelity was assessed using full-reference measures (PSNR, SSIM, MS-SSIM).

= Results <sec:results>

#figure(
  image("assets/plots/jpegxl_errors_z.png", width: 100%),
  caption: [
    Visualisation of errors in the reconstructed volume for JPEG-XL compression (`effort=7`) _across_ the compression planes. Higher distances $d$ indicate greater error bound. Compression with $d=1$ gives acceptable fidelity with $"CR"=95.6$, corresponding to $98.95%$ space saving.
  ]
)

#lorem(200)

= Conclusion


= TODO
- Compression ratio vs fidelity plot
- Error visualization for JPEG-XL
- Cost matrix?


#v(1fr)
= References
#[
#set text(size: 20pt)
#set par(spacing: 1em)
#bibliography("zotero_references.bib", title: none)
]
