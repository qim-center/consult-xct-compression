#import "constants.typ": primary-color

// Filled S-curve spanning its whole container, rising from the bottom-right
// corner to `height` above the bottom on the left, with horizontal tangents at
// both ends so it meets a block's top edge on the left and a baseline on the
// right. Percentages resolve against the container, so e.g. a grid row needs a
// fixed height.
#let swoosh(height, fill: primary-color) = {
  let top = 100% - height // curve coordinates have y pointing down
  curve(
    fill: fill,
    curve.move((0%, top)),
    curve.cubic((50%, top), (50%, 100%), (100%, 100%)),
    curve.line((0%, 100%)),
    curve.close(mode: "straight"), // default "smooth" would curve the closing edge
  )
}
