#!/usr/bin/env python3
"""Derive the mappable AI DC INDEX site table the map reads.

Source: "AI DC INDEX.xlsx" - eight continent sheets sharing one 14-column
schema. Raw workbook is not committed; only the derived table.

WHAT THIS SCRIPT HAS TO DECIDE
------------------------------
Three columns arrive as free prose, not categories: `status` has 89 distinct
values over 346 rows, `energy_type` 173, `ai_focus` 267. Used raw they are
useless as map facets - every site would be its own legend entry. They are
classified here into small closed vocabularies, and the original strings are
carried through unchanged as *_raw so the popup can show what was actually
written and nothing is lost.

Two rules matter and were arrived at by checking the data, not assumed:

1. Classify on the HEAD CLAUSE, not the whole cell. These cells routinely name
   a category and then append a caveat - "AWS cloud region supporting general
   cloud and AI services; specific facility capacity not disclosed". Testing
   the full string sees "not disclosed" and returns Unknown, throwing away the
   "general cloud" the row plainly states. Splitting on ";" and reading only
   the head cut unclassified `ai_focus` from 88 rows to 30.

2. Normalise underscores before matching. 45 rows carry the coded literal
   `under_construction` rather than prose, and a /under construction/ pattern
   silently misses every one of them.

Residual Unknowns are real: 87 of 89 unresolved `energy_type` cells say some
variant of "not disclosed" outright. They are reported, not hidden.

COORDINATES
-----------
52 of 346 rows ship without lat/lng. They are resolved once, offline, into
`geocode_cache.csv` (committed, with the query and the matched display name
for audit) by build/geocode_ai_dc_index.py, and joined here.

Only 13 of those 52 resolve to a city. The rest are portfolio and cloud-region
records - "AWS US East (Northern Virginia) Region", "OpenAI Stargate U.S.
Infrastructure Program" - that name no single building, so they land on a
region or country centroid. That is recorded per row in `geo_precision`
(exact | city | region | country) and the map draws anything coarser than
`exact` with an uncertainty halo instead of pretending to a rooftop. Precision
is derived from which source fields were populated, not from which geocoder
attempt happened to return a hit: with `city` blank the first query degrades to
the region string, and trusting attempt order labels "Oregon" a city.

52 rows also carry no `megawatts`. A circle has no size without it, so they are
excluded from the map's marks but kept in the table and counted in the summary.
34 rows are missing both.

Usage:
    python build/summarise_ai_dc_index.py "/path/to/AI DC INDEX.xlsx"
"""
import csv
import re
import sys
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "ai-dc-index" / "data"
CACHE = OUT / "geocode_cache.csv"

COLS = ["id", "title", "megawatts", "companies", "country", "region", "city",
        "status", "energy_type", "ai_focus", "start_year", "lat", "lng", "sources"]

# --------------------------------------------------------------- classifiers
STATUS_RULES = [
    ("Operational", r"operational|operating|serving traffic|started operation|"
                    r"began operation|went live|in service|live since|existing |"
                    r"active and expanding"),
    ("Under construction", r"under construction|construction (has |is )?(started|began|"
                           r"begun|underway)|early construction|breaking ground|"
                           r"broke ground|groundbreaking|active implementation|"
                           r"equipment bring-up|startup activity"),
    ("Announced", r"\bannounced\b|\bmou\b|memorandum|letter of intent|agreement|"
                  r"exclusive negotiations|\bbid\b|selected as"),
    ("Planned", r"planned|proposal|proposed|future|expected|roadmap|targeted|permit|"
                r"rezoning|feed-stage|initiative|scheduled|restart"),
]
ENERGY_RULES = [
    ("Nuclear", r"nuclear|small modular|\bsmr\b"),
    # "Mixed (Grid with renewable targets)" must not read as Renewable, so Mixed
    # is tested before the renewable keywords it contains.
    ("Mixed", r"\bmixed\b"),
    ("Renewable", r"renewable|hydro|solar|wind|geothermal|net-zero|net zero|"
                  r"100% clean|green (energy|computing)"),
    ("Gas", r"natural gas|\bgas\b|turbine"),
    ("Grid", r"\bgrid\b|utility|kepco|tepco|electric corporation"),
]
FOCUS_RULES = [
    ("Training & inference", r"(train\w*).*(infer\w*)|(infer\w*).*(train\w*)"),
    ("Training", r"train"),
    ("Inference", r"infer"),
    ("HPC", r"\bhpc\b|supercomput"),
    ("General cloud", r"cloud|colocation|interconnect"),
    # Prose that never says training/inference but is unambiguously an AI site
    # ("Sovereign AI (NVIDIA Blackwell)"). Better than dropping it to Unknown.
    ("AI (unspecified)", r"\bai\b|\bgpu\b|accelerat|machine learning|\bllm\b"),
]
UNKNOWN_HEAD = r"^unknown|not disclosed|not selected|not source-resolved|not publicly|not yet source"

