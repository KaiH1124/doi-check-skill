# doi-check-skill

Verify BibTeX references against the [Crossref REST API](https://api.crossref.org) — catch DOI errors, year mismatches, author mismatches, and title discrepancies before manuscript submission.

## Features

- 🎯 **High accuracy** — compares year, first-author surname, and title word overlap against live Crossref metadata, not just DOI format
- 🔍 **Transparent results** — every check produces a `ref_check.csv` with side-by-side bib vs. Crossref fields so you can see exactly what was compared
- 🔄 **Interactive repair** — for each flagged entry, presents top Crossref candidates and lets you choose a replacement DOI or update full metadata in one step
- 📦 **Zero dependencies** — pure Python stdlib (`re`, `csv`, `json`, `urllib`, `pathlib`, `argparse`), runs anywhere without `pip install`

> **IMPORTANT:** This tool queries the Crossref API and results are only as accurate as the data Crossref holds. Always manually verify flagged entries — do not blindly accept suggested replacements.

---

## Install

**Step 1 — install the CLI** (works for all AI coding tools):

```bash
uv tool install "git+https://github.com/KaiH1124/doi-check-skill.git"
```

To update to the latest version:

```bash
uv tool install "git+https://github.com/KaiH1124/doi-check-skill.git" --force
```

Or with pip:

```bash
pip install "git+https://github.com/KaiH1124/doi-check-skill.git"
pip install --upgrade "git+https://github.com/KaiH1124/doi-check-skill.git"
```

**Step 2 — register the skill** by copying `SKILL.md` to your AI coding tool's skills folder:

| Tool | Destination |
|------|-------------|
| Claude Code | `~/.claude/skills/doi-check/SKILL.md` |
| OpenAI Codex | `~/.codex/skills/doi-check/SKILL.md` |

Create the folder if it doesn't exist, then copy `SKILL.md` from this repo into it.

---

## Usage

Point `doi-check` at your `.bib` file and the directory containing your `.tex` files. It will scan all `.tex` files recursively, verify every cited DOI against Crossref, and write a `ref_check.csv` and `summary.txt` to the output directory (default: `output/ref_verification/`).

```bash
# Check only entries actually cited in .tex files
doi-check --bib refs.bib --tex ./manuscript/

# Check every entry in the bib (no .tex directory needed)
doi-check --bib refs.bib --all
```

Add `--no-interactive` to skip the repair prompts and get a report only.

---

## What it does

### 5-step workflow

1. **Select entries to verify** — parses `.bib`, then either (a) scans `.tex` recursively to find only cited entries (`--tex`), or (b) checks every entry in the bib regardless of citations (`--all`).

2. **Verify DOIs via Crossref** — queries `https://api.crossref.org/works/{doi}` for each cited entry with a DOI. Compares year, first-author surname, and title word overlap (≥ 40% required). Writes `ref_check.csv` and `summary.txt`.

3. **Search for correct DOIs** — for FLAGGED / ERROR entries, searches Crossref by title + author and presents the top-5 candidates.

4. **Update `.bib`** — two repair modes:
   - `doi-only`: replace only the `doi` field
   - `full`: fetch complete metadata from Crossref and regenerate the entire entry

5. **Loop until clean** — repeats until zero FLAGGED / ERROR entries remain.

---

## Output

### `ref_check.csv` columns

| Column | Description |
|--------|-------------|
| `cite_key` | BibTeX citation key |
| `status` | `OK` / `FLAGGED` / `ERROR` / `SKIP_NO_DOI` |
| `mismatch_flags` | Pipe-separated list of detected mismatches |
| `bib_doi` | DOI as recorded in `.bib` |
| `link` | `https://doi.org/<doi>` |
| `bib_year` / `cr_year` | Year in `.bib` vs Crossref |
| `bib_first_author` / `cr_first_author` | First author in `.bib` vs Crossref |
| `bib_title` / `cr_title` | Title (first 100 chars) in `.bib` vs Crossref |

### Status values

| Status | Meaning |
|--------|---------|
| `OK` | DOI resolved; year, author, title all match |
| `FLAGGED` | DOI resolved but at least one mismatch detected |
| `ERROR` | Crossref could not resolve the DOI (404, network, etc.) |
| `SKIP_NO_DOI` | Entry has no DOI (books, standards, theses) — not queried |

### Mismatch flags

- `YEAR_MISMATCH(bib=XXXX,cr=YYYY)` — year differs
- `AUTHOR_MISMATCH(bib=surname,cr=surname)` — first-author surname differs
- `TITLE_LOW_OVERLAP(0.XX)` — fewer than 40% of significant words match
- `API_ERROR: ...` — network or HTTP error

---

## Notes

- Crossref rate limit: 0.2 s sleep between requests — ~15 s for 50 DOIs
- `TITLE_LOW_OVERLAP` alone may be a false positive for old papers where Crossref metadata is incomplete
- Books, standards (ISO/ASHRAE), PhD theses, GitHub repos have no DOI → `SKIP_NO_DOI`
- arXiv DOIs (`10.48550/arXiv.xxx`) are not indexed by Crossref and will return ERROR — use the published journal DOI instead when available

---

## License

MIT — see [LICENSE](LICENSE).
