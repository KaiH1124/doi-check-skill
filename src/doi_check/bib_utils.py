"""
bib_utils.py  —  BibTeX parsing and LaTeX cite-key extraction
--------------------------------------------------------------
All functions use Python stdlib only (re, pathlib).
"""

import re
from pathlib import Path


# ── LaTeX comment stripping ───────────────────────────────────────────────────

def strip_latex_comments(text: str) -> str:
    r"""Remove LaTeX % comments (to end of line), preserving escaped \%."""
    placeholder = "\x00PCT\x00"
    text = text.replace(r"\%", placeholder)
    text = re.sub(r"%[^\n]*", "", text)
    return text.replace(placeholder, r"\%")


# ── BibTeX parser ─────────────────────────────────────────────────────────────

def _get_field(body: str, field: str) -> str:
    """Extract a single BibTeX field value from an entry body string."""
    pat = re.compile(
        r"\b" + re.escape(field) + r"\s*=\s*"
        r"(?:\{((?:[^{}]|\{[^{}]*\})*)\}"   # { ... } (one level nesting)
        r'|"([^"]*)"'                          # " ... "
        r"|(\d+))",                             # bare number
        re.IGNORECASE | re.DOTALL
    )
    m = pat.search(body)
    if not m:
        return ""
    val = m.group(1) or m.group(2) or m.group(3) or ""
    return re.sub(r"\s+", " ", val).strip()


def parse_bib(bib_path: Path) -> dict:
    """
    Parse a BibTeX file.

    Returns
    -------
    dict  {cite_key: {"type", "doi", "title", "authors", "year", "journal"}}
    """
    text = bib_path.read_text(encoding="utf-8")

    entry_pat = re.compile(
        r"@(\w+)\s*\{\s*([^,\s]+)\s*,\s*(.*?)\n\}",
        re.DOTALL | re.IGNORECASE
    )

    entries = {}
    for m in entry_pat.finditer(text):
        etype = m.group(1).lower()
        key   = m.group(2).strip()
        body  = m.group(3)
        entries[key] = {
            "type":    etype,
            "doi":     _get_field(body, "doi"),
            "title":   _get_field(body, "title"),
            "authors": _get_field(body, "author"),
            "year":    _get_field(body, "year"),
            "journal": _get_field(body, "journal"),
        }
    return entries


# ── Cite-key collection from .tex files ───────────────────────────────────────

def collect_cited_keys(tex_dir: Path) -> set:
    r"""
    Scan all .tex files under tex_dir recursively.

    Returns the set of cite-keys actually used in non-commented \cite{}
    commands (\cite, \citep, \citet and starred/optional-arg variants).
    """
    cited = set()
    cite_pat = re.compile(r"\\cite[tp]?\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
    for tex_file in tex_dir.rglob("*.tex"):
        raw  = tex_file.read_text(encoding="utf-8", errors="replace")
        text = strip_latex_comments(raw)
        for m in cite_pat.finditer(text):
            for key in m.group(1).split(","):
                cited.add(key.strip())
    return cited
