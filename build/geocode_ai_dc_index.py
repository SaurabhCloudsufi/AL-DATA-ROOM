#!/usr/bin/env python3
"""Resolve the AI DC INDEX rows that ship without lat/lng, once, into a cache.

52 of 346 rows carry no coordinates. This script queries Nominatim (OpenStreetMap,
1 request/second as their usage policy requires) and writes
ai-dc-index/data/geocode_cache.csv, which IS committed - the query and the matched
display name go in alongside each hit so a reader can audit or correct any row by
hand. The summariser then joins that cache and never touches the network.

PRECISION IS NOT ATTEMPT ORDER
------------------------------
Queries are tried city -> region -> country. The obvious mistake is to label the
result by which attempt succeeded: when `city` is blank, `q(city, region, country)`
silently degrades to the region string and still succeeds on attempt one, which
would stamp "Oregon" and "Pennsylvania" as city-precision. Precision is therefore
taken from which source fields were actually populated. Only 13 of the 52 have a
city; 23 resolve at region level and 16 only to a country centroid, because rows
like "OpenAI Stargate U.S. Infrastructure Program" name a portfolio, not a place.

Re-running is safe but unnecessary: delete the cache first to force a refresh.

Usage:
    python build/geocode_ai_dc_index.py "/path/to/AI DC INDEX.xlsx"
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "ai-dc-index" / "data" / "geocode_cache.csv"

UA = "AL-DATA-ROOM/1.0 (research data room; one-off geocode of 52 rows)"
DELAY = 1.1  # Nominatim usage policy: max 1 request/second

# Wording that describes a programme rather than a place; it only confuses the
# geocoder ("Hyderabad cloud region / Telangana" -> "Hyderabad").
NOISE = re.compile(
    r"\b(cloud[- ]region[s]?|region[s]?|cluster|programme?|program|investment|"
    r"expansion|footprint|campus(es)?|areas?|grid|and additional sites?|tbd)\b", re.I)


def clean(v):
    if not v:
        return ""
    v = re.split(r"[/(]", str(v))[0]
    v = NOISE.sub(" ", v)
    return re.sub(r"[;,]\s*$", "", re.sub(r"\s+", " ", v)).strip(" ,-")


def query(*parts):
    seen, out = set(), []
    for p in parts:
        p = clean(p)
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return ", ".join(out)


def nominatim(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        hits = json.load(r)
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0].get("display_name", "")


def rows_missing_coords(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        header = [h for h in next(it) if h]
        idx = {name: i for i, name in enumerate(header)}
        for raw in it:
            def get(k):
                v = raw[idx[k]] if k in idx and idx[k] < len(raw) else None
                s = str(v).strip() if v is not None else ""
                return "" if s.lower() in ("", "none", "nan") else s
            if not get("id") and not get("title"):
                continue
            if get("lat"):
                continue
            out.append({k: get(k) for k in ("id", "title", "city", "region", "country")})
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: python build/geocode_ai_dc_index.py "/path/to/AI DC INDEX.xlsx"')
    todo = rows_missing_coords(sys.argv[1])
    print(f"{len(todo)} rows without coordinates\n")

    records = []
    for i, r in enumerate(todo, 1):
        # Precision comes from the source fields, never from which attempt hit.
        precision = "city" if r["city"] else ("region" if r["region"] else "country")
        attempts = [query(r["city"], r["region"], r["country"]),
                    query(r["city"], r["country"]),
                    query(r["region"], r["country"]),
                    query(r["country"])]
        seen, hit, used = set(), None, ""
        for level, q in zip(("city", "city", "region", "country"), attempts):
            if not q or q in seen:
                continue
            seen.add(q)
            try:
                hit = nominatim(q)
            except Exception as exc:                      # noqa: BLE001 - report and move on
                print(f"  ! {q}: {exc}", file=sys.stderr)
                hit = None
            time.sleep(DELAY)
            if hit:
                used = q
                if level == "country":
                    precision = "country"
                break
        if hit:
            lat, lng, matched = hit
            records.append({"id": r["id"], "lat": round(lat, 4), "lng": round(lng, 4),
                            "precision": precision, "query": used, "matched": matched[:140]})
            print(f"{i:>3}/{len(todo)} [{precision:<7}] {used[:50]:<50} -> {lat:8.3f},{lng:9.3f}")
        else:
            records.append({"id": r["id"], "lat": "", "lng": "", "precision": "unresolved",
                            "query": attempts[0], "matched": ""})
            print(f"{i:>3}/{len(todo)} [UNRESOLVED] {r['title'][:50]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "lat", "lng", "precision", "query", "matched"])
        w.writeheader()
        w.writerows(records)
    unresolved = sum(1 for r in records if r["precision"] == "unresolved")
    print(f"\nwrote {OUT.relative_to(REPO)}: {len(records)} rows, {unresolved} unresolved")


if __name__ == "__main__":
    main()
