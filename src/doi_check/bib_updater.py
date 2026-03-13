"""
bib_updater.py  —  Fetch full metadata from Crossref and patch a .bib file
---------------------------------------------------------------------------
Public API
----------
fetch_metadata(doi)                   → dict of clean BibTeX fields
format_bibtex_entry(key, metadata)    → BibTeX string
patch_bib_entry(bib_path, key, doi)   → updates DOI (and optionally fields)
                                         in-place in the .bib file

All network calls use Python stdlib urllib only.
"""

import re
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

HEADERS = {"User-Agent": "doi-check-skill/1.0 (mailto:research@example.com)"}
_CROSSREF_WORKS = "https://api.crossref.org/works/{doi}"


# ── Metadata fetch ────────────────────────────────────────────────────────────

def fetch_metadata(doi: str) -> dict:
    """
    Fetch full metadata for a DOI from Crossref.

    Returns a dict with keys:
      doi, title, authors, year, journal, volume, number, pages,
      publisher, entry_type, error
    """
    url = _CROSSREF_WORKS.format(doi=urllib.parse.quote(doi, safe="/:"))
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"doi": doi, "error": str(e)}

    msg = data.get("message", {})

    # Title
    titles = msg.get("title", [])
    title = titles[0] if titles else ""

    # Authors  →  "Last, First and Last, First …"
    raw_authors = msg.get("author", [])
    author_parts = []
    for a in raw_authors:
        family = a.get("family", "")
        given  = a.get("given", "")
        if family:
            author_parts.append(f"{family}, {given}" if given else family)
    authors = " and ".join(author_parts)

    # Year
    year = ""
    for df in ("published-print", "published-online", "issued"):
        parts = msg.get(df, {}).get("date-parts", [[]])
        if parts and parts[0]:
            year = str(parts[0][0])
            break

    # Journal / container
    containers = msg.get("container-title", [])
    journal = containers[0] if containers else ""

    # Volume / issue / pages
    volume = msg.get("volume", "")
    number = msg.get("issue", "")
    pages  = msg.get("page", "").replace("-", "--")  # ensure en-dash

    # Publisher
    publisher = msg.get("publisher", "")

    # Entry type mapping
    cr_type    = msg.get("type", "journal-article")
    entry_type = _map_entry_type(cr_type)

    return {
        "doi":        doi,
        "title":      title,
        "authors":    authors,
        "year":       year,
        "journal":    journal,
        "volume":     volume,
        "number":     number,
        "pages":      pages,
        "publisher":  publisher,
        "entry_type": entry_type,
        "error":      "",
    }


def _map_entry_type(cr_type: str) -> str:
    mapping = {
        "journal-article":    "article",
        "book":               "book",
        "book-chapter":       "incollection",
        "proceedings-article": "inproceedings",
        "dissertation":       "phdthesis",
        "dataset":            "misc",
        "posted-content":     "misc",
        "report":             "techreport",
        "monograph":          "book",
        "other":              "misc",
    }
    return mapping.get(cr_type, "misc")


# ── BibTeX formatter ──────────────────────────────────────────────────────────

def format_bibtex_entry(cite_key: str, meta: dict) -> str:
    """
    Generate a clean BibTeX entry string from a metadata dict.

    Only non-empty fields are included.
    """
    etype = meta.get("entry_type", "misc")
    lines = [f"@{etype}{{{cite_key},"]

    def field(name: str, value: str):
        if value:
            lines.append(f"  {name:<12}= {{{value}}},")

    field("author",    meta.get("authors", ""))
    field("title",     meta.get("title", ""))

    if etype == "article":
        field("journal",   meta.get("journal", ""))
    elif etype in ("book", "incollection", "techreport"):
        field("publisher", meta.get("publisher", ""))

    field("year",      meta.get("year", ""))
    field("volume",    meta.get("volume", ""))
    field("number",    meta.get("number", ""))
    field("pages",     meta.get("pages", ""))
    field("doi",       meta.get("doi", ""))

    lines.append("}")
    return "\n".join(lines)


# ── In-place bib patcher ──────────────────────────────────────────────────────

def patch_bib_entry(bib_path: Path, cite_key: str, new_doi: str,
                    update_fields: bool = False) -> bool:
    """
    Patch a .bib file in-place for a given cite_key.

    - Always replaces the `doi` field with new_doi.
    - If update_fields=True, also replaces title/author/year/journal/volume/
      number/pages by fetching fresh metadata from Crossref.

    Returns True on success, False on failure.

    IMPORTANT: Never adds inline (end-of-line) BibTeX comments.
    Notes go on their own lines before the entry if needed.
    """
    text = bib_path.read_text(encoding="utf-8")

    # Locate the entry block
    entry_pat = re.compile(
        r"(@\w+\s*\{\s*" + re.escape(cite_key) + r"\s*,.*?\n\})",
        re.DOTALL | re.IGNORECASE
    )
    m = entry_pat.search(text)
    if not m:
        print(f"  ✗ cite_key '{cite_key}' not found in {bib_path.name}")
        return False

    old_block = m.group(1)
    new_block = old_block

    if update_fields:
        meta = fetch_metadata(new_doi)
        if meta.get("error"):
            print(f"  ✗ Crossref fetch failed: {meta['error']}")
            return False
        new_block = format_bibtex_entry(cite_key, meta)
    else:
        # Only replace the doi field
        doi_pat = re.compile(
            r"(\bdoi\s*=\s*)(\{[^}]*\}|\"[^\"]*\")",
            re.IGNORECASE
        )
        if doi_pat.search(new_block):
            new_block = doi_pat.sub(r"\g<1>{" + new_doi + "}", new_block)
        else:
            # doi field missing — append before closing brace
            new_block = new_block.rstrip()
            if new_block.endswith("}"):
                new_block = new_block[:-1].rstrip(",") + f",\n  doi          = {{{new_doi}}},\n}}"

    new_text = text[:m.start()] + new_block + text[m.end():]
    bib_path.write_text(new_text, encoding="utf-8")
    print(f"  ✓ Updated '{cite_key}' in {bib_path.name}")
    return True
