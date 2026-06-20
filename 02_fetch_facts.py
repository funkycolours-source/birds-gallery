#!/usr/bin/env python3
"""Extract one interesting fact per bird from its Wikipedia article via Claude API.

Usage:
  ANTHROPIC_API_KEY=sk-... python3 02_fetch_facts.py

Reads species.json, fetches each bird's full Wikipedia article text,
asks Claude to extract the single most interesting verifiable fact,
and writes results to facts.json.

Resumes from where it left off if facts.json already exists.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

EXTRACT_PROMPT = (
    "From this Wikipedia article about a bird species, extract the one fact "
    "most likely to surprise a general reader. Use only information stated in "
    "the text — do not invent or infer anything not explicitly present. "
    "Respond with just the fact, one sentence, no preamble."
)

def fetch_article_text(wiki_title):
    """Fetch full plaintext of a Wikipedia article."""
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": wiki_title,
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
        "origin": "*",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "birds-gallery/1.0 (funkycolours@gmail.com)"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                text = page.get("extract", "")
                if text:
                    return text[:8000]
            return None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                wait = 10 * (attempt + 1)
                print(f"  429 — waiting {wait}s...", file=sys.stderr, end=" ")
                time.sleep(wait)
                continue
            print(f"  Wikipedia fetch failed: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"  Wikipedia fetch failed: {e}", file=sys.stderr)
            return None
    return None

def extract_fact(article_text, bird_name):
    """Ask Claude to extract one interesting fact from the article."""
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 150,
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
        return data["content"][0]["text"].strip()
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
        print("Usage: ANTHROPIC_API_KEY=sk-... python3 02_fetch_facts.py", file=sys.stderr)
        sys.exit(1)

    with open("species.json") as f:
        birds = json.load(f)

    # Resume from existing facts.json if present
    facts = {}
    if os.path.exists("facts.json"):
        with open("facts.json") as f:
            facts = json.load(f)
        print(f"Resuming — {len(facts)} facts already done", file=sys.stderr)

    remaining = [b for b in birds if b["wiki"] not in facts]
    print(f"Processing {len(remaining)} of {len(birds)} birds...", file=sys.stderr)

    for i, bird in enumerate(remaining):
        wiki = bird["wiki"]
        common = bird["common"]
        print(f"[{i+1}/{len(remaining)}] {common}...", file=sys.stderr, end=" ")

        article = fetch_article_text(wiki)
        if not article:
            print("no article", file=sys.stderr)
            continue

        fact = extract_fact(article, common)
        if fact:
            facts[wiki] = fact
            print(f"✓ {fact[:60]}...", file=sys.stderr)
        else:
            print("failed", file=sys.stderr)

        # Save after each to allow resume
        with open("facts.json", "w") as f:
            json.dump(facts, f, indent=2, ensure_ascii=False)

        time.sleep(2)

    print(f"\nDone — {len(facts)} facts saved to facts.json", file=sys.stderr)

if __name__ == "__main__":
    run()
