#!/usr/bin/env bash
# Render a PDF to PNGs (and an optional contact-sheet montage) for visual review.
#
#   render.sh deck.pdf [dpi] [outprefix]
#   render.sh deck.pdf 80 /tmp/page     # -> /tmp/page-1.png ... and /tmp/page-montage.png
#
# Then Read the PNGs to inspect the result and iterate.
set -euo pipefail
pdf="${1:?usage: render.sh deck.pdf [dpi] [outprefix]}"
dpi="${2:-80}"
prefix="${3:-/tmp/render}"

command -v pdftoppm >/dev/null || { echo "pdftoppm not found (poppler-utils)" >&2; exit 1; }
rm -f "${prefix}"-*.png "${prefix}-montage.png"
pdftoppm -png -r "$dpi" "$pdf" "$prefix"
ls "${prefix}"-*.png
n=$(ls "${prefix}"-*.png | wc -l)
if command -v montage >/dev/null && [ "$n" -gt 1 ]; then
    cols=3; [ "$n" -le 4 ] && cols=2
    montage "${prefix}"-*.png -tile ${cols}x -geometry +3+3 -background gray "${prefix}-montage.png"
    echo "${prefix}-montage.png"
fi
