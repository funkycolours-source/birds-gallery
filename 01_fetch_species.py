#!/usr/bin/env python3
"""Fetch bird species from Wikidata via SPARQL and output species.json."""

import json
import urllib.request
import urllib.parse
import sys

UNIT_TO_CM = {
    "Q174728": 100, "Q11573": 1, "Q174789": 0.1, "Q218593": 2.54, "Q3710": 30.48,
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
    """Convert to cm, with heuristic correction for Wikidata's inconsistent units.

    Wikidata wingspan data is notoriously messy: values labeled as "metre"
    are often actually in cm, and values labeled "centimetre" are often in metres.
    Use the stated unit conversion first, then sanity-check the result.
    Bird wingspans range from ~6 cm (bee hummingbird) to ~350 cm (wandering albatross).
    """
    if not raw or not unit_uri:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None

    unit = qid(unit_uri)
    factor = UNIT_TO_CM.get(unit, 100)
    converted = v * factor

    # If the converted value is plausible for a bird wingspan, use it
    if 5 <= converted <= 400:
        return round(converted, 1)

    # Heuristic: if the raw value itself is plausible as cm, the unit is probably wrong
    if 5 <= v <= 400:
        return round(v, 1)

    # If raw * 100 is plausible (value was in metres but very small number), try that
    if 5 <= v * 100 <= 400:
        return round(v * 100, 1)

    return None

def run():
    print("Fetching birds with wingspan + Wikipedia article + image...", file=sys.stderr)
    rows = sparql("""
    SELECT ?bird ?birdLabel ?article ?sciName ?wsRaw ?wsUnit ?pop WHERE {
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
      OPTIONAL { ?bird wdt:P1082 ?pop . }
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

        if wiki_title in birds:
            if ws and not birds[wiki_title]["wingspan_cm"]:
                birds[wiki_title]["wingspan_cm"] = ws
            continue

        population = None
        pop_val = r.get("pop", {}).get("value")
        if pop_val:
            try:
                v = int(float(pop_val))
                if v > 0:
                    population = v
            except ValueError:
                pass

        birds[wiki_title] = {
            "wiki": wiki_title,
            "common": r.get("birdLabel", {}).get("value", wiki_title),
            "sci": r.get("sciName", {}).get("value", ""),
            "length_cm": None,
            "wingspan_cm": ws,
            "population": population,
        }

    result = [b for b in birds.values() if b["wingspan_cm"]]
    result.sort(key=lambda b: b["wingspan_cm"], reverse=True)
    result = result[:500]

    print(f"\nWriting {len(result)} species to species.json", file=sys.stderr)
    with open("species.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    has_pop = sum(1 for b in result if b["population"])
    print(f"Stats: all {len(result)} have wingspan, {has_pop} with population", file=sys.stderr)
    print(f"Largest: {result[0]['common']} ({result[0]['wingspan_cm']} cm)", file=sys.stderr)
    print(f"Smallest: {result[-1]['common']} ({result[-1]['wingspan_cm']} cm)", file=sys.stderr)

if __name__ == "__main__":
    run()
