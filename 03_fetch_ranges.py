#!/usr/bin/env python3
"""Fetch country-level occurrence data per bird species from GBIF.

Usage:
  python3 03_fetch_ranges.py

Reads species.json, queries GBIF for each species' occurrence countries,
and writes results to ranges.json.

Resumes from where it left off if ranges.json already exists.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

def gbif_species_key(sci_name):
    """Look up GBIF species key by scientific name."""
    params = urllib.parse.urlencode({"name": sci_name})
    url = f"https://api.gbif.org/v1/species/match?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "birds-gallery/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get("matchType") != "NONE" and data.get("usageKey"):
            return data["usageKey"]
    except Exception as e:
        print(f"    match failed: {e}", file=sys.stderr)
    return None

def gbif_countries(species_key):
    """Get list of country codes where this species has been observed."""
    url = f"https://api.gbif.org/v1/occurrence/search?taxonKey={species_key}&limit=0&facet=country&facetLimit=300"
    req = urllib.request.Request(url, headers={"User-Agent": "birds-gallery/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        facets = data.get("facets", [])
        for f in facets:
            if f.get("field") == "COUNTRY":
                return [c["name"] for c in f.get("counts", []) if c.get("count", 0) >= 5]
    except Exception as e:
        print(f"    countries failed: {e}", file=sys.stderr)
    return []

def run():
    with open("species.json") as f:
        birds = json.load(f)

    ranges = {}
    if os.path.exists("ranges.json"):
        with open("ranges.json") as f:
            ranges = json.load(f)
        print(f"Resuming — {len(ranges)} species already done", file=sys.stderr)

    remaining = [b for b in birds if b["wiki"] not in ranges]
    print(f"Processing {len(remaining)} of {len(birds)} species...", file=sys.stderr)

    for i, bird in enumerate(remaining):
        wiki = bird["wiki"]
        sci = bird["sci"]
        print(f"[{i+1}/{len(remaining)}] {bird['common']} ({sci})...", file=sys.stderr, end=" ")

        key = gbif_species_key(sci)
        if not key:
            print("no GBIF match", file=sys.stderr)
            ranges[wiki] = []
            with open("ranges.json", "w") as f:
                json.dump(ranges, f, indent=2, ensure_ascii=False)
            time.sleep(0.3)
            continue

        countries = gbif_countries(key)
        ranges[wiki] = countries
        print(f"→ {len(countries)} countries", file=sys.stderr)

        with open("ranges.json", "w") as f:
            json.dump(ranges, f, indent=2, ensure_ascii=False)

        time.sleep(0.3)

    total = sum(1 for v in ranges.values() if v)
    print(f"\nDone — {total} species with range data saved to ranges.json", file=sys.stderr)

if __name__ == "__main__":
    run()
