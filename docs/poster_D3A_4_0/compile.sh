#!/bin/bash

typst c poster.typ --pdf-standard a-2b --font-path fonts/
# typst c poster.typ --format svg --font-path fonts/
typst c poster.typ --format png --ppi 50 --font-path fonts/