STATUS_ORDER = ["Operational", "Under construction", "Planned", "Announced", "Unknown"]
ENERGY_ORDER = ["Renewable", "Nuclear", "Gas", "Grid", "Mixed", "Unknown"]
FOCUS_ORDER = ["Training & inference", "Training", "Inference", "HPC",
               "General cloud", "AI (unspecified)", "Unknown"]

COMPANY_ALIAS = {
    "amazon web services": "Amazon", "aws": "Amazon", "amazon": "Amazon",
    "google cloud": "Google", "google": "Google", "google deepmind": "Google",
    "microsoft azure": "Microsoft", "microsoft": "Microsoft",
    "alibaba cloud": "Alibaba", "alibaba": "Alibaba",
    "meta platforms": "Meta", "meta": "Meta",
    "softbank group": "SoftBank", "softbank": "SoftBank",
    "tencent cloud": "Tencent", "huawei cloud": "Huawei",
    "oracle cloud": "Oracle", "hewlett packard enterprise": "HPE",
}


def norm(v):
    return re.sub(r"[_\s]+", " ", str(v or "").strip().lower())


def classify(value, rules):
    head = norm(value).split(";")[0].strip()
    if not head or re.search(UNKNOWN_HEAD, head):
        return "Unknown"
    for label, pattern in rules:
        if re.search(pattern, head):
            return label
    return "Unknown"


def primary_company(cell):
    first = re.split(r";", str(cell or ""))[0].strip()
    return COMPANY_ALIAS.get(first.lower(), first) or "Unknown"


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def txt(v):
    s = str(v).strip() if v is not None else ""
    return "" if s.lower() in ("", "none", "nan") else s


