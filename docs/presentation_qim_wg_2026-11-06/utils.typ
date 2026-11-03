#import "qim.typ"

#let pb = pagebreak(weak: true)

#let _green = std.green.transparentize(60%)
#let _red = std.red.transparentize(60%)

#let green = highlight.with(fill: _green, radius: 3pt, extent: 2pt)
#let green-box = box.with(fill: _green, radius: 3pt, outset: 2pt)

#let red = highlight.with(fill: _red, radius: 3pt, extent: 2pt)
#let red-box = box.with(fill: _red, radius: 3pt, outset: 2pt)

#let boxed = box.with(stroke: (thickness: 1pt, paint: qim.grey), outset: 10pt, radius: 10pt)

#let ratio(x) = {
  let (nom, denom) = x.children.map(c => c.at("text", default: "")).join().split(":")
  [$nom#h(0.1em)∶#h(0.1em)#denom$]
}

/// Places a right curly brace spanning the full height of `body`, with `annotation` to its right.
/// Uses tight (leading) spacing so it can sit inside a list without breaking its rhythm.
#let brace-right(body, annotation, gap: 0.3em) = context {
  let h = measure(body).height
  block(spacing: par.leading, grid(
    columns: 3,
    align: horizon,
    column-gutter: gap,
    body, math.lr($\}$, size: h), annotation,
  ))
}
