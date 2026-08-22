"""
scrape_oracle_docs.py

OPTIONAL knowledge-base expander. NOT run automatically by anything else in
this project, and it was NOT run in the sandbox this project was built in
(that sandbox's network allowlist only covers pypi/npm/github, not
docs.oracle.com). You need to run this yourself, from a machine with normal
internet access (e.g. inside Antigravity).

WHAT THIS DOES
--------------
Fetches Oracle's own official "Database Error Messages" documentation pages
and extracts each error's official Cause/Action text, then appends any codes
not already in our hand-written knowledge base (build_knowledge_base.py) to
data/knowledge_base/oracle_errors_kb.jsonl.

RESPONSIBLE USE NOTES
---------------------
- This is meant for building an INTERNAL reference tool (exactly this
  project), not for republishing/redistributing Oracle's documentation
  as a public dataset or product. Check Oracle's site terms of use before
  doing anything beyond internal engineering use.
- Be a polite scraper: this script rate-limits requests and only hits a
  documentation index once. Don't remove the delay or parallelize this
  aggressively against Oracle's servers.
- Oracle's docs change their page structure between versions sometimes --
  the CSS selectors below were written against the general shape of Oracle's
  Database Error Messages guide as of Oracle Database 19c/21c documentation.
  If they return nothing, open one page in a browser, inspect the actual
  HTML, and adjust SELECTOR_CAUSE / SELECTOR_ACTION below.

USAGE
-----
    pip install requests beautifulsoup4

    # Single chapter page (e.g. just the ORA-xxxxx chapter):
    python src/data_generation/scrape_oracle_docs.py --url <chapter-page-url> --limit 500

    # Whole guide (recommended): crawl every chapter linked from the TOC
    python src/data_generation/scrape_oracle_docs.py \
        --toc-url https://docs.oracle.com/cd/E11882_01/server.112/e17766/toc.htm \
        --limit 5000

The guide's TOC page lists ~130 chapters (one per error-code-prefix range,
e.g. "TNS-00000 to TNS-12699", "UDE-00001 to UDE-00054"). --toc-url discovers
and scrapes all of them in one run, rate-limited (1.5s between requests) to
stay polite. Search "Oracle Database Error Messages <version>" if you want a
newer version's TOC than 11g R2 (11.2).
"""

import argparse
import json
import os
import re
import time

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("This script needs: pip install requests beautifulsoup4")
    raise

CODE_RE = re.compile(r"\b([A-Z]{2,4})-(\d{3,5})\b")


def fetch_page(url: str) -> str:
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (internal-kb-builder/1.0)"})
    resp.raise_for_status()
    return resp.text


def extract_entries_from_html(html: str):
    """Best-effort extraction of (code, message, cause, action) tuples from
    an Oracle error-messages documentation page. Oracle typically renders
    each error as a heading (the code + short message) followed by
    "Cause:" and "Action:" paragraphs. Adjust the selectors below if
    Oracle's current page structure differs.
    """
    soup = BeautifulSoup(html, "html.parser")
    entries = []

    # Oracle doc pages commonly use <dt>/<dd> or heading+paragraph patterns
    # for each error entry. We look for any heading-like element whose text
    # starts with a recognizable error code, then read forward until the
    # next such heading to gather that entry's body text.
    candidates = soup.find_all(["h2", "h3", "h4", "dt", "dd", "p", "strong"])

    current = None
    for el in candidates:
        text = el.get_text(" ", strip=True)
        m = CODE_RE.match(text)
        if m:
            if current:
                entries.append(current)
            code = f"{m.group(1)}-{m.group(2)}"
            message = text[m.end():].lstrip(": ").strip()
            current = {"code": code, "message": message, "cause": "", "action": ""}
            continue

        if current is not None:
            lower = text.lower()
            if lower.startswith("cause:"):
                current["cause"] = text[len("cause:"):].strip()
            elif lower.startswith("action:"):
                current["action"] = text[len("action:"):].strip()

    if current:
        entries.append(current)

    return entries


