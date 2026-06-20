#!/usr/bin/env python3
"""Fetch bird species from Wikidata via SPARQL and output species.json.

Fetches: wingspan, length (P2043), height (P2048), IUCN status, family.
Length fallback: P2043 → P2048 → null (Wikipedia extraction is a separate script).
"""

import json
import urllib.request
import urllib.parse
import sys
import time

UNIT_TO_CM = {
    "Q174728": 100, "Q11573": 1, "Q174789": 0.1, "Q218593": 2.54, "Q3710": 30.48,
}

IUCN_QID = {
    "Q211005":  "LC",
    "Q719675":  "NT",
    "Q278113":  "VU",
    "Q11394":   "EN",
    "Q219127":  "CR",
    "Q239509":  "EW",
    "Q237350":  "EX",
    "Q3245245": "DD",
}

def sparql(query):
    url = "https://query.wikidata.org/sparql"
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(
        f"{url}?{params}",
        headers={"User-Agent": "birds-gallery/1.0 (funkycolours@gmail.com)"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())["results"]["bindings"]

def qid(uri):
    return uri.rsplit("/", 1)[-1] if uri else None

def to_cm(raw, unit_uri, lo=2, hi=500):
    if not raw or not unit_uri:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    unit = qid(unit_uri)
    factor = UNIT_TO_CM.get(unit, 100)
    converted = v * factor
    if lo <= converted <= hi:
        return round(converted, 1)
    if lo <= v <= hi:
        return round(v, 1)
    if lo <= v * 100 <= hi:
        return round(v * 100, 1)
    return None

def run():
    print("Query 1: birds with wingspan + article + image...", file=sys.stderr)
    rows = sparql("""
    SELECT ?bird ?birdLabel ?article ?sciName ?wsRaw ?wsUnit ?iucn ?family ?familyLabel WHERE {
      ?bird wdt:P105 wd:Q7432 ;
            wdt:P171* wd:Q5113 ;
            wdt:P18 [] ;
            wdt:P225 ?sciName ;
            wdt:P2050 [] .
      ?article schema:about ?bird ;
               schema:isPartOf <https://en.wikipedia.org/> .
      ?bird p:P2050/psv:P2050 [
        wikibase:quantityAmount ?wsRaw ;
        wikibase:quantityUnit ?wsUnit
      ] .
      OPTIONAL { ?bird wdt:P141 ?iucn . }
      OPTIONAL {
        ?bird wdt:P171 ?genus .
        ?genus wdt:P171 ?family .
        ?family wdt:P105 wd:Q35409 .
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    LIMIT 5000
    """)
    print(f"  → {len(rows)} raw rows", file=sys.stderr)

    birds = {}
    bird_qids = {}
    for r in rows:
        article_url = r.get("article", {}).get("value", "")
        if "/wiki/" not in article_url:
            continue
        wiki_title = urllib.parse.unquote(article_url.split("/wiki/")[1]).replace("_", " ")
        ws = to_cm(r.get("wsRaw", {}).get("value"), r.get("wsUnit", {}).get("value"), lo=5, hi=400)
        iucn_code = IUCN_QID.get(qid(r.get("iucn", {}).get("value", "")))
        family = r.get("familyLabel", {}).get("value", "")
        bid = qid(r.get("bird", {}).get("value", ""))

        if wiki_title in birds:
            b = birds[wiki_title]
            if ws and not b["wingspan_cm"]:
                b["wingspan_cm"] = ws
            if iucn_code and not b.get("status"):
                b["status"] = iucn_code
            if family and not b.get("family"):
                b["family"] = family
            continue

        birds[wiki_title] = {
            "wiki": wiki_title,
            "common": r.get("birdLabel", {}).get("value", wiki_title),
            "sci": r.get("sciName", {}).get("value", ""),
            "length_cm": None,
            "wingspan_cm": ws,
            "status": iucn_code,
            "family": family or None,
        }
        if bid:
            bird_qids[bid] = wiki_title

    print(f"  → {len(birds)} unique species", file=sys.stderr)
    time.sleep(3)

    # Query 2: P2043 (length)
    print("Query 2: length (P2043)...", file=sys.stderr)
    rows2 = sparql("""
    SELECT ?bird ?lenRaw ?lenUnit WHERE {
      ?bird wdt:P105 wd:Q7432 ;
            wdt:P171* wd:Q5113 ;
            wdt:P2043 [] .
      ?bird p:P2043/psv:P2043 [
        wikibase:quantityAmount ?lenRaw ;
        wikibase:quantityUnit ?lenUnit
      ] .
    }
    LIMIT 5000
    """)
    print(f"  → {len(rows2)} rows", file=sys.stderr)
    len_matched = 0
    for r in rows2:
        bid = qid(r.get("bird", {}).get("value", ""))
        if bid and bid in bird_qids:
            title = bird_qids[bid]
            length = to_cm(r.get("lenRaw", {}).get("value"), r.get("lenUnit", {}).get("value"))
            if length and not birds[title]["length_cm"]:
                birds[title]["length_cm"] = length
                len_matched += 1
    print(f"  → matched {len_matched} length values", file=sys.stderr)
    time.sleep(3)

    # Query 3: P2048 (height) — fallback for species missing length
    print("Query 3: height (P2048) as length fallback...", file=sys.stderr)
    rows3 = sparql("""
    SELECT ?bird ?htRaw ?htUnit WHERE {
      ?bird wdt:P105 wd:Q7432 ;
            wdt:P171* wd:Q5113 ;
            wdt:P2048 [] .
      ?bird p:P2048/psv:P2048 [
        wikibase:quantityAmount ?htRaw ;
        wikibase:quantityUnit ?htUnit
      ] .
    }
    LIMIT 5000
    """)
    print(f"  → {len(rows3)} rows", file=sys.stderr)
    ht_matched = 0
    for r in rows3:
        bid = qid(r.get("bird", {}).get("value", ""))
        if bid and bid in bird_qids:
            title = bird_qids[bid]
            if not birds[title]["length_cm"]:
                height = to_cm(r.get("htRaw", {}).get("value"), r.get("htUnit", {}).get("value"))
                if height:
                    birds[title]["length_cm"] = height
                    ht_matched += 1
    print(f"  → matched {ht_matched} height-as-length values", file=sys.stderr)

    result = [b for b in birds.values() if b["wingspan_cm"]]
    result.sort(key=lambda b: b["wingspan_cm"], reverse=True)
    result = result[:500]

    has_len = sum(1 for b in result if b["length_cm"])
    has_status = sum(1 for b in result if b.get("status"))
    has_family = sum(1 for b in result if b.get("family"))
    print(f"\nWriting {len(result)} species to species.json", file=sys.stderr)
    print(f"Stats: {has_len} with length, all {len(result)} with wingspan, {has_status} with status, {has_family} with family", file=sys.stderr)

    with open("species.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    run()
