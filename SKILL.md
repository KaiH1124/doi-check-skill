---
name: doi-check
description: >
  Verify BibTeX references against the Crossref API to catch DOI errors,
  year mismatches, author mismatches, and title discrepancies. Use this skill
  whenever the user wants to validate, check, or audit citations in a LaTeX
  manuscript — including phrases like "check my references", "verify DOIs",
  "validate citations", "doi-check", "/doi-check", or "run doi-check on my bib".
  Also trigger when the user suspects a citation might be wrong or wants a
  systematic audit of their bibliography before submission.
---

# doi-check — BibTeX Reference Verifier

Systematically verifies every **actually-cited** reference in a LaTeX manuscript
against the Crossref REST API, then guides the user through interactive repair
of any flagged entries.

## Scripts (all stdlib only — no pip installs)

```
scripts/
├── bib_utils.py      parse_bib, collect_cited_keys, strip_latex_comments
├── crossref_api.py   query_doi, search_by_title_author, extract_fields, detect_mismatches
├── bib_updater.py    fetch_metadata, format_bibtex_entry, patch_bib_entry
└── doi_check.py      main CLI orchestrator (5-step workflow below)
```

## Running the skill

```bash
doi-check \
  --bib  <path/to/refs.bib> \
  --tex  <manuscript_directory> \
  --out  <output_directory>        # default: output/ref_verification/
```

Add `--no-interactive` to skip the repair loop (report only).

Install the CLI:

```bash
uv tool install "git+https://github.com/KaiH1124/doi-check-skill.git"
```

Detect the `.bib` path, manuscript directory, and output directory from
context or by asking the user before running.

---

## 5-Step Workflow

### Step 1 — Filter to actually-cited references
- Parse the `.bib` file (`bib_utils.parse_bib`)
- Scan all `.tex` files recursively, stripping LaTeX `%` comments before
  extracting `\cite{}` / `\citep{}` / `\citet{}` keys
  (`bib_utils.collect_cited_keys`)
- Only cited entries proceed to verification — entries in bib but not cited
  are ignored; entries cited but missing from bib are flagged immediately

### Step 2 — Run DOI check, output CSV and summary
- For each cited entry with a DOI: query `https://api.crossref.org/works/{doi}`
- Compare year, first-author surname, and title word overlap (≥ 40 % required)
- Write `ref_check.csv` and `summary.txt` to the output directory
- Ask the user: *"N issues found — start interactive repair?"*

### Step 3 — Search for correct DOIs (for FLAGGED / ERROR entries)
- For each problematic entry, call `crossref_api.search_by_title_author()`
  using the bib title + first-author surname + year
- Present the top-5 Crossref candidates with DOI, title, author, year, journal
- User selects a candidate, enters a DOI manually, or skips

### Step 4 — Update .bib
- Two repair modes (user chooses):
  - **doi-only**: replace only the `doi` field (`bib_updater.patch_bib_entry`)
  - **full**: fetch complete metadata from Crossref and regenerate the entire
    entry (`bib_updater.fetch_metadata` + `format_bibtex_entry`)
- Ask the user: *"Re-run the check to verify?"*

### Step 5 — Loop until clean
- Repeat steps 1–4 until zero FLAGGED/ERROR entries remain
- Print a final prompt asking the user to do a **manual double-check** of the
  CSV before submission

---

## Status values in CSV

| Status | Meaning |
|--------|---------|
| `OK` | DOI resolved, year/author/title all match |
| `FLAGGED` | DOI resolved but at least one mismatch detected |
| `ERROR` | Crossref could not resolve the DOI (404, network, etc.) |
| `SKIP_NO_DOI` | Entry has no DOI (books, standards, theses) — not queried |

## Mismatch flags

- `YEAR_MISMATCH(bib=XXXX,cr=YYYY)` — year differs
- `AUTHOR_MISMATCH(bib=surname,cr=surname)` — first-author surname differs
- `TITLE_LOW_OVERLAP(0.XX)` — fewer than 40 % of significant words match
- `API_ERROR: ...` — network or HTTP error

---

## IMPORTANT: Never add inline BibTeX comments

**Do NOT add `% ...` at the end of BibTeX field lines**, e.g.:

```bibtex
% WRONG — BibTeX parser treats this as a new field name
doi = {10.1016/...},  % NOTE: check this
```

BibTeX only allows `%` comments on their own dedicated lines, outside entries.
Inline end-of-line comments cause *"missing field name"* errors and silently
drop the whole entry. If a note is needed, place it before the entry:

```bibtex
% NOTE: Crossref title differs; verify manually
@article{key,
  doi = {10.1016/...},
}
```

---

## Notes

- Crossref rate limit: 0.2 s sleep between requests — ~15 s for 50 DOIs
- `TITLE_LOW_OVERLAP` alone may be a false positive for old papers where
  Crossref metadata is incomplete (e.g. 1916 Du Bois paper)
- Books, standards (ISO/ASHRAE), PhD theses, GitHub repos have no DOI and
  appear as `SKIP_NO_DOI` — expected behaviour
- The skill uses **only Python stdlib** (re, csv, json, urllib, pathlib,
  argparse) and is safe to publish/share without any dependency management
- The search step uses `https://api.crossref.org/works?query=…` directly —
  no MCP tools or third-party packages required, making the skill fully
  self-contained and portable to any Claude Code environment