# --------------------------------------------------------------- extraction
def read_workbook(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        header = [h for h in next(it) if h]
        if header[:len(COLS)] != COLS:
            sys.exit(f"{ws.title}: unexpected header {header[:len(COLS)]}")
        for raw in it:
            rec = dict(zip(COLS, raw[:len(COLS)]))
            if not txt(rec["id"]) and not txt(rec["title"]):
                continue
            rec["continent"] = "Oceania" if ws.title == "Ocenaia" else ws.title
            rows.append(rec)
    return rows


def load_cache():
    if not CACHE.exists():
        sys.exit(f"missing {CACHE.relative_to(REPO)} - run "
                 f"build/geocode_ai_dc_index.py first")
    with CACHE.open() as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def build(rows, cache):
    out = []
    for r in rows:
        lat, lng = num(r["lat"]), num(r["lng"])
        precision = "exact"
        if lat is None or lng is None:
            hit = cache.get(txt(r["id"]))
            if hit and hit.get("lat"):
                lat, lng = float(hit["lat"]), float(hit["lng"])
                precision = hit["precision"]
            else:
                precision = "unresolved"
        out.append({
            "id": txt(r["id"]),
            "title": txt(r["title"]),
            "megawatts": num(r["megawatts"]),
            "primary_company": primary_company(r["companies"]),
            "companies": "; ".join(c.strip() for c in re.split(r";", txt(r["companies"])) if c.strip()),
            "continent": r["continent"],
            "country": txt(r["country"]),
            "region": txt(r["region"]),
            "city": txt(r["city"]),
            "status_class": classify(r["status"], STATUS_RULES),
            "status_raw": txt(r["status"]),
            "energy_class": classify(r["energy_type"], ENERGY_RULES),
            "energy_raw": txt(r["energy_type"]),
            "focus_class": classify(r["ai_focus"], FOCUS_RULES),
            "focus_raw": txt(r["ai_focus"]),
            "start_year": int(num(r["start_year"])) if num(r["start_year"]) else None,
            "lat": round(lat, 4) if lat is not None else None,
            "lng": round(lng, 4) if lng is not None else None,
            "geo_precision": precision,
            "source_url": txt(r["sources"]).split()[0] if txt(r["sources"]) else "",
        })
    return out


# --------------------------------------------------------------- outputs
def write_csv(name, fieldnames, records):
    path = OUT / name
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for rec in records:
            w.writerow({k: ("" if rec.get(k) is None else rec.get(k)) for k in fieldnames})
    print(f"wrote {path.relative_to(REPO)}  ({len(records)} rows)")


def rollup(sites, key, order=None):
    agg = {}
    for s in sites:
        k = s[key] or "Unknown"
        a = agg.setdefault(k, {key: k, "sites": 0, "sites_with_mw": 0, "megawatts": 0.0})
        a["sites"] += 1
        if s["megawatts"]:
            a["sites_with_mw"] += 1
            a["megawatts"] += s["megawatts"]
    rows = list(agg.values())
    for a in rows:
        a["megawatts"] = round(a["megawatts"], 1)
    if order:
        rows.sort(key=lambda a: order.index(a[key]) if a[key] in order else len(order))
    else:
        rows.sort(key=lambda a: -a["megawatts"])
    return rows


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[-1].strip())
    OUT.mkdir(parents=True, exist_ok=True)

    rows = read_workbook(sys.argv[1])
    sites = build(rows, load_cache())

    write_csv("dc_index_sites.csv", list(sites[0].keys()), sites)
    for name, key, order in [("dc_index_by_country.csv", "country", None),
                             ("dc_index_by_company.csv", "primary_company", None),
                             ("dc_index_by_status.csv", "status_class", STATUS_ORDER),
                             ("dc_index_by_energy.csv", "energy_class", ENERGY_ORDER),
                             ("dc_index_by_focus.csv", "focus_class", FOCUS_ORDER)]:
        recs = rollup(sites, key, order)
        write_csv(name, [key, "sites", "sites_with_mw", "megawatts"], recs)

    mapped = [s for s in sites if s["lat"] is not None and s["megawatts"]]
    years = [s["start_year"] for s in sites if s["start_year"]]
    summary = [{
        "sites_total": len(sites),
        "sites_mapped": len(mapped),
        "megawatts_total": round(sum(s["megawatts"] for s in sites if s["megawatts"]), 1),
        "megawatts_mapped": round(sum(s["megawatts"] for s in mapped), 1),
        "missing_megawatts": sum(1 for s in sites if not s["megawatts"]),
        "missing_coords_in_source": sum(1 for r in rows if num(r["lat"]) is None),
        "geo_exact": sum(1 for s in sites if s["geo_precision"] == "exact"),
        "geo_city": sum(1 for s in sites if s["geo_precision"] == "city"),
        "geo_region": sum(1 for s in sites if s["geo_precision"] == "region"),
        "geo_country": sum(1 for s in sites if s["geo_precision"] == "country"),
        "geo_unresolved": sum(1 for s in sites if s["geo_precision"] == "unresolved"),
        "missing_start_year": sum(1 for s in sites if not s["start_year"]),
        "year_first": min(years), "year_last": max(years),
        "countries": len({s["country"] for s in sites}),
        "primary_companies": len({s["primary_company"] for s in sites}),
        "status_unclassified": sum(1 for s in sites if s["status_class"] == "Unknown"),
        "energy_unclassified": sum(1 for s in sites if s["energy_class"] == "Unknown"),
        "focus_unclassified": sum(1 for s in sites if s["focus_class"] == "Unknown"),
    }]
    write_csv("dc_index_summary.csv", list(summary[0].keys()), summary)

    s = summary[0]
    print(f"\n  {s['sites_total']} sites, {s['sites_mapped']} mappable "
          f"({s['megawatts_mapped']:,.0f} of {s['megawatts_total']:,.0f} MW), "
          f"{s['countries']} countries, {s['year_first']}-{s['year_last']}")


if __name__ == "__main__":
    main()
