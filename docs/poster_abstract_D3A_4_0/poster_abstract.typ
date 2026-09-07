#import "@preview/wordometer:0.1.5": word-count-of
#import "@preview/zero:0.7.0": num as znum, quan
#import calc: pow

#set par(justify: true)
#set text(size: 12pt)

#set page(margin: 2.0cm)

#let full = false

#set document(
  author: "Jeppe Klitgaard",
  date: datetime(year: 2026, month: 09, day: 07),
  title: [
    Compression Strategies for High-Throughput X-Ray CT\
    of Natural History Collections
  ]
)

#show title: set text(size: 14pt)

#align(center)[
  #title()

  #underline[Jeppe Klitgaard]#super([a,b,\*]),
  Carsten Gundlach#super([c,d]),
  Christy Anna Hipsley#super([e,f]),
  Mark D. Scherz#super([e]),\
  Kim Steenstrup Pedersen#super([e,g]),
  Felipe Delestro Matos#super([a,b]),\
  Anders Bjorholm Dahl#super([a,b,c]),
  Jakob Sauer Jørgensen#super([a,b])

  #[
    #set text(size: 9pt)
    #super([a])_Center for Quantification of Imaging Data from MAX IV, Kongens Lyngby, Denmark_\
    #super([b])_Department of Applied Mathematics and Computer Science, Technical University of Denmark, Kongens Lyngby, Denmark_\
    #super([c])_3D Imaging Centre, Technical University of Denmark, Kongens Lyngby, Denmark_\
    #super([d])_Department of Physics, Technical University of Denmark, Kongens Lyngby, Denmark_\
    #super([e])_Natural History Museum of Denmark, University of Copenhagen, Copenhagen, Denmark_\
    #super([f])_Department of Biology, University of Copenhagen, Copenhagen, Denmark_\
    #super([g])_Department of Computer Science, University of Copenhagen, Copenhagen, Denmark_
  ]
]
// Hack for * footnote
#[
#set footnote(numbering: (x) => none)
#footnote[#super[\*]E-Mail: `s250250@dtu.dk`]
#counter(footnote).update(0)
]
#let abstract = [
  The NaturArv3D project#footnote(link("https://3dim.dtu.dk/newsarchive/2025/03/naturarv_3d")) will acquire 3D X-ray images of the full vertebrate collection of the Natural History Museum of Denmark at sub-#quan[10 um] voxel size, in collaboration with the DTU 3D Imaging Centre. The scale of the project necessitates a custom high-throughput X-ray scanner with robotic sample handling, capable of scanning up to 500 samples per week. The expected annual data volume of approximately #quan[1 PB] renders long-term archival storage economically onerous without substantial compression.

  The compression ratios (CR), compression and decompression times, and quality loss are determined for in-memory compression tests across a large number of lossless and lossy compression schemes, including JPEG-LS and the recent JPEG XL standard. Relevant subsets of the tests are performed in TIFF, DICOM, and (OME-)Zarr containers in order to determine the most viable archival formats and their compatibility with prevalent image-processing software packages. Quality loss is quantified using common full-reference metrics including SSIM @ref:wangImageQualityAssessment2004, MS-SSIM @ref:wangMultiscaleStructuralSimilarity2003, and PSNR.

  We find that lossless schemes yield a maximum CR of 1.75:1, corresponding to a 43% space saving (SS). The JPEG-LS and JPEG XL codecs achieve CRs of 16.3:1 (93.9% SS) and 45.6:1 (97.8% SS), respectively, at imperceptible quality loss ($"PSNR" ≈ #quan[60 dB] "full scale", "3D SSIM" ≈ 0.999$) on a representative 16-bit CT volume. Alongside JPEG 2000, these schemes in combination with a DICOM container constitute the only lossy options widely supported among the surveyed packages. Compression times remain compatible with high-throughput acquisition, while decompression is sufficiently fast to improve access times over the uncompressed, I/O-bound case.

  Relative to the baseline data pipeline without compression, the proposed schemes offer an estimated annual storage-cost saving of 2 million DKK under realistic operating conditions. This underscores that the adoption of lossy compression is decisive for the economic viability of high-throughput X-ray imaging at scale.
]
#abstract
#v(1fr)
#[
#set text(size: 10pt)
// #show heading: set text(size: 12pt)
#bibliography("zotero_references.bib", title: "References")
// #bibliography("zotero_references.bib", title: none)
]

