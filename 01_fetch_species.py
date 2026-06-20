#!/usr/bin/env python3
"""Fetch bird species from Wikidata via SPARQL and output species.json.

Fetches: wingspan, IUCN conservation status, family taxonomy.
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
    "Q211005":  "LC",   # Least Concern
    "Q719675":  "NT",   # Near Threatened
    "Q278113":  "VU",   # Vulnerable
    "Q11394":   "EN",   # Endangered
    "Q219127":  "CR",   # Critically Endangered
    "Q239509":  "EW",   # Extinct in the Wild
    "Q237350":  "EX",   # Extinct
    "Q3245245": "DD",   # Data Deficient
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

def to_cm(raw, unit_uri):
    if not raw or not unit_uri:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    unit = qid(unit_uri)
    factor = UNIT_TO_CM.get(unit, 100)
    converted = v * factor
    if 5 <= converted <= 400:
        return round(converted, 1)
    if 5 <= v <= 400:
        return round(v, 1)
    if 5 <= v * 100 <= 400:
        return round(v * 100, 1)
    return None

def run():
    # Query 1: birds with wingspan + article + image
    print("Query 1: birds with wingspan...", file=sys.stderr)
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
    for r in rows:
        article_url = r.get("article", {}).get("value", "")
        if "/wiki/" not in article_url:
            continue
        wiki_title = urllib.parse.unquote(article_url.split("/wiki/")[1]).replace("_", " ")

        ws = to_cm(r.get("wsRaw", {}).get("value"), r.get("wsUnit", {}).get("value"))

        iucn_uri = r.get("iucn", {}).get("value", "")
        iucn_code = IUCN_QID.get(qid(iucn_uri))

        family = r.get("familyLabel", {}).get("value", "")

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
            "wingspan_cm": ws,
            "status": iucn_code,
            "family": family or None,
        }

    result = [b for b in birds.values() if b["wingspan_cm"]]
    result.sort(key=lambda b: b["wingspan_cm"], reverse=True)
    result = result[:500]

    has_status = sum(1 for b in result if b.get("status"))
    has_family = sum(1 for b in result if b.get("family"))
    print(f"\nWriting {len(result)} species to species.json", file=sys.stderr)
    print(f"Stats: all {len(result)} have wingspan, {has_status} with IUCN status, {has_family} with family", file=sys.stderr)
    print(f"Largest: {result[0]['common']} ({result[0]['wingspan_cm']} cm)", file=sys.stderr)
    print(f"Smallest: {result[-1]['common']} ({result[-1]['wingspan_cm']} cm)", file=sys.stderr)

    with open("species.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    run()