def merge_into_kb(new_entries, kb_path: str):
    existing_codes = set()
    lines = []
    if os.path.exists(kb_path):
        with open(kb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                lines.append(line)
                existing_codes.add(json.loads(line)["code"])

    added = 0
    for e in new_entries:
        if e["code"] in existing_codes:
            continue
        if not e.get("cause") and not e.get("action"):
            continue  # skip entries we couldn't actually extract useful text for
        record = {
            "code": e["code"],
            "message": e.get("message", ""),
            "category": "Scraped",
            "cause": e.get("cause", ""),
            "solution": e.get("action", ""),
            "keywords": [],
            "severity": "unknown",
        }
        lines.append(json.dumps(record, ensure_ascii=False))
        existing_codes.add(e["code"])
        added += 1

    with open(kb_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return added


def discover_chapter_urls(toc_url: str) -> list:
    """Given the table-of-contents page of an Oracle error-messages guide
    (e.g. https://docs.oracle.com/cd/E11882_01/server.112/e17766/toc.htm),
    find every chapter page URL it links to (things like tnsus.htm,
    udeus.htm, sclsmsg.htm -- each chapter covers one prefix's code range).
    """
    html = fetch_page(toc_url)
    soup = BeautifulSoup(html, "html.parser")
    base = toc_url.rsplit("/", 1)[0] + "/"

    urls = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Clean off any hash fragment
        clean_href = href.split("#")[0]
        # Chapter pages in this guide are relative .htm links living next to
        # toc.htm itself (not title.htm/preface.htm/index.htm, which don't
        # contain error entries).
        if not clean_href.endswith(".htm"):
            continue
        skip_names = {"toc.htm", "title.htm", "preface.htm", "index.htm", "cpyright.htm"}
        name = clean_href.rsplit("/", 1)[-1]
        if name in skip_names:
            continue
        full_url = clean_href if clean_href.startswith("http") else base + clean_href
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls


def crawl_and_merge(toc_url: str, kb_path: str, limit: int, delay_seconds: float = 1.5):
    """Full-guide crawl: discover every chapter page from the TOC, scrape
    each one, and merge all new entries into the KB in one pass. Prints
    progress as it goes since this can take a few minutes across ~130 pages.
    """
    chapter_urls = discover_chapter_urls(toc_url)
    print(f"Discovered {len(chapter_urls)} chapter pages from {toc_url}")

    all_entries = []
    for i, url in enumerate(chapter_urls, 1):
        try:
            html = fetch_page(url)
        except Exception as e:
            print(f"  [{i}/{len(chapter_urls)}] SKIP {url} ({e})")
            continue
        entries = extract_entries_from_html(html)
        print(f"  [{i}/{len(chapter_urls)}] {url} -> {len(entries)} entries")
        all_entries.extend(entries)
        time.sleep(delay_seconds)  # stay polite across the whole crawl

    all_entries = all_entries[:limit]
    added = merge_into_kb(all_entries, kb_path)
    print(f"\nTotal candidate entries extracted: {len(all_entries)}")
    print(f"New entries added to {kb_path}: {added}")


def main():
    parser = argparse.ArgumentParser(description="Expand the Oracle error KB from Oracle's official documentation.")
    parser.add_argument("--url", help="URL of a single Oracle Database Error Messages chapter page")
    parser.add_argument("--toc-url", help="URL of the guide's table-of-contents page -- crawls every chapter it links to")
    parser.add_argument("--limit", type=int, default=5000, help="Max number of new entries to add")
    parser.add_argument(
        "--kb-path",
        default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge_base", "oracle_errors_kb.jsonl")),
    )
    args = parser.parse_args()

    if not args.url and not args.toc_url:
        parser.error("Provide either --url (one chapter) or --toc-url (crawl the whole guide)")

    if args.toc_url:
        crawl_and_merge(args.toc_url, args.kb_path, args.limit)
        return

    print(f"Fetching {args.url} ...")
    html = fetch_page(args.url)
    time.sleep(1)  # be polite

    entries = extract_entries_from_html(html)
    print(f"Extracted {len(entries)} candidate entries from the page.")

    entries = entries[: args.limit]
    added = merge_into_kb(entries, args.kb_path)
    print(f"Added {added} new entries to {args.kb_path}")


if __name__ == "__main__":
    main()
