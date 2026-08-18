#!/usr/bin/env python3
"""Check that every published chart names the source files it was built from.

The rule this enforces: a chart is traceable only if the file names it was built
from are stated on the chart itself, in its plot index row, and in the rendered
gallery - and only if those names are real files in the project data store.
A chart that names no file, or names one the store does not hold, fails here
rather than reaching a client.

    python build/verify_source_files.py

The store is the Drive folder recorded in build/source_files_manifest.csv:
https://drive.google.com/drive/folders/1oon2UYaOTBDiKUguQLlCf9Z3Pa_yvOz0

Exits non-zero on the first chart that breaks the rule, so it can gate a build.
"""

import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "build" / "source_files_manifest.csv"

# file names as written in a source line: letters, digits, underscore, hyphen
FILE_RX = re.compile(r"[A-Za-z0-9_-]+\.(?:csv|xlsx)")
# matplotlib writes the footer as text (svg.fonttype="none"), so it stays
# greppable - but a long source wraps across several <text> elements, so the
# whole footer is reassembled in document order before the source is read out
SVG_TEXT_RX = re.compile(r">([^<>]*)</text>")
SVG_SRC_RX = re.compile(r"Source:(.*?)Methodology:", re.S)
HTML_SRC_RX = re.compile(r"Source: [^<]{0,300}")
GALLERY_RX = re.compile(r'<dt>Source files</dt><dd class="files">([^<]*)</dd>')


def named(text):
    return sorted(set(FILE_RX.findall(text or "")))


def load_manifest():
    with MANIFEST.open(encoding="utf-8") as f:
        return {r["File"]: r["Drive_folder"] for r in csv.DictReader(f)}


def load_index():
    """Plot_ID -> files named in its plot index row."""
    out = {}
    for path in sorted((REPO / "build").glob("plot_index_*.csv")):
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if "Source_files" in row:
                    out[row["Plot_ID"]] = named(row["Source_files"])
    return out


def load_gallery():
    """Plot_ID -> files shown in the rendered gallery, per domain page."""
    out = {}
    for page in sorted(REPO.glob("*/index.html")):
        text = page.read_text(encoding="utf-8")
        for section in re.split(r'(?=<section class="chart")', text):
            pid = re.search(r'id="([A-Z0-9-]+)"', section)
            files = GALLERY_RX.search(section)
            if pid and files:
                out[pid.group(1)] = named(files.group(1))
    return out


def main():
    store = load_manifest()
    index = load_index()
    gallery = load_gallery()

    faces, interactive = {}, {}
    for svg in sorted(REPO.glob("*/charts/*.svg")):
        footer = " ".join(SVG_TEXT_RX.findall(
            svg.read_text(encoding="utf-8", errors="replace")))
        m = SVG_SRC_RX.search(footer)
        faces[svg.stem] = named(m.group(1) if m else "")
    for html in sorted(REPO.glob("*/charts/*.html")):
        m = HTML_SRC_RX.search(html.read_text(encoding="utf-8", errors="replace"))
        interactive[html.stem] = named(m.group(0) if m else "")

    if not faces:
        sys.exit("no charts found - run build/generate_charts.py first")

    failures, orphans = 0, []
    for pid in sorted(faces):
        face, idx = faces[pid], index.get(pid)
        web, inter = gallery.get(pid), interactive.get(pid)
        problems = []

        if idx is None:
            # not in any plot index, so not published: a builder that outlived
            # its chart, per the convention in README. Nothing to enforce.
            orphans.append(pid)
            continue
        if not face:
            problems.append("chart face names no source file")
        if not idx:
            problems.append("plot index row names no source file")
        elif face and set(idx) != set(face):
            problems.append(f"plot index {idx} != chart face {face}")
        if web is None:
            problems.append("no Source files row in the rendered gallery")
        elif face and set(web) != set(face):
            problems.append(f"gallery {web} != chart face {face}")
        # an interactive companion may name fewer files than the static chart
        # (it plots one panel of it), never a file the static chart does not use
        if inter is not None:
            if not inter:
                problems.append("interactive companion names no source file")
            elif set(inter) - set(face):
                problems.append(f"interactive {inter} not used by chart face {face}")
        unknown = sorted((set(face) | set(idx or [])) - set(store))
        if unknown:
            problems.append(f"not in the source store: {', '.join(unknown)}")

        if problems:
            failures += 1
            print(f"FAIL  {pid}")
            for p in problems:
                print(f"        {p}")
        else:
            where = ", ".join(f"{f} [{store[f]}]" for f in face)
            print(f"ok    {pid:<12} {where}")

    if orphans:
        print(f"\nnot published, skipped: {', '.join(orphans)}")
    print(f"\n{len(faces) - len(orphans)} published charts checked, {failures} failing")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
