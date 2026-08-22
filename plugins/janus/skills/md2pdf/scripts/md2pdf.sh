#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_CSS="$SCRIPT_DIR/../css/default.css"

usage() {
  echo "Usage: md2pdf.sh INPUT.md [OUTPUT.pdf] [--css FILE]" >&2
  echo "  OUTPUT defaults to INPUT with .pdf extension" >&2
  exit 1
}

input=""
output=""
css="$DEFAULT_CSS"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --css)
      css="$2"
      shift 2
      ;;
    --help|-h)
      usage
      ;;
    *)
      if [[ -z "$input" ]]; then
        input="$1"
      elif [[ -z "$output" ]]; then
        output="$1"
      else
        usage
      fi
      shift
      ;;
  esac
done

[[ -z "$input" ]] && usage
[[ ! -f "$input" ]] && echo "Error: $input not found" >&2 && exit 1
[[ -z "$output" ]] && output="${input%.md}.pdf"

pandoc "$input" -o "$output" \
  --pdf-engine=weasyprint \
  --css="$css"

echo "$output"
