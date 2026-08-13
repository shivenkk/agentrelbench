#!/usr/bin/env bash
# Build the arXiv source package.
#
# Exists because an ad-hoc `tar czf` on macOS silently ships AppleDouble members.
# Every file under paper/ carries a com.apple.provenance xattr, and Apple's tar
# serialises those as `._name` entries. Worse, bsdtar *hides* them when listing:
# `tar tzf` reported 10 members while the archive actually held 18. Only a reader
# that does not merge AppleDouble (Python's tarfile, GNU tar) sees them.
#
# COPYFILE_DISABLE=1 stops the xattr serialisation; --no-xattrs is belt and
# braces. The verification pass at the end reads the archive with Python so the
# check cannot be fooled the same way the original one was.
#
# Usage: scripts/make-arxiv-package.sh [output.tar.gz]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO/dist-arxiv/agentrelbench-arxiv.tar.gz}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# arXiv compiles from the archive root, so the package is flat: no directories.
# main.tex's \graphicspath includes {./} for exactly this reason.
cp "$REPO"/paper/main.tex \
   "$REPO"/paper/appendix.tex \
   "$REPO"/paper/appendix-e.tex \
   "$REPO"/paper/refs.bib \
   "$REPO"/paper/main.bbl \
   "$REPO"/paper/neurips_2026.sty \
   "$STAGE/"
cp "$REPO"/docs/figs/fig1-pipeline.pdf \
   "$REPO"/docs/figs/fig2-universality-stochasticity.pdf \
   "$REPO"/docs/figs/fig3-capability-gradient.pdf \
   "$REPO"/docs/figs/fig4-audit-decay.pdf \
   "$STAGE/"

# Strip inherited xattrs from the staged copies as well, so the tar flags are a
# second line of defence rather than the only one.
xattr -cr "$STAGE" 2>/dev/null || true

mkdir -p "$(dirname "$OUT")"
( cd "$STAGE" && COPYFILE_DISABLE=1 tar --no-xattrs -czf "$OUT" ./* )

python3 - "$OUT" <<'PY'
import sys, tarfile
path = sys.argv[1]
names = tarfile.open(path).getnames()
stray = [n for n in names if n.startswith(("._", "./._")) or "/._" in n]
dirs = [n for n in names if n.count("/") > 1]
print(f"  members: {len(names)}")
for n in sorted(names):
    print(f"    {n}")
problems = []
if stray:
    problems.append(f"AppleDouble members present: {stray}")
if dirs:
    problems.append(f"package is not flat: {dirs}")
if len([n for n in names if n.endswith(".tex")]) != 3:
    problems.append("expected exactly 3 .tex files")
if not any(n.endswith("main.bbl") for n in names):
    problems.append("main.bbl missing (arXiv would need to run bibtex)")
if problems:
    print("\n  FAILED:")
    for p in problems:
        print(f"    {p}")
    sys.exit(1)
print("\n  clean: flat, no AppleDouble, bbl present")
PY

echo "  wrote $OUT"
