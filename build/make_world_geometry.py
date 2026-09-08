#!/usr/bin/env python3
"""Decode Natural Earth 110m country outlines into plain rings for inline SVG.

The map is self-contained: no tile server, no CDN, no API key. That means the
basemap has to ship inside the HTML, so this reduces world-atlas TopoJSON to the
smallest thing that still reads as a world map - a flat list of
{n: country name, r: [ring, ...]} with rings as [[lng, lat], ...].

Output build/world_110m.json is committed (~150 KB, 176 countries, 279 rings,
~9,900 points). Each country also carries a label anchor and the longitude span
of its largest ring, so the map can place country names and decide which ones
are wide enough on screen to be worth drawing at the current zoom.

Antarctica is dropped: it is a large share of the vertices and no AI data centre
is ever going there.

THE SEAM
--------
Three rings (Russia x2, Fiji) are stored wrapping the +/-180 antimeridian. Drawn
as-is in a projected plane each one smears a grey band straight across the map,
because consecutive vertices jump 360 degrees. They are cut at the jump; their
vertices already sit exactly on +/-180, so closing each piece leaves a clean
meridian edge. This is verified below - the script fails rather than emitting a
file that draws bands.

Coordinates are rounded to 2 decimals (~1.1 km), which is finer than 110m source
data resolves anyway.

Usage:
    python build/make_world_geometry.py          # downloads the source once
"""
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / "world_110m.json"
SRC = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"

DROP = {"Antarctica"}
TOLERANCE = 2


def decode_arcs(topo):
    """TopoJSON arcs are delta-encoded, quantised integers; undo both."""
    tr = topo.get("transform")
    (sx, sy), (tx, ty) = (tr["scale"], tr["translate"]) if tr else ((1, 1), (0, 0))
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty) if tr else (x, y))
        arcs.append(pts)
    return arcs


def stitch(arcs, indices):
    """A negative index means "arc ~i, reversed"; shared endpoints are dropped."""
    pts = []
    for i in indices:
        a = arcs[~i][::-1] if i < 0 else arcs[i]
        pts.extend(a[1:] if pts else a)
    return pts


def rings_of(geom, arcs):
    if geom["type"] == "Polygon":
        return [stitch(arcs, r) for r in geom["arcs"]]
    if geom["type"] == "MultiPolygon":
        return [stitch(arcs, r) for poly in geom["arcs"] for r in poly]
    return []


def split_antimeridian(pts):
    """Break a ring wherever it jumps the seam, then re-join the wrapped tail."""
    pieces, cur = [], []
    for a, b in zip(pts, pts[1:]):
        cur.append(a)
        if abs(b[0] - a[0]) > 180:
            pieces.append(cur)
            cur = []
    cur.append(pts[-1])
    pieces.append(cur)
    if len(pieces) > 1 and pieces[0] and pieces[-1]:
        pieces[0] = pieces[-1] + pieces[0]
        pieces.pop()
    return [p for p in pieces if len(p) >= 4]


def simplify(pts, tol):
    out = []
    for x, y in pts:
        p = (round(x, tol), round(y, tol))
        if not out or p != out[-1]:
            out.append(p)
    return out if len(out) >= 4 else None


def ring_area(ring):
    """Unsigned shoelace area, used only to rank rings against each other."""
    a = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


def label_anchor(rings):
    """Where a country's name should sit: the centroid of its largest ring.

    Largest, not all rings averaged - averaging drags the United States into the
    Pacific between Alaska, Hawaii and the mainland, and France into the Atlantic
    off its overseas territories. The biggest landmass is the one a reader is
    looking at, so the name goes there. Returned with that ring's longitude span,
    which the map uses to decide whether the country is wide enough on screen to
    be worth labelling at the current zoom.
    """
    big = max(rings, key=ring_area)
    xs = [p[0] for p in big]
    ys = [p[1] for p in big]
    return ([round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2)],
            round(max(xs) - min(xs), 2))


def main():
    print(f"fetching {SRC}")
    with urllib.request.urlopen(SRC, timeout=60) as r:
        topo = json.load(r)
    arcs = decode_arcs(topo)

    features = []
    for geom in topo["objects"]["countries"]["geometries"]:
        name = (geom.get("properties") or {}).get("name", "")
        if name in DROP:
            continue
        raw = [piece for ring in rings_of(geom, arcs) for piece in split_antimeridian(ring)]
        rings = [s for s in (simplify(r, TOLERANCE) for r in raw) if s]
        if rings:
            anchor, span = label_anchor(rings)
            features.append({"n": name, "l": anchor, "w": span,
                             "r": [[[x, y] for x, y in r] for r in rings]})

    bad = [f["n"] for f in features for r in f["r"]
           if any(abs(b[0] - a[0]) > 180 for a, b in zip(r, r[1:]))]
    if bad:
        sys.exit(f"seam-crossing rings survived in: {sorted(set(bad))}")

    blob = json.dumps(features, separators=(",", ":"))
    OUT.write_text(blob)
    print(f"wrote {OUT.relative_to(REPO)}  {len(features)} countries, "
          f"{sum(len(f['r']) for f in features)} rings, "
          f"{sum(len(r) for f in features for r in f['r']):,} points, {len(blob):,} bytes")


if __name__ == "__main__":
    main()
