# LaTeX build

```
paper/
  main.tex         body (sections 1-8 + reproducibility statement)
  appendix.tex     appendices A-D and F
  appendix-e.tex   GENERATED, do not edit  <- scripts/make_appendix_e.py
  refs.bib         GENERATED, do not edit  <- scripts/fetch_bib.py
```

Figures are pulled from `../docs/figs/` via `\graphicspath`, using the PDF
versions produced by `scripts/make_figures.py`.

## Build

```sh
cd paper
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

**No TeX toolchain was installed in the environment where these files were
written, so the sources have never been compiled.** They pass structural checks
only (balanced braces and environments, no unescaped underscores outside
verbatim, ASCII-clean bibliography). Expect to fix minor float placement and
table widths on the first real build. On macOS, `brew install --cask basictex`
then `sudo tlmgr install natbib booktabs` is enough for this preamble.

## Regenerating the two generated files

```sh
python scripts/make_appendix_e.py   # -> paper/appendix-e.tex + docs/appendix-e-tables.md
python scripts/fetch_bib.py         # -> paper/refs.bib   (needs network)
```

`make_appendix_e.py` asserts every number Section 5 cites and exits nonzero on
drift, so a failing run means the paper and the data have diverged. `fetch_bib.py`
pulls titles and author lists from the arXiv API rather than transcribing them,
which is the citation-verification gate in executable form.

## ICLR style files

The ICLR 2027 style files are not published yet (the 2027 Author Guide was still
404 as of 2026-07-31), so `main.tex` compiles as a plain `article`. The header of
`main.tex` lists the exact three changes to switch over once
`iclr2027_conference.sty` and `.bst` are available. Re-verify the Author Guide at
that point: the policy basis currently relied on is the 2026 guide.

## Still to do before submission

- Compile, then fix floats and table widths.
- Switch to the ICLR class and the anonymous author block.
- Add published venue fields to `refs.bib` for camera-ready (the arXiv records do
  not carry them); `fetch_bib.py` marks this with a TODO in the file it writes.
- Full-text read of each cited paper. The fetched metadata verifies identity
  (title, authors, abstract) but not the body-level claims attributed to them in
  Section 2.
