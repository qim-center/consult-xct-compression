#let mref(key) = {
  /// Allows referencing a label while in math mode.
  let lbl = label(key)
  math.text([(#ref(lbl, supplement: none))])
}

#let below(x, b) = {
  math.scripts(math.attach(math.limits(x), b: b))
}

#let underbar(x) = {
  below(x, math.macron)
}

#let mathformatter(underbars: 0, bold: true, upright: false) = {
  /// This function can be used to construct a vector or matrix notation function.
  ///
  /// My preferred style is:
  /// #let vv = mathformatter(underbars: 0, bold: true, upright: false)
  /// #let mm = mathformatter(underbars: 0, bold: true, upright: true)
  ///
  /// For handwritten-style vectors and matrices, I recommend:
  /// #let vv = mathformatter(underbars: 1, bold: false, upright: false)
  /// #let mm = mathformatter(underbars: 2, bold: false, upright: true)
  ///
  /// Arguments:
  ///   underbars: How many underbars to put under.
  ///   bold: Whether to make the vector bold.
  ///   upright: Whether to make the vector upright.

  let f(x) = {
    let out = x

    for _ in range(underbars) {
      out = underbar(out)
    }

    if bold {
      out = math.bold(out)
    }

    if upright {
      out = math.upright(out)
    }

    out
  }
  f
}
