#!/usr/bin/env python3
"""Print the abstract as arXiv's metadata form wants it, straight from main.tex.

Do not paste the abstract out of the rendered PDF. main.tex is pure ASCII, but
the PDF is not: extracting from it yields typographic ligatures for fi and fl,
a curly apostrophe, and a combining circumflex from the p-hat. That is nine
invisible non-ASCII characters carried into a listing that is ASCII only, and
nobody would see them before they were public.

arXiv also refuses an abstract over 1920 characters, and the footnote is not
part of the abstract: it renders at the foot of the page, not in the metadata
field. Both are asserted here rather than left to a person counting at a form.

Math is emitted as TeX, which arXiv renders, rather than flattened to prose.

    python scripts/arxiv_abstract.py        -> the text to paste, then a report
"""
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIMIT = 1920  # arXiv rejects anything longer


def drop_command_with_arg(s, cmd):
    """Remove \\cmd{...} and its argument, honouring nested braces."""
    out, i, tag = [], 0, "\\" + cmd + "{"
    while True:
        j = s.find(tag, i)
        if j < 0:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:j])
        k, depth = j + len(tag), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(s[k], 0)
            k += 1
        i = k


def main():
    src = (REPO / "paper" / "main.tex").read_text()
    body = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", src, re.S).group(1)

    t = drop_command_with_arg(body, "footnote")
    t = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", t)   # prints its argument
    t = re.sub(r"\\emph\{([^{}]*)\}", r"\1", t)
    t = t.replace("{,}", ",").replace(r"\%", "%").replace(r"\&", "&")

    # \phat already sits inside $...$ in the source, so it expands to bare TeX,
    # not to its own math group. Everything after this point must leave math
    # alone: stripping commands and braces across it would turn \hat{p} into p
    # and strand the dollars, which is how this script first got it wrong.
    def prose(seg):
        seg = re.sub(r"\\[a-zA-Z]+\s*", "", seg)     # any remaining bare command
        return seg.replace("{", "").replace("}", "")

    parts = re.split(r"(\$[^$]*\$)", t)
    t = "".join(p.replace(r"\phat", r"\hat{p}")
                    .replace(r"\passk", "pass^k").replace(r"\safek", "safe^k")
                if p.startswith("$") else prose(p)
                for p in parts)
    t = re.sub(r"\s+", " ", t).strip()

    print(t)

    bad = [(i, c, unicodedata.name(c, "?")) for i, c in enumerate(t) if ord(c) > 127]
    print(f"\n--- {len(t)} characters, {len(t.split())} words, limit {LIMIT}",
          file=sys.stderr)
    if bad:
        for i, c, name in bad:
            print(f"    non-ASCII at {i}: {c!r} {name}", file=sys.stderr)
        sys.exit("abstract is not ASCII; arXiv metadata must be")
    if len(t) > LIMIT:
        sys.exit(f"abstract is {len(t) - LIMIT} characters over arXiv's limit")
    print(f"--- ASCII clean, {LIMIT - len(t)} characters to spare", file=sys.stderr)


if __name__ == "__main__":
    main()
