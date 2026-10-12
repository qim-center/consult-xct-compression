#import "@preview/codly:1.3.0": *
#import "@preview/codly-languages:0.1.10": *

#let primary-color = color.rgb(153, 0, 0)

#let style(doc) = {
  show: codly-init.with()
  codly(languages: codly-languages)

  set heading(numbering: "1.1")
  show <nonumber>: set heading(numbering: none)
  set math.equation(numbering: "(1)")

  // show link: underline.with(offset: 0.15em)
  show link: set text(fill: primary-color, font: "DejaVu Sans Mono", size: 0.8em)

  set page(
    numbering: "1/1",
    margin: (
      top: 2.0cm,
      bottom: 2.0cm,
      left: 2.0cm,
      right: 3.0cm,
    )
  )
  doc
}

#let frontpage-1(front-content: none, authors: (), date: auto) = {
  // Setup variables
  let font = "Liberation Sans"
  let logo = image("assets/dtu_logo.svg", width: 20mm)

  set page(margin: 30mm, numbering: none)
  pagebreak(weak: true)

  let affiliation = [
    #set text(font: font, size: 14pt)
    #set par(spacing: 0.8em)
    #set par(leading: 0.5em)
    *DTU Compute*

    Department of Applied Mathematics\
    and Computer Science
  ]

  [
    #set align(center)
    #logo
    #v(6mm)
    #affiliation

    #v(15mm)

    #line(length:100%)
    #title()
    #line(length:100%)

    #set text(size: 14pt)
    #authors.intersperse(linebreak()).join()


    #v(10mm)
    #front-content
    #v(1fr)
    #{if date != auto {date} else {datetime.today()}}.display()
  ]
  pagebreak(weak: true)
}

#set page(paper: "a4")
#set document(
  title: "Dutten Report Demo",
  author: ("Jeppe Klitgaard")
)
#frontpage-1()

#set text(
  size: 11pt
)

#let appendix(body) = {
  set heading(numbering: "A.1", supplement: [Appendix])
  counter(heading).update(0)
  body
}
