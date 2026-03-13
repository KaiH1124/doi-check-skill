"""
crossref_api.py  —  Crossref REST API helpers
----------------------------------------------
- query_doi(doi)            verify a DOI and return its Crossref metadata
- search_by_title_author()  find candidate DOIs when the current one is wrong
- extract_fields()          normalise Crossref message → flat dict
- detect_mismatches()       compare bib entry against Crossref metadata

All network calls use Python stdlib urllib only.
"""

import re
import json
import time
import urllib.request
import urllib.parse
from typing import Optional

HEADERS = {"User-Agent": "doi-check-skill/1.0 (mailto:research@example.com)"}
_CROSSREF_WORKS  = "https://api.crossref.org/works/{doi}"
_CROSSREF_SEARCH = "https://api.crossref.org/works?query={q}&rows={rows}&select=DOI,title,author,published-print,published-online,issued,container-title,type"


# ── Low-level requests ────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 12) -> Optional[dict]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


# ── DOI lookup ────────────────────────────────────────────────────────────────

def query_doi(doi: str) -> dict:
    """
    Query Crossref for a single DOI.

    Returns the raw Crossref 'message' dict, or {'_error': ...} on failure.
    """
    url = _CROSSREF_WORKS.format(doi=urllib.parse.quote(doi, safe="/:"))
    data = _get(url)
    if data is None or "_error" in data:
        return data or {"_error": "no response"}
    return data.get("message", {"_error": "empty message"})


# ── Title+author search ───────────────────────────────────────────────────────

def search_by_title_author(title: str, first_author: str = "",
                            year: str = "", rows: int = 5) -> list:
    """
    Search Crossref by title (and optionally first-author surname / year).

    Returns a list of candidate dicts:
      [{doi, title, first_author, year, journal, score_hint}]
    sorted by Crossref relevance (best first).
    """
    query_parts = [title]
    if first_author:
        query_parts.append(first_author)
    if year:
        query_parts.append(year)
    q = urllib.parse.quote(" ".join(query_parts))
    url = _CROSSREF_SEARCH.format(q=q, rows=rows)

    data = _get(url)
    if not data or "_error" in data:
        return []

    items = data.get("message", {}).get("items", [])
    results = []
    for item in items:
        cr_titles = item.get("title", [])
        cr_title  = cr_titles[0] if cr_titles else ""

        authors = item.get("author", [])
        cr_first = authors[0].get("family", "") if authors else ""

        cr_year = ""
        for df in ("published-print", "published-online", "issued"):
            parts = item.get(df, {}).get("date-parts", [[]])
            if parts and parts[0]:
                cr_year = str(parts[0][0])
                break

        journals = item.get("container-title", [])
        cr_journal = journals[0] if journals else ""

        results.append({
            "doi":         item.get("DOI", ""),
            "title":       cr_title,
            "first_author": cr_first,
            "year":        cr_year,
            "journal":     cr_journal,
            "link":        f"https://doi.org/{item.get('DOI', '')}",
        })
    return results


# ── Field extraction ──────────────────────────────────────────────────────────

def extract_fields(msg: dict) -> dict:
    """
    Normalise a Crossref message dict into a flat result dict.

    Keys: cr_title, cr_first_author, cr_year, cr_journal, cr_error
    """
    if "_error" in msg:
        return {"cr_title": "", "cr_first_author": "", "cr_year": "",
                "cr_journal": "", "cr_error": msg["_error"]}

    titles = msg.get("title", [])
    cr_title = titles[0] if titles else ""

    authors = msg.get("author", [])
    cr_first_author = authors[0].get("family", "") if authors else ""

    cr_year = ""
    for df in ("published-print", "published-online", "issued"):
        parts = msg.get(df, {}).get("date-parts", [[]])
        if parts and parts[0]:
            cr_year = str(parts[0][0])
            break

    journals = msg.get("container-title", [])
    cr_journal = journals[0] if journals else ""

    return {
        "cr_title":        cr_title,
        "cr_first_author": cr_first_author,
        "cr_year":         cr_year,
        "cr_journal":      cr_journal,
        "cr_error":        "",
        "_raw":            msg,   # keep raw for bib_updater
    }


# ── Mismatch detection ────────────────────────────────────────────────────────

def detect_mismatches(entry: dict, cr: dict) -> list:
    """
    Compare a bib entry dict against Crossref fields.

    entry keys: title, authors, year
    cr keys:    cr_title, cr_first_author, cr_year, cr_error

    Returns a list of human-readable flag strings.
    """
    flags = []

    if cr.get("cr_error"):
        flags.append(f"API_ERROR: {cr['cr_error']}")
        return flags

    # Year
    bib_year = entry.get("year", "").strip()
    cr_year  = cr.get("cr_year", "").strip()
    if bib_year and cr_year and bib_year != cr_year:
        flags.append(f"YEAR_MISMATCH(bib={bib_year},cr={cr_year})")

    # First-author surname (ASCII-normalised)
    def ascii_only(s: str) -> str:
        return re.sub(r"[^a-z]", "", s.lower())

    bib_authors = entry.get("authors", "")
    cr_first    = cr.get("cr_first_author", "")
    if cr_first and bib_authors:
        first_raw   = re.split(r"\band\b", bib_authors, flags=re.IGNORECASE)[0].strip()
        bib_surname = (first_raw.split(",")[0].strip()
                       if "," in first_raw else first_raw.split()[-1].strip())
        a, b = ascii_only(cr_first), ascii_only(bib_surname)
        if a and b and a not in b and b not in a:
            flags.append(f"AUTHOR_MISMATCH(bib={bib_surname},cr={cr_first})")

    # Title word overlap (≥ 40 % required)
    bib_words = set(re.findall(r"\w{4,}", entry.get("title", "").lower()))
    cr_words  = set(re.findall(r"\w{4,}", cr.get("cr_title", "").lower()))
    if bib_words and cr_words:
        overlap = len(bib_words & cr_words) / min(len(bib_words), len(cr_words))
        if overlap < 0.4:
            flags.append(f"TITLE_LOW_OVERLAP({overlap:.2f})")

    return flags
