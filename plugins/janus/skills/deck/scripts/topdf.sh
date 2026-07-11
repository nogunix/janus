#!/usr/bin/env bash
# Convert pptx -> pdf with LibreOffice, with the Japanese-font fix applied, then
# report which CJK fonts got embedded so you can catch Chinese-glyph fallback.
#
#   topdf.sh deck.pptx [outdir]
#
# Why LANG=ja_JP.UTF-8: with an en_US locale LibreOffice resolves CJK fallback to
# Simplified-Chinese glyphs (Han unification). A Japanese locale makes fontconfig
# prefer the JP faces. A throwaway -env profile avoids a stale font cache.
set -euo pipefail
src="${1:?usage: topdf.sh deck.pptx [outdir]}"
outdir="${2:-$(dirname "$src")}"
prof="/tmp/lo_topdf_$$"

command -v soffice >/dev/null || { echo "soffice not found; install libreoffice-impress" >&2; exit 1; }

LANG=ja_JP.UTF-8 LC_ALL=ja_JP.UTF-8 soffice "-env:UserInstallation=file://$prof" \
    --headless --convert-to pdf --outdir "$outdir" "$src"

pdf="$outdir/$(basename "${src%.*}").pdf"
if command -v pdffonts >/dev/null; then
    echo "--- embedded CJK fonts in $pdf ---"
    if pdffonts "$pdf" | grep -i cjk; then :; else echo "(none)"; fi
    if pdffonts "$pdf" | grep -qi cjksc; then
        echo "WARNING: NotoSansCJKsc (Chinese) embedded — set East-Asian font to 'Noto Sans CJK JP' and/or check the locale." >&2
    fi
fi
echo "$pdf"