#if full [
#pagebreak(weak: true)
#set page(margin: 0.5cm)
Word count: #word-count-of(abstract)

#v(1fr)

#let sizes = (
  // (
  //   name: [Czeibart],
  //   shape: (500, 500, 1000),
  //   crop: 0.0,
  //   bitdepth: 16,
  // ),
  (
    name: [*Small Detector*],
    shape: (3072, 3072, 3072),
    crop: 0.5,
    bitdepth: 16,
  ),
  (
    name: [4K],
    shape: (4096, 4096, 4096),
    crop: 0.0,
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
    name: [
      *Lossy\
      JPEG-LS*\
      $"level" = 128$
    ],
    ratio: 16.3,
  ),
  (
    name: [
      *Lossy\
      JPEG XL*\
      $d=0.25$
      ],
    ratio: 45.6,
  ),
  (
    name: [
      *Lossy\
      JPEG XL*\
      $d=1.0$
      ],
    ratio: 140.5,
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
      let voxels = size.shape.at(0) * size.shape.at(1) * size.shape.at(2)
      let uncompressed = voxels * (size.bitdepth / 8) * (1 - size.crop)
      let compressed = uncompressed / compression.ratio
      let compressed_GB = compressed / pow(10, 9)
      let morphsource_USD_per_GB = 3.47
      let DKK_per_USD = 6.39
      let DKK_per_GBP = 8.70
      let backblaze_B2_USD_per_GB_per_year = 83.4 / 1000
      let cambridge_RCS_RDS_GBP_per_GB_per_year = 95.0 / 1000

      let ms_ratio = pow(10, -9) * morphsource_USD_per_GB * DKK_per_USD
      let bb_ratio = pow(10, -9) * backblaze_B2_USD_per_GB_per_year * DKK_per_USD * 5
      let cam_ratio = pow(10, -9) * cambridge_RCS_RDS_GBP_per_GB_per_year * DKK_per_GBP * 5
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

          num-disp(voxels, unit: "vx"),
          num-disp(voxels * 500, unit: "vx"),
          num-disp(voxels * (500 / 7 * 365.2425), unit: "vx"),

          num-disp(compressed, unit: "B"),
          num-disp(compressed * 500, unit: "B"),
          num-disp(compressed * (500 / 7 * 365.2425), unit: "B"),

          num-disp(compressed * ms_ratio, unit: "kr"),
          num-disp(compressed * week_coeff * ms_ratio, unit: "kr"),
          num-disp(compressed * year_coeff * ms_ratio, unit: "kr"),

          num-disp(compressed * cam_ratio, unit: "kr"),
          num-disp(compressed * week_coeff * cam_ratio, unit: "kr"),
          num-disp(compressed * year_coeff * cam_ratio, unit: "kr"),

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


- Cell rows:
  + Data size
  + Storage cost — MorphSource, 3.47 USD/GB = 22.33 DKK/GB
  + Storage cost — University of Cambridge, Research Computing Services, Research File Share
    - https://docs.hpc.cam.ac.uk/storage/prices.html
    - Backed up, 2 replicas
    - 475.00 GBP/TB/5yr = 4132.5 DKK/TB/5yr
  + Storage cost — Backblaze B2
    - 417 USD/TB/5yr = 2.683.75 DKK/TB/yr
- Cell columns:
  + 1 reconstruction
  + 1 week of reconstructions (shaded, $500$)
  + 1 year of reconstructions ($500 × 365.2425 \/ 7 ≈ 26089$)
- Units have been SI-ified: mkr = milli-kroner, Mkr = mega-kroner/million, etc.

Cost estimate in abstract:
- Lossy JPEG XL with $d=0.25$ for $"CR" = 45.6$
- Round up *_Small Detector_* estimate from ≈ 756 GB to 1 PB to account for the fact that some significant portion of samples are to be run on _Large Detector_.
- Use Cambridge RCS cost estimate, amortized over 5 years:
- $1 "PB" × 1000 "TB"/"PB" × 475.00 £/("TB" × 5 "yr") × 8.7 "DKK"/£ × (1 - 1 / 45.6) = #znum[3055657.5]$ DKK
]
