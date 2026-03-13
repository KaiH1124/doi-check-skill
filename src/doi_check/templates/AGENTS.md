# doi-check

When the user asks to verify, check, or audit BibTeX references or DOIs in a
LaTeX manuscript, use the `doi-check` command-line tool.

## When to invoke

- "check my references" / "verify DOIs" / "validate citations"
- "run doi-check" / "/doi-check"
- User suspects a citation might be wrong
- Pre-submission bibliography audit

## Usage

```bash
doi-check \
  --bib  <path/to/refs.bib> \
  --tex  <manuscript_directory> \
  --out  <output_directory>
```

Add `--no-interactive` for report-only mode (no interactive repair prompts).

Detect the `.bib` path, manuscript directory, and output directory from
context or by asking the user before running.

## Output

Produces `ref_check.csv` and `summary.txt` in the output directory.

Status values:
- `OK` — DOI resolves, year/author/title all match
- `FLAGGED` — DOI resolves but at least one mismatch detected
- `ERROR` — Crossref could not resolve the DOI
- `SKIP_NO_DOI` — entry has no DOI (books, theses) — skipped

## Notes

- arXiv DOIs (`10.48550/arXiv.xxx`) are NOT in Crossref — they return ERROR;
  use the journal DOI when available
- Books, standards, theses without DOIs are silently skipped
