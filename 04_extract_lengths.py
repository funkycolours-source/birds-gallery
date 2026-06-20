#!/usr/bin/env python3
"""Extract length/height from Wikipedia article text via Claude API.

Fallback step 3: for birds still missing length_cm after Wikidata queries.

Usage:
  ANTHROPIC_API_KEY=sk-... python3 04_extract_lengths.py

Reads species.json, fetches Wikipedia article text for birds with null length_cm,
asks Claude to extract any stated size figure, and updates species.json in place.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import re

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

EXTRACT_PROMPT = (
    "From this Wikipedia article about a bird species, extract the bird's body "
    "length or height in centimetres. Look for phrases like 'X cm long', "
    "'X–Y cm in length', 'X inches', 'height of X', or similar. Convert inches "
    "to cm (1 in = 2.54 cm). If a range is given, return the midpoint.\n\n"
    "Respond with ONLY a single number (the length/height in cm), nothing else. "
    "If no length or height is stated in the text, respond with just: null"
)

def fetch_article_text(wiki_title):
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": wiki_title,
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
        "origin": "*",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "birds-gallery/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            text = page.get("extract", "")
            if text:
                return text[:6000]
    except Exception as e:
        print(f"  Wikipedia fetch failed: {e}", file=sys.stderr)
    return None

def extract_length(article_text, bird_name):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 20,
        "messages": [
            {
                "role": "user",
                "content": f"Article about {bird_name}:\n\n{article_text}\n\n{EXTRACT_PROMPT}"
            }
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        text = data["content"][0]["text"].strip()
        if text.lower() == "null":
            return None
        match = re.search(r"[\d.]+", text)
        if match:
            v = float(match.group())
            if 2 <= v <= 500:
                return round(v, 1)
        return None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  API error {e.code}: {error_body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  API call failed: {e}", file=sys.stderr)
        return None

def run():
    if not API_KEY:
        print("Set ANTHROPIC_API_KEY environment variable first.", file=sys.stderr)
        print("Usage: ANTHROPIC_API_KEY=sk-... python3 04_extract_lengths.py", file=sys.stderr)
        sys.exit(1)

    with open("species.json") as f:
        birds = json.load(f)

    missing = [b for b in birds if not b.get("length_cm")]
    print(f"{len(missing)} of {len(birds)} birds missing length — extracting from Wikipedia...", file=sys.stderr)

    extracted = 0
    for i, bird in enumerate(missing):
        print(f"[{i+1}/{len(missing)}] {bird['common']}...", file=sys.stderr, end=" ")

        article = fetch_article_text(bird["wiki"])
        if not article:
            print("no article", file=sys.stderr)
            continue

        length = extract_length(article, bird["common"])
        if length:
            bird["length_cm"] = length
            extracted += 1
            print(f"→ {length} cm", file=sys.stderr)
        else:
            print("no size found", file=sys.stderr)

        time.sleep(0.3)

    with open("species.json", "w") as f:
        json.dump(birds, f, indent=2, ensure_ascii=False)

    total_with_length = sum(1 for b in birds if b.get("length_cm"))
    print(f"\nDone — extracted {extracted} new lengths, {total_with_length}/{len(birds)} total have length", file=sys.stderr)

if __name__ == "__main__":
    run()
