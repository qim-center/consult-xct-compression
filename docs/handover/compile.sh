#!/usr/bin/env bash
# Compile the main Typst document of each folder in docs/ into docs/handover/,
# copy over the results summary, then bundle everything into docs/handover/handover.zip.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS="$(dirname "$HERE")"

failed=()
# Usage: [PDF_STANDARD=...] compile <source relative to docs/> <output name> [extra typst args...]
compile() {
    echo "Compiling $1 -> $2"
    typst compile --pdf-standard "${PDF_STANDARD:-a-2b}" "${@:3}" "$DOCS/$1" "$HERE/$2" || failed+=("$1")
}

# Meetings
compile meetings/2026-08-04__Jeppe_Jakob/slides.typ 2026-08-04_meeting_Jeppe_Jakob_slides.pdf
compile meetings/2026-08-12__NaturArv3D/slides.typ  2026-08-12_meeting_NaturArv3D_slides.pdf
compile meetings/2026-08-27__NaturArv3D/slides.typ  2026-08-27_meeting_NaturArv3D_slides.pdf
compile meetings/2026-09-18__NaturArv3D/slides.typ  2026-09-18_meeting_NaturArv3D_slides.pdf
compile meetings/2026-10-06__NaturArv3D/slides.typ  2026-10-06_meeting_NaturArv3D_slides.pdf

# D3A 4.0 poster and abstract
compile poster_abstract_D3A_4_0/poster_abstract.typ D3A_4_0_poster_abstract.pdf
compile poster_D3A_4_0/poster.typ                   D3A_4_0_poster.pdf \
    --font-path "$DOCS/poster_D3A_4_0/fonts"

# Results summary behind the poster
echo "Copying poster_D3A_4_0/assets/summary.csv -> summary.csv"
cp "$DOCS/poster_D3A_4_0/assets/summary.csv" "$HERE/summary.csv" || failed+=("summary.csv")

if ((${#failed[@]})); then
    echo "Failed:" >&2
    printf '  %s\n' "${failed[@]}" >&2
    exit 1
fi

# Bundle all PDFs and the summary into a single zip
ZIP="$HERE/handover.zip"
echo "Zipping PDFs, summary.csv, and REMARKS.md -> $(basename "$ZIP")"
rm -f "$ZIP"
zip -jq "$ZIP" "$HERE"/*.pdf "$HERE/summary.csv" "$HERE/REMARKS.md"
